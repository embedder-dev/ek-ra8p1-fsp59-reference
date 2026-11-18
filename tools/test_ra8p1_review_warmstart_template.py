"""Compile the owning 5.9 entry template with production startup on the host.

Template substitutions are controlled fixtures, not an e2 generation or boot test.
The original release provides the independent legacy-output oracle.
"""
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from test_ra8p1_startup import function

ROOT = Path(__file__).resolve().parents[1]
BSP = ROOT / "baseline/ra/fsp/src/bsp"
MDF = ROOT / "baseline/module_descriptions/Renesas##Common##all##fsp_common####5.9.0.xml"
ENTRY = "./rtos[@id='_none']/thread[@id='_hal']/entry"
GUARD = b"#if !BSP_FEATURE_BSP_HAS_SECONDARY_CORE || (BSP_CFG_CPU_CORE == 0)\r\n"


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, command))}\n{result.stdout}{result.stderr}")
    return result.stdout


class WarmStartTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("cc")
        if cls.compiler is None:
            raise RuntimeError("Native compiler required")
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != (
                    "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363"):
                raise AssertionError("Original FSP 5.9 release checksum mismatch")
        with zipfile.ZipFile(archive) as release:
            with zipfile.ZipFile(io.BytesIO(release.read(
                    "internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack"))) as pack:
                cls.stock = pack.read(".module_descriptions/" + MDF.name)
                support = ET.fromstring(pack.read("toolingSupport.xml"))
                if support.find("file[@supportType='Modules'][.='.module_descriptions/" + MDF.name + "']") is None:
                    raise AssertionError("Original warm-start owner is not registered")
        cls.current = MDF.read_bytes()
        cls.legacy = sorted(p.parent.name for p in (BSP / "mcu").glob("*/bsp_feature.h")
                            if p.parent.name != "ra8p1")

    def test_only_shared_post_c_body_changes_and_crlf_is_preserved(self):
        self.assertEqual(self.current.count(b"\n"), self.current.count(b"\r\n"))
        opening = b"        /* Configure pins. */\r\n"
        closing = b"        R_BSP_SdramInit(true);\r\n#endif\r\n"
        self.assertEqual(1, self.stock.count(opening))
        self.assertEqual(1, self.stock.count(closing))
        expected = self.stock.replace(opening, GUARD + opening).replace(closing, closing + b"#endif\r\n")
        self.assertEqual(expected, self.current)

    def substitute(self, stock):
        entry = ET.fromstring(self.stock if stock else self.current).findtext(ENTRY)
        self.assertIsNotNone(entry)
        for token, value in (("IOPORT_CFG_CTRL", "g_ioport_ctrl"), ("IOPORT_CFG_NAME", "g_bsp_pin_cfg")):
            self.assertEqual(1, entry.count(token))
            entry = entry.replace(token, value)
        self.assertNotIn("IOPORT_CFG_", entry)
        return entry

    def fixture(self):
        source = (ROOT / "tools/ra8p1/review_dual_cache/fixture.c").read_text()
        source = source.replace("/* CACHE FUNCTIONS */", "\n".join(
            function(BSP / "mcu/all/bsp_common.h", name)
            for name in ("R_BSP_FlashCacheDisable", "R_BSP_FlashCacheEnable")))
        source = source.replace("/* SYSTEM FUNCTION */", function(
            BSP / "cmsis/Device/RENESAS/Source/system.c", "SystemInit"))
        start = source.index("static void R_BSP_WarmStart(unsigned stage)")
        end = source.index("\n}", start) + len("\n}")
        source = source[:start] + r'''
typedef unsigned bsp_warm_start_event_t;
#define FSP_CPP_HEADER
#define FSP_CPP_FOOTER
static unsigned g_ioport_ctrl, g_bsp_pin_cfg;
static unsigned pin_opens, sdram_inits, user_hooks[3];
static struct { unsigned DFLCTL; } flash_lp;
#define R_FACI_LP (&flash_lp)
static void R_IOPORT_Open(unsigned * ctrl, unsigned const * cfg)
{
    assert(ctrl == &g_ioport_ctrl && cfg == &g_bsp_pin_cfg);
    assert(user_hooks[BSP_WARM_START_POST_C] == 1U);
    assert(pin_opens++ == 0U);
    event('p');
}
static void R_BSP_SdramInit(bool enable)
{
    assert(enable && pin_opens == 1U);
    assert(sdram_inits++ == 0U);
    event('s');
}
#define R_BSP_WarmStart default_warm_start
#include "hal_entry.c"
#undef R_BSP_WarmStart
static void R_BSP_WarmStart(unsigned stage)
{
    observe_cache();
    assert(stage <= BSP_WARM_START_POST_C);
    assert(pin_opens == 0U && sdram_inits == 0U);
    assert(user_hooks[stage]++ == 0U);
    event("RPC"[stage]);
    default_warm_start(stage);
}
''' + source[end:]
        source = source[:source.index("int main(")] + r'''
int main(void)
{
    reset_model(false);
    SystemInit();
    observe_cache();
    for (unsigned stage = 0; stage < 3U; stage++)
    {
        assert(user_hooks[stage] == 1U);
    }
    assert(pin_opens == EXPECT_SHARED);
    assert(sdram_inits == (EXPECT_SHARED && BSP_CFG_SDRAM_ENABLED));
    assert(flash_lp.DFLCTL == (BSP_FEATURE_FLASH_LP_VERSION != 0));
    puts(trace);
    return 0;
}
'''
        return source

    def command(self, folder, device, core, sdram, shared):
        return [self.compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-Wno-unused-variable", "-Wno-pointer-to-int-cast",
                "-D__CLANG_TIDY__", "-DTEST_SYSTEM=1", "-DBSP_CFG_XTAL_HZ=24000000",
                "-DBSP_CFG_SKIP_INIT=0", "-DBSP_TZ_CFG_SKIP_INIT=0",
                f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_CFG_SDRAM_ENABLED={sdram}",
                f"-DEXPECT_SHARED={shared}", "-I", BSP / "mcu" / device, "-I", folder]

    def test_both_core_user_hooks_and_default_shared_ownership(self):
        with tempfile.TemporaryDirectory(prefix="warmstart-template-") as temp:
            folder = Path(temp)
            source, binary = folder / "fixture.c", folder / "fixture"
            source.write_text(self.fixture())
            (folder / "hal_data.h").write_text("")
            for core in (0, 1):
                for sdram in (0, 1):
                    # The original template is the negative control: CPU1 replays shared setup.
                    for stock in (True, False):
                        with self.subTest(core=core, sdram=sdram, stock=stock):
                            (folder / "hal_entry.c").write_text(self.substitute(stock))
                            shared = int(stock or core == 0)
                            command = self.command(folder, "ra8p1", core, sdram, shared)
                            run(command + ["-fsanitize=undefined", source, "-o", binary])
                            trace = run([binary]).strip()
                            self.assertEqual("RPC", "".join(c for c in trace if c in "RPC"))
                            self.assertEqual("p" * shared + "s" * (shared and sdram),
                                             "".join(c for c in trace if c in "ps"))
                            if shared:
                                self.assertLess(trace.index("C"), trace.index("p"))

    def test_all_legacy_preprocessed_executable_and_runtime_parity(self):
        self.assertEqual(32, len(self.legacy))
        with tempfile.TemporaryDirectory(prefix="warmstart-legacy-") as temp:
            folder = Path(temp)
            source, binary, obj = folder / "fixture.c", folder / "fixture", folder / "fixture.o"
            source.write_text(self.fixture())
            (folder / "hal_data.h").write_text("")
            for device in self.legacy:
                for sdram in (0, 1):
                    with self.subTest(device=device, sdram=sdram):
                        results = []
                        for stock in (True, False):
                            (folder / "hal_entry.c").write_text(self.substitute(stock))
                            command = self.command(folder, device, 0, sdram, 1)
                            tokens = run(command + ["-E", "-P", source])
                            run(command + ["-O2", "-g0", "-c", source, "-o", obj])
                            code = obj.read_bytes()
                            run(command + ["-fsanitize=undefined", source, "-o", binary])
                            results.append((tokens, code, run([binary])))
                        self.assertEqual(*results)


if __name__ == "__main__":
    unittest.main()
