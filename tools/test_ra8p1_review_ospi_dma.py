"""OSPI008..012: default tests require and execute the applied canonical repair.

While production is frozen, RA8P1_OSPI_DMA_STAGING=1 explicitly permits tests
of the proposal on disposable copies. A staging pass is NOT an applied pass.

HM17.2.19 p756: channel base 0x4000a000/0x5000a000 + 0x40*n, DMBWR +0x30,
8-bit access, channels 0..7, DMAST=0 OR DTE=0 at each write. HM17.4.1 p786
supplies normal-transfer completion semantics. Whole production OSPI and DMAC
TUs and real transfer APIs execute with redirected volatile MMIO. Canonical
headers supply types/bases; independent numeric fixture assertions supply the
oracle. This is controlled host/ARM-compile evidence, not e2/HIL or flash data.
No production, metadata, generated file or installed artifact is modified.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

from tools.ra8p1.regression import readonly_sections
from tools.test_ra8p1_review_peripheral_capabilities import HEADERS, instrument, prepare, run

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
SOURCE = FSP / "src/r_ospi_b/r_ospi_b.c"
DMA_SOURCE = FSP / "src/r_dmac/r_dmac.c"
FIX = ROOT / "tools/ra8p1/review_ospi_dma"
PATCH = FIX / "ospi008.patch"


def versions(source, staging=False):
    """Exact line-position application of this owning-file proposal only; no fuzzy matching."""
    patch = PATCH.read_text().splitlines(keepends=True)
    assert patch[:2] == ["--- a/baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c\n",
                         "+++ b/baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c\n"]
    hunks = []
    for line in patch[2:]:
        if line.startswith("@@"):
            match = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", line)
            assert match, "Unexpected OSPI DMA hunk header"
            old_at, old_count, new_at, new_count = map(int, match.groups())
            hunks.append((old_at - 1, new_at - 1, old_count, new_count, [], []))
        else:
            assert hunks and line[0] in " +-", "Unexpected OSPI DMA patch record"
            content = line[1:].replace("\n", "\r\n") if b"\r\n" in source else line[1:]
            if line[0] in " -":
                hunks[-1][4].append(content.encode())
            if line[0] in " +":
                hunks[-1][5].append(content.encode())
    assert hunks
    for _, _, oc, nc, old, new in hunks:
        assert (len(old), len(new)) == (oc, nc)
    lines = source.splitlines(keepends=True)
    applied = all(lines[na:na + nc] == new for _, na, _, nc, _, new in hunks)
    if not applied and not staging:
        raise AssertionError("Canonical OSPI008..012 repair is not applied; staging-only evidence requires RA8P1_OSPI_DMA_STAGING=1")
    before = list(lines)
    if applied:
        for _, na, _, nc, old, new in reversed(hunks):
            assert before[na:na + nc] == new
            before[na:na + nc] = old
    after = list(before)
    for oa, _, oc, _, old, new in reversed(hunks):
        assert after[oa:oa + oc] == old, "Owning source does not exactly match the proposal"
        after[oa:oa + oc] = new
    if applied:
        assert after == lines  # Normal invocations execute actual canonical bytes, not a repair.
    return b"".join(before), b"".join(after), hunks


def dma_registers(folder, device):
    text = (FSP / "src/bsp/cmsis/Device/RENESAS/Include" / HEADERS[device]).read_text()
    declarations = ["#define BASE_NS_OFFSET (REVIEW_NONSECURE ? 0x10000000UL : 0UL)"]
    for name in ("R_DMAC0", "R_DMA", "R_ICU"):
        closing = "} " + name + "_Type;"
        end = text.index(closing) + len(closing)
        declarations.append(text[text.rfind("typedef struct", 0, end):end])
        declarations.extend(re.findall(r"^[ \t]*#define " + name + r"_\w+_(?:Msk|Pos)\b[^\n]*", text, re.M))
    pattern = r"^[ \t]*#define R_(?:DMAC[01]|DMA|ICU)(?:_(?:S|NS))?(?:_BASE)?[ \t]+[^\n]*"
    declarations.extend(re.findall(pattern, text, re.M))
    (folder / "dma_registers.h").write_text("\n".join(declarations) + "\n")


def instrument_dma(ir):
    # transfer_info_t also has volatile host pointer fields; preserve their reads/writes.
    reads = re.compile(r"^(\s*)(%[\w.]+) = load volatile ptr, ptr (.*?), align \d+.*$", re.M)
    writes = re.compile(r"^(\s*)store volatile ptr (.*?), ptr (.*?), align \d+.*$", re.M)
    ir = reads.sub(lambda m: f"{m[1]}{m[2]} = call ptr @review_readptr(ptr {m[3]})", ir)
    ir = writes.sub(lambda m: f"{m[1]}call void @review_writeptr(ptr {m[3]}, ptr {m[2]})", ir)
    return instrument(ir) + "\ndeclare ptr @review_readptr(ptr)\ndeclare void @review_writeptr(ptr, ptr)\n"


class OspiDmaReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        cls.arm = os.environ.get("RA8P1_ARM_GCC")
        db = ROOT / "validation/ra8p1/projects/wdt/Debug/compile_commands.json"
        if not cls.arm and db.is_file():
            cls.arm = shlex.split(json.loads(db.read_text())[0]["command"])[0]
        cls.arm = cls.arm or shutil.which("arm-none-eabi-gcc")
        if not cls.cc or not cls.arm:
            raise RuntimeError("Clang and original ARM GNU toolchain required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-ospi-dma-staged-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        cls.snapshot = SOURCE.read_bytes()
        cls.staging = os.environ.get("RA8P1_OSPI_DMA_STAGING") == "1"
        cls.before, cls.after, cls.hunks = versions(cls.snapshot, cls.staging)
        cls.source_hash = hashlib.sha256(cls.snapshot).hexdigest()
        cls.dma_hash = hashlib.sha256(DMA_SOURCE.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != cls.source_hash:
            raise AssertionError("Canonical OSPI source changed during staging verification")
        if hashlib.sha256(DMA_SOURCE.read_bytes()).hexdigest() != cls.dma_hash:
            raise AssertionError("Canonical DMAC source changed during staging verification")

    def flags(self, folder, core=0, checks=1, nonsecure=0, device="ra8p1", enabled=1):
        flags = prepare(folder, device)
        flags[flags.index("-include") + 1] = str(FIX / "bsp_api.h")
        dma_registers(folder, device)
        cfg = folder / "r_ospi_b_cfg.h"
        cfg.write_text(cfg.read_text().replace("DMAC_SUPPORT_ENABLE 0", f"DMAC_SUPPORT_ENABLE {enabled}"))
        (folder / "r_dmac_cfg.h").write_text("#define DMAC_CFG_PARAM_CHECKING_ENABLE CHECKS\n")
        return flags + [f"-DBSP_CFG_CPU_CORE={core}", f"-DCHECKS={checks}",
                        f"-DREVIEW_NONSECURE={nonsecure}", "-DPROTECT=0", "-DBYPASS=0"]

    def runtime(self, tag, source, core=0, checks=1, nonsecure=0):
        folder = self.tmp / tag
        folder.mkdir()
        flags = self.flags(folder, core, checks, nonsecure)
        ospi = folder / "r_ospi_b.c"
        ospi.write_bytes(source)
        objects = []
        for src in (ospi, DMA_SOURCE):
            ir = run([self.cc, *flags, "-O0", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                      "-S", "-emit-llvm", src, "-o", "-"])
            output = folder / (src.stem + ".ll")
            output.write_text(instrument_dma(ir))
            objects.append(output)
        binary = folder / "fixture"
        run([self.cc, *flags, "-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all",
             *objects, FIX / "fixture.c", "-o", binary])
        return binary

    def test_staged_patch_is_minimal_original_legacy_expression_and_all_other_bytes_preserved(self):
        self.assertNotEqual(self.before, self.after)
        removed, added = self.before.splitlines(keepends=True), self.after.splitlines(keepends=True)
        for oa, na, oc, nc, old, new in reversed(self.hunks):
            self.assertEqual(removed[oa:oa + oc], old)
            self.assertEqual(added[na:na + nc], new)
            del removed[oa:oa + oc]
            del added[na:na + nc]
        self.assertEqual(removed, added)
        legacy = b"    R_DMAC0_Type              * p_dma_reg     = R_DMAC0 + (sizeof(R_DMAC0_Type) * p_dmac_extend->channel);"
        self.assertEqual(self.after.count(legacy), 1)
        if not self.staging:
            self.assertEqual(self.after, self.snapshot)
        # Check patch syntax/application with the real utility, always inside a temporary tree.
        tree = self.tmp / "patch-utility"
        destination = tree / "baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(self.before)
        run(["patch", "--batch", "-p1", "-i", PATCH], cwd=tree)
        self.assertEqual(destination.read_bytes(), self.after)

    def test_staged_complete_write_path_all_channels_cores_checks_security_views_and_dmbwr_state(self):
        for core, checks, ns in itertools.product((0, 1), repeat=3):
            with self.subTest(core=core, checks=checks, nonsecure=ns):
                binary = self.runtime(f"fixed-{core}-{checks}-{ns}", self.after, core, checks, ns)
                self.assertIn("OSPI DMA cases passed", run([binary]))

    def test_failing_before_proof_nonzero_channel_reaches_wrong_dmbwr(self):
        for core, checks, ns in itertools.product((0, 1), repeat=3):
            with self.subTest(core=core, checks=checks, nonsecure=ns):
                binary = self.runtime(f"before-{core}-{checks}-{ns}", self.before, core, checks, ns)
                # Channel zero is an independent passing control for the original defect.
                self.assertIn("OSPI DMA cases passed", run([binary, "0"]))
                result = subprocess.run([str(binary), "1"], capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DMBWR address mismatch", result.stderr)
                for mode, diagnostic in (
                    ("length65536", "oversize DMA accepted" if checks else "DMA length narrowed"),
                    ("length65537", "DMA length narrowed"),
                    ("wren", "WREN error ignored"), ("open-error", "lower Open error ignored"),
                    ("foreign", "lower Open error ignored"),
                    ("reconfigure", "BWE left enabled after DMA failure"),
                    ("start", "BWE left enabled after DMA failure"),
                    ("info", "BWE left enabled after DMA failure"),
                    ("abort", "failed cleanup did not retain recovery state"),
                ):
                    with self.subTest(boundary=mode):
                        result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
                        self.assertNotEqual(result.returncode, 0, "Original DMA defect passed the independent oracle")
                        self.assertIn(diagnostic, result.stderr)

    def test_default_requires_canonical_repair_never_auto_repairs_and_exact_patch_roundtrips(self):
        with self.assertRaisesRegex(AssertionError, "Canonical OSPI008..012 repair is not applied"):
            versions(self.before)
        self.assertEqual(versions(self.after)[1], self.after)
        self.assertEqual(versions(self.after)[0], self.before)
        # No fuzzy or partial application, including when explicit staging is enabled.
        corrupt = self.before.replace(b"#define OSPI_B_PRV_OPEN                   (0x78535049U)",
                                      b"#define OSPI_B_PRV_OPEN                   (0x78535048U)", 1)
        with self.assertRaisesRegex(AssertionError, "does not exactly match"):
            versions(corrupt, staging=True)

    def test_quiescence_requires_actual_dte_and_act_readbacks_not_just_disable_success(self):
        for name, old, mode, diagnostic in (
            ("dte", b"(0U != (p_dma_reg->DMCNT & R_DMAC0_DMCNT_DTE_Msk))", "abort-dte", "DMAST=1 and DTE=1"),
            ("act", b"(0U != (p_dma_reg->DMSTS & R_DMAC0_DMSTS_ACT_Msk))", "abort-act", "failed cleanup did not retain recovery state"),
        ):
            self.assertEqual(self.after.count(old), 1)
            binary = self.runtime("no-" + name + "-readback", self.after.replace(old, b"false"))
            result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(diagnostic, result.stderr)

    def test_missing_channel_bound_is_detected_before_any_dma_write(self):
        guard = (b"    FSP_ERROR_RETURN(p_dmac_extend->channel < BSP_FEATURE_DMAC_MAX_CHANNEL, "
                 b"FSP_ERR_IP_CHANNEL_NOT_PRESENT);")
        self.assertEqual(self.after.count(guard), 3)
        at = self.after.index(guard, self.after.index(b"fsp_err_t R_OSPI_B_Write ("))
        no_bound = self.after[:at] + self.after[at:].replace(guard, b"", 1)
        binary = self.runtime("no-bound", no_bound)
        result = subprocess.run([str(binary), "invalid"], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DMBWR address mismatch", result.stderr)

    def test_setting_condition_oracle_detects_externally_pre_enabled_channel(self):
        binary = self.runtime("pre-enabled", self.after)
        result = subprocess.run([str(binary), "pre-enabled"], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DMBWR setting condition violated: DMAST=1 and DTE=1", result.stderr)

    def test_staged_whole_ospi_and_dmac_compile_both_cores_checks_security_views(self):
        for core, checks, ns in itertools.product((0, 1), repeat=3):
            folder = self.tmp / f"arm-{core}-{checks}-{ns}"
            folder.mkdir()
            flags = self.flags(folder, core, checks, ns)
            flags += ["-mcpu=" + ("cortex-m33" if core else "cortex-m85+nopacbti"), "-mthumb", "-O2"]
            source = folder / "r_ospi_b.c"
            source.write_bytes(self.after)
            for src in (source, DMA_SOURCE):
                with self.subTest(core=core, checks=checks, nonsecure=ns, driver=src.stem):
                    obj = folder / (src.stem + ".o")
                    run([self.arm, *flags, "-c", src, "-o", obj])
                    self.assertTrue(readonly_sections(obj.read_bytes()))

    def test_all_32_legacy_instance_control_layouts_remain_original_arm_abi(self):
        header = FSP / "inc/instances/r_ospi_b.h"
        original = subprocess.check_output(["git", "-C", str(ROOT / "baseline"), "show",
                                            "HEAD:ra/fsp/inc/instances/r_ospi_b.h"])
        self.assertEqual(header.read_bytes(), original)
        devices = sorted(p.parent for p in (FSP / "src/bsp/mcu").glob("*/bsp_feature.h")
                         if p.parent.name != "ra8p1")
        self.assertEqual(len(devices), 32)
        reference = None
        for device, enabled in itertools.product(devices, (0, 1)):
            folder = self.tmp / f"layout-{device.name}-{enabled}"
            folder.mkdir()
            flags = prepare(folder, "ra8m1")
            flags[flags.index("-I" + str(FSP / "src/bsp/mcu/ra8m1"))] = "-I" + str(device)
            cfg = folder / "r_ospi_b_cfg.h"
            cfg.write_text(cfg.read_text().replace("DMAC_SUPPORT_ENABLE 0", f"DMAC_SUPPORT_ENABLE {enabled}"))
            source = folder / "layout.c"
            fields = ("p_cfg", "open", "spi_protocol", "channel", "p_cmd_set", "p_reg")
            source.write_text('#include "r_ospi_b.h"\n'
                              '_Static_assert(BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP == 0, "legacy branch");\n'
                              '_Static_assert(sizeof(ospi_b_instance_ctrl_t) == 20, "original GNU ARM control size");\n'
                              '_Static_assert(_Alignof(ospi_b_instance_ctrl_t) == 4, "original ARM alignment");\n'
                              + "".join(f'_Static_assert(offsetof(ospi_b_instance_ctrl_t, {f}) == {offset}, "original offset");\n'
                                        for f, offset in zip(fields, (0, 4, 8, 10, 12, 16)))
                              + 'const unsigned layout[] = { sizeof(ospi_b_instance_ctrl_t), '
                              + ", ".join(f"offsetof(ospi_b_instance_ctrl_t, {f})" for f in fields) + ' };\n')
            obj = folder / "layout.o"
            run([self.arm, *flags, "-DCHECKS=1", "-mcpu=cortex-m33", "-mthumb", "-O2", "-c", source, "-o", obj])
            layout = readonly_sections(obj.read_bytes())
            self.assertTrue(layout)
            if reference is None:
                reference = layout
            with self.subTest(device=device.name, dma=enabled):
                self.assertEqual(reference, layout)

    def test_legacy_and_dma_disabled_preprocessed_executable_constant_relocation_parity(self):
        for device, checks, ns, enabled in itertools.product(("ra8m1", "ra8p1"), (0, 1), (0, 1), (0, 1)):
            if device == "ra8p1" and enabled:
                continue
            folder = self.tmp / f"parity-{device}-{checks}-{ns}-{enabled}"
            folder.mkdir()
            flags = self.flags(folder, 0, checks, ns, device, enabled)
            flags += ["-mcpu=cortex-m85+nopacbti", "-mthumb", "-O2"]
            code, binary = [], []
            for name, text in (("before", self.before), ("after", self.after)):
                src = folder / (name + ".c")
                src.write_bytes(text)
                code.append(re.sub(r"\s+", " ", run([self.arm, *flags, "-E", "-P", src])))
                obj = folder / (name + ".o")
                run([self.arm, *flags, "-c", src, "-o", obj])
                binary.append(readonly_sections(obj.read_bytes()))
            with self.subTest(device=device, checks=checks, nonsecure=ns, dma=enabled):
                self.assertEqual(*code)
                self.assertTrue(binary[0])
                self.assertEqual(*binary)


if __name__ == "__main__":
    unittest.main()
