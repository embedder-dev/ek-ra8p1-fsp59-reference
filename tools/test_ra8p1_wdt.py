"""Execute the complete production WDT translation unit with mock BSP/registers.

The real FSP 5.9 instance and API headers are used unchanged. Only BSP, register,
and generated driver-configuration dependencies are replaced by host fixtures.
"""
from pathlib import Path
import itertools
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
PRODUCTION = BASELINE / "ra/fsp/src/r_wdt/r_wdt.c"
FIXTURES = ROOT / "tools/ra8p1/wdt_test"


def configuration(per_core, core, checks, auto=False, nmi=True, register_nmi=True):
    selected_ofs = ((not auto) << 17) | (3 << 18) | (15 << 20)
    selected_ofs |= (1 << 24) | (2 << 26) | ((not nmi) << 28)
    other_ofs = selected_ofs ^ 0x5FFE0000
    return {
        "TEST_PER_CORE": per_core,
        "TEST_CORE": core,
        "TEST_CHECKS": checks,
        "TEST_AUTO": int(auto),
        "TEST_NMI": int(nmi),
        "TEST_REGISTER_NMI": int(register_nmi),
        "TEST_NMI_SUPPORTED": int(nmi if auto else register_nmi),
        "TEST_SELECTED_OFS": hex(selected_ofs),
        "TEST_OTHER_OFS": hex(other_ofs),
    }


def executable_sections(path):
    """Read executable section bytes from native 64-bit Mach-O or ELF objects."""
    data = path.read_bytes()
    result = {}
    if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
        endian = "<" if data[:4] == b"\xcf\xfa\xed\xfe" else ">"
        commands = struct.unpack_from(endian + "I", data, 16)[0]
        offset = 32
        for _ in range(commands):
            kind, size = struct.unpack_from(endian + "II", data, offset)
            if kind == 0x19:  # LC_SEGMENT_64
                count = struct.unpack_from(endian + "I", data, offset + 64)[0]
                for index in range(count):
                    section = struct.unpack_from(endian + "16s16sQQIIIIIIII", data,
                                                 offset + 72 + 80 * index)
                    name, segment, _, length, start = section[:5]
                    if section[8] & 0x80000400:  # PURE_INSTRUCTIONS or SOME_INSTRUCTIONS
                        key = (segment.rstrip(b"\0"), name.rstrip(b"\0"))
                        result[key] = data[start:start + length]
            offset += size
    elif data[:5] == b"\x7fELF\x02":
        endian = "<" if data[5] == 1 else ">"
        header = struct.unpack_from(endian + "HHIQQQIHHHHHH", data, 16)
        start, step, count, names_index = header[5], header[10], header[11], header[12]
        sections = [struct.unpack_from(endian + "IIQQQQIIQQ", data, start + step * i)
                    for i in range(count)]
        names = sections[names_index]
        strings = data[names[4]:names[4] + names[5]]
        for section in sections:
            if section[2] & 4:  # SHF_EXECINSTR
                name = strings[section[0]:].split(b"\0", 1)[0]
                result[name] = data[section[4]:section[4] + section[5]]
    else:
        raise AssertionError("Legacy object comparison requires native 64-bit Mach-O or ELF")
    if not result or not any(result.values()):
        raise AssertionError("Compiler object has no executable section bytes to compare")
    return result


class WdtProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native C compiler is required for production WDT tests")

    def compile(self, destination, source, defines, *, object_only=False):
        command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror"]
        command += [f"-I{FIXTURES}",
                    f"-I{BASELINE / 'ra/fsp/inc/instances'}",
                    f"-I{BASELINE / 'ra/fsp/inc/api'}"]
        command += [f"-D{key}={value}" for key, value in defines.items()]
        if object_only:
            command += ["-O2", "-c", str(source)]
        else:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), str(FIXTURES / "harness.c")]
            if sys.platform == "darwin" and defines["TEST_PER_CORE"] and defines["TEST_CORE"] == 1:
                # Darwin arm64 PAGEZERO excludes the actual low option addresses; x86_64 permits them.
                command += ["-arch", "x86_64", "-Wl,-pagezero_size,0x4000", "-Wl,-no_pie"]
        command += ["-o", str(destination)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Production WDT header harness cannot compile:\n"
                         + " ".join(command) + "\n" + result.stdout + result.stderr)

    def test_full_production_behavior_matrix(self):
        modes = (
            ("register_nmi", False, True, True),
            ("register_reset", False, False, True),
            ("register_reset_without_nmi", False, False, False),
            ("auto_nmi", True, True, True),
            ("auto_reset", True, False, True),
        )
        with tempfile.TemporaryDirectory(prefix="wdt-test-") as temp:
            for (per_core, core), checks, mode in itertools.product(
                    ((1, 0), (1, 1), (0, 0)), (0, 1), modes):
                name, auto, nmi, register_nmi = mode
                with self.subTest(per_core=per_core, core=core, checks=checks, mode=name):
                    defines = configuration(per_core, core, checks, auto, nmi, register_nmi)
                    binary = Path(temp) / "wdt"
                    self.compile(binary, PRODUCTION, defines)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("production WDT behavior passed", result.stdout)

    def test_legacy_executable_sections_match_pristine_head(self):
        pristine = subprocess.run(
            ["git", "-C", str(BASELINE), "show", "HEAD:ra/fsp/src/r_wdt/r_wdt.c"],
            capture_output=True, timeout=10)
        self.assertEqual(pristine.returncode, 0, pristine.stderr.decode())
        self.assertIn(b"fsp_err_t R_WDT_Open", pristine.stdout)
        with tempfile.TemporaryDirectory(prefix="wdt-legacy-") as temp:
            directory = Path(temp)
            original = directory / "pristine.c"
            original.write_bytes(pristine.stdout)
            for checks, (auto, nmi, register_nmi) in itertools.product(
                    (0, 1), ((False, True, True), (False, False, True),
                             (False, False, False), (True, True, True), (True, False, True))):
                with self.subTest(checks=checks, auto=auto, nmi=nmi, register_nmi=register_nmi):
                    defines = configuration(0, 0, checks, auto, nmi, register_nmi)
                    before = directory / "before.o"
                    after = directory / "after.o"
                    self.compile(before, original, defines, object_only=True)
                    self.compile(after, PRODUCTION, defines, object_only=True)
                    self.assertEqual(executable_sections(before), executable_sections(after),
                                     "Legacy r_wdt executable sections changed from pristine FSP 5.9 HEAD")


if __name__ == "__main__":
    unittest.main()
