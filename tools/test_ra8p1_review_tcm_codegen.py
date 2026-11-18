"""DUAL-003: inspect real GNU 13.2.1 CPU1 system.c objects, without e2 or mocks.

Uses the existing CPU1 compilation database and its generated headers verbatim.
RA8P1 HM Rev.1.30 2.17.1.1 Table 2.37 pp191-192 specifies the two
CPU1-local scrub windows: 0..0xffff and 0x20000000..0x2000ffff.
Set RA8P1_TCM_CODEGEN_EVIDENCE to retain objects, disassembly and commands.
These checks qualify emitted instructions, not C portability or silicon boot.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c"
DATABASE = ROOT / "validation/ra8p1/projects/cpu1/Debug/compile_commands.json"
LEVELS = ("-O0", "-Og", "-O1", "-O2", "-O3", "-Os")

# Instruction-level oracles are deliberately specific to this qualified compiler.
# Branch operands name instruction indices within the scrub block, not source labels.
LOOPS = {
    "-O0": """nop
movs r3, #0
str r3, [r7, #12]
b.n @15
ldr r3, [r7, #12]
movs r2, #0
str r2, [r3, #0]
ldr r3, [r7, #12]
add.w r3, r3, #536870912
mov r2, r3
movs r3, #0
str r3, [r2, #0]
ldr r3, [r7, #12]
adds r3, #4
str r3, [r7, #12]
ldr r3, [r7, #12]
cmp.w r3, #65536
bcc.n @4""",
    "-Og": """movs r3, #0
b.n @7
movs r2, #0
str r2, [r3, #0]
add.w r1, r3, #536870912
str r2, [r1, #0]
adds r3, #4
cmp.w r3, #65536
bcc.n @2""",
    "-O1": """movs r3, #0
mov r2, r3
str r2, [r3, #0]
add.w r1, r3, #536870912
str r2, [r1, #0]
adds r3, #4
cmp.w r3, #65536
bne.n @2""",
    "-O2": """movs r3, #0
mov r2, r3
str r2, [r3, #0]
add.w r1, r3, #536870912
adds r3, #4
cmp.w r3, #65536
str r2, [r1, #0]
bne.n @2""",
}
LOOPS["-O3"] = LOOPS["-Os"] = LOOPS["-O2"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd):
    result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        raise AssertionError(shlex.join(list(map(str, command))) + "\n" + result.stdout + result.stderr)
    return result


def section(disassembly, name):
    match = re.search(r"(?ms)^Disassembly of section \.text\." + re.escape(name)
                      + r":\n(.*?)(?=^Disassembly of section |\Z)", disassembly)
    if match is None:
        raise AssertionError("Missing emitted section: " + name)
    return match[1]


def scrub_block(disassembly, level):
    owner = "bsp_init_ctcm" if level in ("-O0", "-Og") else "SystemInit"
    text = section(disassembly, owner)
    instructions = []
    for match in re.finditer(r"(?m)^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+"
                             r"([a-z][a-z0-9.]*)[ \t]*([^\n]*)", text):
        address, opcode, operands = match.groups()
        operands = " ".join(operands.split("@")[0].split())
        instructions.append((int(address, 16), opcode, operands))
    barriers = [i for i, (_, opcode, _) in enumerate(instructions) if opcode == "dmb"]
    if len(barriers) < 3:
        raise AssertionError("Scrub pre/post barriers disappeared")
    block = instructions[barriers[1] + 1:barriers[2]]
    positions = {address: i for i, (address, _, _) in enumerate(block)}
    normalized = []
    for _, opcode, operands in block:
        if opcode in ("b.n", "bcc.n", "bne.n"):
            target = int(operands.split()[0], 16)
            if target not in positions:
                raise AssertionError("Scrub branch leaves the finite loop")
            operands = "@" + str(positions[target])
        normalized.append(opcode + (" " + operands if operands else ""))
    return "\n".join(normalized)


def inspect(disassembly, level):
    if re.search(r"\b(?:udf|bkpt)\b", disassembly):
        raise AssertionError("Unexpected emitted trap")
    actual = scrub_block(disassembly, level)
    if actual != LOOPS[level]:
        raise AssertionError("Scrub instructions differ from the qualified finite two-window loop:\n" + actual)
    startup = section(disassembly, "SystemInit")
    for symbol in ("bsp_clock_freq_var_init", "SystemCoreClockUpdate", "bsp_irq_cfg", "bsp_init"):
        if not re.search(r"R_ARM_THM_(?:CALL|JUMP24)\s+" + symbol + r"\b", startup):
            raise AssertionError("Later initialization disappeared: " + symbol)
    if len(re.findall(r"R_ARM_THM_CALL\s+R_BSP_WarmStart\b", startup)) != 3:
        raise AssertionError("Later warm callbacks disappeared")
    if level in ("-O0", "-Og"):
        if not re.search(r"R_ARM_THM_CALL\s+bsp_init_ctcm\b", startup):
            raise AssertionError("Startup no longer calls the out-of-line scrub")
        if not re.search(r"\b(?:bx\s+lr|pop\s+\{[^}]*pc\})", section(disassembly, "bsp_init_ctcm")):
            raise AssertionError("Out-of-line scrub no longer returns")
    return actual


class TcmCodegenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DATABASE.is_file():
            raise unittest.SkipTest("Real generated CPU1 compile_commands.json is required")
        entry, = [e for e in json.loads(DATABASE.read_text()) if e["file"].endswith("/system.c")]
        original = shlex.split(entry["command"])
        compiler = Path(original[0])
        if not compiler.is_file():
            raise unittest.SkipTest("Recorded original GNU toolchain is unavailable: " + str(compiler))
        cls.cwd = Path(entry["directory"])
        version = run([compiler, "--version"], cls.cwd).stdout
        if "13.2.1 20231009" not in version:
            raise AssertionError("DUAL-003 requires the recorded original GNU 13.2.1 compiler")
        for flag in ("-mcpu=cortex-m33", "-mthumb", "-mfloat-abi=hard", "-mfpu=fpv5-sp-d16",
                     "-D_RA_CORE=CM33", "-D_RA_PRIMARY_CORE=CM85", "-D_RA_ORDINAL=2", "-O2"):
            if flag not in original:
                raise AssertionError("CPU1 BSP flag changed: " + flag)
        cls.temp = tempfile.TemporaryDirectory(prefix="ra8p1-tcm-codegen-")
        cls.addClassCleanup(cls.temp.cleanup)
        output = os.environ.get("RA8P1_TCM_CODEGEN_EVIDENCE")
        cls.output = Path(output).resolve() if output else Path(cls.temp.name)
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.results = {}
        records = []
        for level in LEVELS:
            obj = cls.output / (level[1:] + ".o")
            command = [level if token == "-O2" else token for token in original]
            command[command.index(entry["file"])] = str(SOURCE)
            command[command.index("-o") + 1] = str(obj)
            compiled = run(command, cls.cwd)
            dump = [str(compiler.with_name("arm-none-eabi-objdump")), "-dr", str(obj)]
            disassembly = run(dump, cls.cwd).stdout
            (cls.output / (level[1:] + ".dis")).write_text(disassembly)
            cls.results[level] = disassembly
            records.append({"optimization": level, "command": shlex.join(command),
                            "objdump_command": shlex.join(dump), "diagnostics": compiled.stderr,
                            "object_sha256": sha256(obj)})
        flags = original.copy()
        del flags[flags.index("-o"):flags.index("-o") + 2]
        flags.remove("-c")
        flags[flags.index(entry["file"])] = str(SOURCE)
        macro_command = flags + ["-E", "-dM"]
        macros = run(macro_command, cls.cwd).stdout
        cls.macros = macros
        selected = "\n".join(line for line in macros.splitlines() if re.match(
            r"#define (?:BSP_(?:PRV_[CS]TCM|CFG_(?:CPU_CORE|C_RUNTIME_INIT|SKIP_INIT)|"
            r"FEATURE_BSP_HAS_CTCM|TZ_(?:NONSECURE_BUILD|CFG_SKIP_INIT))|__GNUC__)", line)) + "\n"
        (cls.output / "selected-macros.txt").write_text(selected)
        dependency_command = flags + ["-M", "-MT", "inputs"]
        dependencies = run(dependency_command, cls.cwd).stdout.split(":", 1)[1].replace("\\\n", " ")
        paths = sorted({(cls.cwd / p).resolve() for p in shlex.split(dependencies)})
        manifest = {"compiler_version": version, "compiler": str(compiler),
                    "compiler_sha256": sha256(compiler), "cwd": str(cls.cwd),
                    "source": str(SOURCE), "database": str(DATABASE),
                    "database_sha256": sha256(DATABASE), "original_entry": entry,
                    "macro_command": shlex.join(macro_command),
                    "dependency_command": shlex.join(dependency_command),
                    "inputs_sha256": {str(p): sha256(p) for p in paths}, "builds": records}
        (cls.output / "commands-and-inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def test_generated_cpu1_configuration_enables_actual_scrub_and_runtime_init(self):
        for definition in ("#define BSP_CFG_CPU_CORE (1)", "#define BSP_TZ_NONSECURE_BUILD (0)",
                           "#define BSP_CFG_C_RUNTIME_INIT ((1))",
                           "#define BSP_PRV_CTCM_BASE (0x00000000U)",
                           "#define BSP_PRV_STCM_BASE (0x20000000U)",
                           "#define BSP_PRV_CTCM_SIZE (0x10000U)"):
            self.assertIn(definition, self.macros)
        # The recorded bare-metal project leaves this undefined: #if treats it as 0.
        self.assertNotIn("#define BSP_CFG_SKIP_INIT ", self.macros)

    def test_full_source_real_cpu1_flags_all_optimization_levels(self):
        for level, disassembly in self.results.items():
            with self.subTest(optimization=level):
                inspect(disassembly, level)

    def test_codegen_oracle_rejects_trap_missing_store_spin_and_elided_init(self):
        disassembly = self.results["-O2"]
        changes = (("str\tr2, [r3, #0]", "udf\t#255"),
                   ("str\tr2, [r1, #0]", "nop"),
                   ("bne.n\t2a <SystemInit+0x2a>", "bne.n\t38 <SystemInit+0x38>"),
                   ("R_ARM_THM_CALL\tbsp_clock_freq_var_init", "R_ARM_THM_CALL\tremoved"))
        for before, after in changes:
            with self.subTest(mutation=before):
                self.assertIn(before, disassembly)
                with self.assertRaises(AssertionError):
                    inspect(disassembly.replace(before, after), "-O2")


if __name__ == "__main__":
    unittest.main()
