"""Read-only candidate verification fixtures; no IDE or hardware access."""
import io
import json
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from fsp_manifest import digest
from ra8p1 import verify_candidate as verifier


PACK = "Renesas.RA_mcu_ra8p1.5.9.0.pack"
SOURCE = "ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c"
ALIAS = "ra~1/Source/system.c"
MDF = ".module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml"
PDSC = "Renesas.RA_mcu_ra8p1.pdsc"


def contract():
    # Explicit fixtures from HM 5.1 p.239 and the caller's current memory contract.
    return {"part": "R7KA8P1KFLCAC", "fsp": "5.9.0", "address_bits": 32,
            "physical": {"MRAM": {"start": "0x02000000", "size": "0x100000", "ns_start": "0x12000000"},
                         "SRAM": {"start": "0x22000000", "size": "0x1a0000", "ns_start": "0x32000000"}},
            "cores": {
                "CM85": {"compiler": "cortex-m85", "debugger": "R7KA8P1KF_CPU0",
                         "compile_flags": {"mcpu": "cortex-m85+nopacbti", "mfpu": "fpv5-d16", "mfloat-abi": "hard"},
                         "boot": {"vector_address": "0x02000000", "vector_alignment": 128},
                         "MRAM": {"start": "0x02000000", "size": "0x80000"},
                         "SRAM": {"start": "0x22000000", "size": "0xd0000"},
                         "ITCM": {"start": 0, "size": "0x20000", "bus_alias": "0x28000000"},
                         "DTCM": {"start": "0x20000000", "size": "0x20000", "bus_alias": "0x28020000"}},
                "CM33": {"compiler": "cortex-m33", "debugger": "R7KA8P1KF_CPU1",
                         "compile_flags": {"mcpu": "cortex-m33", "mfpu": "fpv5-sp-d16", "mfloat-abi": "hard"},
                         "boot": {"vector_address": "0x02080000", "vector_alignment": 128},
                         "MRAM": {"start": "0x02080000", "size": "0x80000"},
                         "SRAM": {"start": "0x220d0000", "size": "0xd0000"},
                         "ITCM": {"start": 0, "size": "0x10000", "bus_alias": "0x2a000000"},
                         "DTCM": {"start": "0x20000000", "size": "0x10000", "bus_alias": "0x2a010000"}}},
            "options": {".option_word": {"address": "0x02c9f040", "size": 4, "owner": "CM85"}}}


def elf_text(cpu="cortex-m85", physical=0x02000000, virtual=None, filesz=4, memsz=None, offset=0):
    virtual = physical if virtual is None else virtual
    memsz = filesz if memsz is None else memsz
    return (f'ELF Header:\n  Class: ELF32\n  Machine: ARM\n'
            f'  Tag_CPU_name: "{cpu}"\nProgram Headers:\n'
            f'  LOAD 0x{offset:x} 0x{virtual:x} 0x{physical:x} 0x{filesz:x} 0x{memsz:x} R E 0x1\n')


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()

    def ranges(self, **kwargs):
        return verifier.elf_ranges(elf_text(**kwargs), 4096, self.contract, "CM85")

    def test_region_exact_end_passes_and_one_byte_over_fails(self):
        self.assertEqual(self.ranges(physical=0x0207fffc), [(0x0207fffc, 0x02080000)])
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x0207fffd)
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x01ffffff)
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x02080000)

    def test_shared_sram_exact_physical_end_and_alias(self):
        text = elf_text(cpu="cortex-m33", physical=0x3219fffc)
        self.assertEqual(verifier.elf_ranges(text, 4096, self.contract, "CM33"),
                         [(0x2219fffc, 0x221a0000)])
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            verifier.elf_ranges(elf_text(cpu="cortex-m33", physical=0x3219fffd), 4096, self.contract, "CM33")

    def test_mram_and_sram_aliases_normalize(self):
        self.assertEqual(self.ranges(physical=0x12000000), [(0x02000000, 0x02000004)])
        self.assertEqual(self.ranges(physical=0x32000000), [(0x22000000, 0x22000004)])

    def test_overlap_through_alias_is_rejected_and_touching_is_allowed(self):
        left = self.ranges()
        self.contract["cores"]["CM33"]["MRAM"] = {"start": "0x02000000", "size": "0x80000"}
        right = verifier.elf_ranges(elf_text(cpu="cortex-m33", physical=0x12000000), 4096, self.contract, "CM33")
        with self.assertRaisesRegex(ValueError, "Physical overlap"):
            verifier.disjoint({"CM85": left, "CM33": right})
        verifier.disjoint({"CM85": [(1, 4)], "CM33": [(4, 8)]})

    def test_runtime_sram_alias_overlap_is_rejected_with_disjoint_load_images(self):
        self.contract["cores"]["CM33"]["SRAM"] = {"start": "0x22000000", "size": "0xd0000"}
        left = self.ranges(physical=0x02000000, virtual=0x22000000)
        right = verifier.elf_ranges(elf_text(cpu="cortex-m33", physical=0x02080000, virtual=0x32000000),
                                    4096, self.contract, "CM33")
        with self.assertRaisesRegex(ValueError, "Physical overlap"):
            verifier.disjoint({"CM85": left, "CM33": right})

    def test_local_tcm_windows_normalize_to_distinct_caller_bus_aliases(self):
        left = self.ranges(physical=0)
        right = verifier.elf_ranges(elf_text(cpu="cortex-m33", physical=0), 4096, self.contract, "CM33")
        self.assertEqual(left, [(0x28000000, 0x28000004)])
        self.assertEqual(right, [(0x2a000000, 0x2a000004)])
        verifier.disjoint({"CM85": left, "CM33": right})
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x20000)

    def test_missing_tcm_contract_is_not_silently_ignored(self):
        del self.contract["cores"]["CM85"]["ITCM"]
        with self.assertRaises(KeyError):
            self.ranges(physical=0)
        self.contract = contract()
        self.contract["cores"]["CM85"]["ITCM"]["size"] = 0
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0)

    def test_tcm_bus_alias_and_explicit_additional_alias(self):
        self.contract["cores"]["CM85"]["ITCM"]["aliases"] = [0x10000000]
        self.assertEqual(self.ranges(physical=0x10000000), self.ranges(physical=0x28000000, virtual=0))

    def test_allocation_cannot_exceed_physical_contract(self):
        self.contract["cores"]["CM85"]["MRAM"]["size"] = "0x100001"
        with self.assertRaisesRegex(ValueError, "outside physical MRAM"):
            self.ranges()

    def test_no_guessed_nonsecure_or_option_memory_aliases(self):
        del self.contract["physical"]["MRAM"]["ns_start"]
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x12000000)
        self.assertEqual(self.ranges(physical=0x02c9f040), [(0x02c9f040, 0x02c9f044)])
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x12c9f040)
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            verifier.elf_ranges(elf_text(cpu="cortex-m33", physical=0x02c9f040), 4096, self.contract, "CM33")

    def test_initialized_ram_checks_load_image_and_runtime_bss_separately(self):
        result = self.ranges(physical=0x0207fffc, virtual=0x22000000, filesz=4, memsz=16)
        self.assertEqual(result, [(0x0207fffc, 0x02080000), (0x22000000, 0x22000010)])
        with self.assertRaisesRegex(ValueError, "outside explicit"):
            self.ranges(physical=0x02000000, virtual=0x220cfffc, memsz=8)

    def test_bss_only_segment_is_checked_at_runtime_address(self):
        self.assertEqual(self.ranges(physical=0, virtual=0x22000000, filesz=0, memsz=32),
                         [(0x22000000, 0x22000020)])

    def test_arithmetic_invalid_sizes_and_file_bounds(self):
        for kwargs, message in (({"physical": 0xfffffffe, "filesz": 4}, "overflow"),
                                ({"filesz": 8, "memsz": 4}, "file size exceeds"),
                                ({"offset": 4095, "filesz": 4}, "beyond ELF file")):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                self.ranges(**kwargs)
        for value in (-1, True, "-4", 1.5, "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.number(value)
        self.assertEqual(verifier.interval(0xffffffff, 1, 1 << 32), (0xffffffff, 1 << 32))
        with self.assertRaises(ValueError):
            verifier.interval(1 << 32, 0, 1 << 32)

    def test_wrong_elf_cpu_architecture_and_missing_identity_fail(self):
        with self.assertRaisesRegex(ValueError, "Wrong ELF CPU"):
            self.ranges(cpu="cortex-m33")
        for text in (elf_text().replace("Machine: ARM", "Machine: AArch64"),
                     elf_text().replace("Class: ELF32", "Class: ELF64"),
                     elf_text().replace('  Tag_CPU_name: "cortex-m85"\n', "")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verifier.elf_ranges(text, 4096, self.contract, "CM85")

    def test_caller_elf_fpu_and_abi_attribute_policy_is_checked(self):
        self.contract["cores"]["CM85"]["elf_attributes"] = {
            "Tag_FP_arch": "FPv5/FP-D16 for ARMv8", "Tag_ABI_VFP_args": "VFP registers"}
        text = elf_text() + "  Tag_FP_arch: FPv5/FP-D16 for ARMv8\n  Tag_ABI_VFP_args: VFP registers\n"
        self.assertTrue(verifier.elf_ranges(text, 4096, self.contract, "CM85"))
        for wrong in (elf_text(), text.replace("VFP registers", "Base AAPCS"), text.replace("FPv5/FP-D16", "VFPv4")):
            with self.subTest(text=wrong), self.assertRaisesRegex(ValueError, "ELF attribute"):
                verifier.elf_ranges(wrong, 4096, self.contract, "CM85")

    def test_malformed_load_and_empty_elf_fail(self):
        for text in ("", "LOAD invalid", elf_text(filesz=0, memsz=0)):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verifier.elf_ranges(text, 4096, self.contract, "CM85")

    def test_empty_load_skips_only_mapping_congruence(self):
        empty = "  LOAD 0x4d4 0x0 0x0 0x0 0x0     0x1000\n"
        self.assertEqual(verifier.elf_ranges(elf_text() + empty, 4096, self.contract, "CM85"), self.ranges())
        for bad, message in ((empty.replace("0x0 0x0     ", "0x0 0x1     "), "alignment"),
                             (empty.replace("0x0 0x0     ", "0x1 0x1     "), "alignment"),
                             (empty.replace("0x0 0x0     ", "0x1 0x0     "), "file size exceeds"),
                             (empty.replace("0x4d4", "0x1001"), "beyond ELF file"),
                             (empty.replace("0x4d4", "0x100000000"), "overflow"),
                             (empty.replace("0x1000", "0x3"), "alignment"),
                             (empty.replace("0x4d4 0x0", "0x4d4 0x100000000"), "overflow"),
                             (empty.replace("0x0 0x0 0x0 0x0", "0x0 0x100000000 0x0 0x0"), "overflow")):
            with self.subTest(segment=bad), self.assertRaisesRegex(ValueError, message):
                verifier.elf_ranges(elf_text() + bad, 4096, self.contract, "CM85")

    def test_alignment_and_ambiguous_contract_fail(self):
        with self.assertRaisesRegex(ValueError, "alignment"):
            verifier.elf_ranges(elf_text().replace("0x1\n", "0x3\n"), 4096, self.contract, "CM85")
        self.contract["cores"]["CM85"]["DTCM"]["start"] = 0
        with self.assertRaisesRegex(ValueError, "Ambiguous address windows"):
            self.ranges()


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.cfg = contract()["cores"]["CM85"]
        self.path = self.project / "Debug/compile_commands.json"
        self.path.parent.mkdir()
        self.arguments = ["/tool chain/bin/arm-none-eabi-gcc", "-mthumb", "-mcpu=cortex-m85+nopacbti",
                          "-mfpu=fpv5-d16", "-mfloat-abi=hard", "-c", "source with spaces.c"]
        self.entry = {"directory": str(self.project), "file": "source with spaces.c", "arguments": self.arguments}

    def check(self, entries=None, compiler=None):
        self.path.write_text(json.dumps([self.entry] if entries is None else entries))
        return verifier.check_compile_commands(self.project, self.cfg, compiler=compiler)

    def test_arguments_and_quoted_command_both_cores(self):
        result = self.check()
        self.assertEqual(result["checked_entries"], 1)
        self.assertEqual(result["entries"][0]["flags"], self.cfg["compile_flags"])
        self.entry["command"] = shlex.join(self.entry.pop("arguments"))
        self.assertEqual(self.check()["checked_entries"], 1)
        self.cfg = contract()["cores"]["CM33"]
        self.entry["command"] = self.entry["command"].replace("cortex-m85+nopacbti", "cortex-m33").replace("fpv5-d16", "fpv5-sp-d16")
        self.assertEqual(self.check()["entries"][0]["flags"], self.cfg["compile_flags"])

    def test_every_entry_checked_despite_correct_configuration_identity(self):
        for index, wrong, flag in ((2, "-mcpu=cortex-m33", "mcpu"), (3, "-mfpu=fpv5-sp-d16", "mfpu"),
                                    (4, "-mfloat-abi=softfp", "mfloat-abi")):
            with self.subTest(flag=flag):
                arguments = self.arguments.copy()
                arguments[index] = wrong
                entry = {**self.entry, "file": "second.c", "arguments": arguments}
                with self.assertRaisesRegex(ValueError, "entry 1.*second.c"):
                    self.check([self.entry, entry])

    def test_missing_flags_conflicting_flags_and_wrong_executable_fail(self):
        for arguments in (["clang", *self.arguments[1:]], ["gcc", *self.arguments[1:]],
                          self.arguments[:3] + self.arguments[4:], self.arguments + ["-mcpu=cortex-m33"],
                          self.arguments + ["-mfloat-abi=soft"], self.arguments + ["-mfpu=auto"]):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, "Wrong"):
                self.check([{**self.entry, "arguments": arguments}])

    def test_response_files_and_target_overrides_are_not_silently_ignored(self):
        for flag in ("@options.rsp", "-march=armv7-m", "-Wa,-mcpu=cortex-m33", "-marm", "--specs=override.specs", "--"):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "Unsupported"):
                self.check([{**self.entry, "arguments": self.arguments + [flag]}])

    def test_only_noncompilation_linker_scripts_are_omitted_and_reported(self):
        script = {**self.entry, "file": "script/fsp.ld", "arguments": ["clang", "-I."]}
        result = self.check([self.entry, script])
        self.assertEqual(result["checked_entries"], 1)
        self.assertEqual(result["omitted_noncompilation_entries"][0]["file"], "script/fsp.ld")
        with self.assertRaisesRegex(ValueError, r"no C/C\+\+/assembly"):
            self.check([script])
        for suffix in (".c", ".C", ".cpp", ".cxx", ".cc", ".S", ".s", ".asm", ".h", ".unknown"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.check([self.entry, {**script, "file": "real" + suffix}])
        for arguments in (["clang", "-c", "script/fsp.ld"], ["clang", "-x", "c", "script/fsp.ld"]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.check([self.entry, {**script, "arguments": arguments}])

    def test_default_fpu_requires_explicit_policy_and_matching_trusted_compiler(self):
        self.entry["arguments"] = [arg for arg in self.arguments if not arg.startswith("-mfpu=")]
        trusted = self.arguments[0]
        with self.assertRaisesRegex(ValueError, "compiler -mfpu"):
            self.check(compiler=trusted)
        self.cfg["allow_default_fpu"] = True
        with self.assertRaisesRegex(ValueError, "trusted toolchain compiler"):
            self.check()
        with self.assertRaisesRegex(ValueError, "differs from trusted"):
            self.check(compiler="/different/bin/arm-none-eabi-gcc")

    def test_default_fpu_observed_macros_are_compared_and_cached_per_target(self):
        self.cfg["allow_default_fpu"] = True
        self.entry["arguments"] = [arg for arg in self.arguments if not arg.startswith("-mfpu=")]
        macros = {"__ARM_FP": 14, "__ARM_PCS_VFP": 1, "__SOFTFP__": 0}
        with patch.object(verifier, "probe_fp_macros", return_value=macros) as probe:
            result = self.check([self.entry, {**self.entry, "file": "second.cpp"}], compiler=self.arguments[0])
            self.assertEqual(probe.call_count, 2)
        item = result["entries"][0]
        self.assertIsNone(item["flags"]["mfpu"])
        self.assertEqual(item["effective_fpu"]["observed_macros"], macros)
        self.assertEqual(item["effective_fpu"]["reference_mfpu"], "fpv5-d16")
        self.assertNotIn("-mfpu=fpv5-d16", item["effective_fpu"]["target_flags"])
        self.assertIn("-mfpu=fpv5-d16", probe.call_args_list[1].args[1])
        for wrong in ({**macros, "__ARM_FP": 6}, {**macros, "__ARM_PCS_VFP": 0}, {**macros, "__SOFTFP__": 1}):
            with self.subTest(macros=wrong), patch.object(verifier, "probe_fp_macros", side_effect=[wrong, macros]):
                with self.assertRaisesRegex(ValueError, "default FPU/ABI mismatch"):
                    self.check(compiler=self.arguments[0])

    def test_default_policy_does_not_accept_explicit_wrong_fpu_or_nonboolean(self):
        self.cfg["allow_default_fpu"] = True
        self.entry["arguments"] = [arg.replace("fpv5-d16", "fpv5-sp-d16") for arg in self.arguments]
        with patch.object(verifier, "probe_fp_macros") as probe:
            with self.assertRaisesRegex(ValueError, "compiler -mfpu"):
                self.check(compiler=self.arguments[0])
            probe.assert_not_called()
        self.cfg["allow_default_fpu"] = "yes"
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            self.check()

    def test_probe_rejects_missing_fp_macros_diagnostics_and_nonzero_status(self):
        for result in (subprocess.CompletedProcess([], 0, "#define __ARM_PCS_VFP 1\n", ""),
                       subprocess.CompletedProcess([], 0, "#define __ARM_FP 14\n", "warning"),
                       subprocess.CompletedProcess([], 1, "", "invalid target")):
            with self.subTest(result=result), patch.object(verifier.subprocess, "run", return_value=result):
                with self.assertRaises(ValueError):
                    verifier.probe_fp_macros("arm-none-eabi-gcc", ["-mcpu=cortex-m85+nopacbti"])

    def test_missing_database_requires_explicit_fixture_opt_out(self):
        with self.assertRaisesRegex(ValueError, "Missing compile_commands"):
            verifier.check_compile_commands(self.project, self.cfg)
        self.cfg["legacy_fixture"] = {"skip_compile_commands": True}
        self.assertIn("skipped", verifier.check_compile_commands(self.project, self.cfg)["status"])
        self.cfg["legacy_fixture"]["skip_compile_commands"] = "yes"
        with self.assertRaisesRegex(ValueError, "boolean"):
            verifier.check_compile_commands(self.project, self.cfg)

    def test_missing_or_disagreeing_contract_is_not_inferred_from_core(self):
        del self.cfg["compile_flags"]
        with self.assertRaisesRegex(ValueError, "contract requires compile_flags"):
            self.check()
        self.cfg["compile_flags"] = contract()["cores"]["CM33"]["compile_flags"]
        with self.assertRaisesRegex(ValueError, "disagrees with compiler"):
            self.check()

    def test_malformed_empty_conflicting_and_symlinked_databases_fail(self):
        for entries in ([], {}, [None], [{**self.entry, "arguments": "invalid"}],
                        [{**self.entry, "command": "arm-none-eabi-gcc -mcpu=cortex-m33"}]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.check(entries)
        target = self.project / "outside.json"
        target.write_text("[]")
        self.path.unlink()
        self.path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            verifier.check_compile_commands(self.project, self.cfg)


def boot_fixture(vector=0x02000000, vector_end=None, reset=0x02000041, initial_sp=0x22000100,
                 stack_limit=0x22000080, stack_top=0x22000100, handler=None, entry=None):
    vector_end = vector + 0x40 if vector_end is None else vector_end
    data = bytearray(128)
    # HM 14.3.1 Table 14.3: reserved slots are 8, 9, 10 and 13, not NMI.
    struct.pack_into("<16I", data, 0, initial_sp, reset, reset, reset if handler is None else handler,
                     reset, reset, reset, reset, 0, 0, 0, reset, reset, 0, reset, reset)
    struct.pack_into("<H", data, 0x40, 0xe7fe)  # Thumb branch to self, after the fixed table.
    text = elf_text(physical=vector, filesz=96)
    text += ("  Data: 2's complement, little endian\n  Entry point address: " + hex(reset if entry is None else entry) + "\n" +
             f"  LOAD 0x80 0x{stack_limit:x} 0x{stack_limit:x} 0x0 0x{max(0, stack_top-stack_limit):x} RW 0x1\n")
    for index, (name, value) in enumerate((("__Vectors", vector), ("__Vectors_End", vector_end),
                                          ("Reset_Handler", reset), ("__StackLimit", stack_limit), ("__StackTop", stack_top))):
        text += f" {index}: {value:08x} 0 NOTYPE GLOBAL DEFAULT 1 {name}\n"
    return bytes(data), text


class BootTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()

    def check(self, **kwargs):
        data, text = boot_fixture(**kwargs)
        verifier.elf_ranges(text, len(data), self.contract, "CM85")
        return verifier.check_boot(data, text, self.contract, "CM85")

    def test_vector_reset_entry_stack_and_handlers_are_reported(self):
        result = self.check()
        self.assertEqual(result["reset"], "0x2000041")
        self.assertEqual(result["vector_end"], "0x2000040")
        self.assertEqual(result["initial_sp"], "0x22000100")
        self.assertEqual(result["checked_handlers"], 11)

    def test_truncated_fixed_vector_tables_are_rejected(self):
        data, text = boot_fixture()
        for size in (8, 16, 60):
            with self.subTest(size=size, mutation="extent"):
                truncated = text.replace("02000040 0 NOTYPE", f"{0x02000000 + size:08x} 0 NOTYPE")
                with self.assertRaisesRegex(ValueError, "vector table extent"):
                    verifier.check_boot(data, truncated, self.contract, "CM85")
            with self.subTest(size=size, mutation="file bytes"):
                with self.assertRaisesRegex(ValueError, "beyond ELF file"):
                    verifier.check_boot(data[:size], text, self.contract, "CM85")

    def test_zero_reset_nmi_and_hardfault_are_rejected_on_both_cores(self):
        for core in ("CM85", "CM33"):
            cfg = self.contract["cores"][core]
            vector = int(cfg["MRAM"]["start"], 0)
            ram = int(cfg["SRAM"]["start"], 0)
            data, text = boot_fixture(vector=vector, reset=vector + 0x41, initial_sp=ram + 256,
                                      stack_limit=ram + 128, stack_top=ram + 256)
            self.assertEqual(verifier.check_boot(data, text, self.contract, core)["status"], "checked")
            for offset, message in ((4, "reset vector"), (8, "mandatory"), (12, "mandatory")):
                with self.subTest(core=core, offset=offset):
                    bad = bytearray(data)
                    struct.pack_into("<I", bad, offset, 0)
                    with self.assertRaisesRegex(ValueError, message):
                        verifier.check_boot(bad, text, self.contract, core)

    def test_reserved_holes_and_security_dependent_zeros_remain_valid(self):
        data, text = boot_fixture()
        for offset in (0x20, 0x24, 0x28, 0x34):
            self.assertEqual(struct.unpack_from("<I", data, offset)[0], 0)
        # SecureFault is present in the secure-style fixture, absent in a non-secure table.
        self.assertNotEqual(struct.unpack_from("<I", data, 0x1c)[0], 0)
        nonsecure = bytearray(data)
        struct.pack_into("<I", nonsecure, 0x1c, 0)
        self.assertEqual(verifier.check_boot(nonsecure, text, self.contract, "CM85")["checked_handlers"], 10)
        # Only Reset, NMI and HardFault are unconditionally mandatory here.
        minimal = bytearray(data)
        for offset in (0x10, 0x14, 0x18, 0x1c, 0x2c, 0x30, 0x38, 0x3c):
            struct.pack_into("<I", minimal, offset, 0)
        self.assertEqual(verifier.check_boot(minimal, text, self.contract, "CM85")["checked_handlers"], 3)

    def test_every_nonzero_fixed_handler_needs_thumb_executable_backing(self):
        data, text = boot_fixture()
        for offset in range(8, 0x40, 4):
            for handler, message in ((0x02000040, "Thumb"), (0x22000081, "outside allocated"),
                                     (0x02000081, "backing")):
                with self.subTest(offset=offset, handler=hex(handler)):
                    bad = bytearray(data)
                    struct.pack_into("<I", bad, offset, handler)
                    with self.assertRaisesRegex(ValueError, message):
                        verifier.check_boot(bad, text, self.contract, "CM85")

    def test_optional_external_vectors_are_checked_after_complete_fixed_table(self):
        data, text = boot_fixture(vector_end=0x02000048, reset=0x02000051)
        data = bytearray(data)
        struct.pack_into("<II", data, 0x40, 0, 0)
        struct.pack_into("<H", data, 0x50, 0xe7fe)
        self.assertEqual(verifier.check_boot(data, text, self.contract, "CM85")["checked_handlers"], 11)
        for offset in (0x40, 0x44):
            with self.subTest(offset=offset):
                bad = bytearray(data)
                struct.pack_into("<I", bad, offset, 0x02000040)
                with self.assertRaisesRegex(ValueError, "Thumb"):
                    verifier.check_boot(bad, text, self.contract, "CM85")

    def test_stack_top_can_be_exact_one_past_ram_end(self):
        self.assertEqual(self.check(stack_limit=0x220cff00, stack_top=0x220d0000, initial_sp=0x220d0000)["stack_top"],
                         "0x220d0000")

    def test_wrong_reset_thumb_entry_executable_backing_or_bounds_fail(self):
        for kwargs, message in (({"reset": 0x02000020}, "reset vector/Thumb"),
                                ({"entry": 0x02000023}, "entry"),
                                ({"reset": 0x02080001}, "outside allocated"),
                                ({"reset": 0x02000081}, "backing"),
                                ({"handler": 0x02000020}, "Thumb"),
                                ({"handler": 0x22000081}, "outside allocated")):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                self.check(**kwargs)
        data, text = boot_fixture()
        with self.assertRaisesRegex(ValueError, "reset vector"):
            verifier.check_boot(data, text.replace("02000041 0 NOTYPE", "02000043 0 NOTYPE"), self.contract, "CM85")
        with self.assertRaisesRegex(ValueError, "backing"):
            verifier.check_boot(data, text.replace("R E", "R  "), self.contract, "CM85")

    def test_vector_address_alignment_extent_and_file_bounds_fail(self):
        for kwargs in ({"vector": 0x02000004}, {"vector_end": 0x02000004},
                       {"vector_end": 0x02000011}, {"vector_end": 0x02080004}, {"vector_end": 0x02000100}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(**kwargs)
        self.contract["cores"]["CM85"]["boot"]["vector_alignment"] = 3
        with self.assertRaisesRegex(ValueError, "alignment"):
            self.check()
        self.contract["cores"]["CM85"]["boot"] = {"vector_address": "0x02080000", "vector_alignment": 128}
        data, text = boot_fixture(vector=0x02080000)
        with self.assertRaisesRegex(ValueError, "Vector table outside allocated"):
            verifier.check_boot(data, text, self.contract, "CM85")
        data, text = boot_fixture()
        with self.assertRaisesRegex(ValueError, "beyond ELF file"):
            verifier.check_boot(data[:4], text, contract(), "CM85")

    def test_wrong_initial_sp_stack_bounds_alignment_or_permissions_fail(self):
        for kwargs in ({"initial_sp": 0x22000108}, {"initial_sp": 0x22000000},
                       {"stack_limit": 0x22000100}, {"stack_limit": 0x22000084},
                       {"stack_limit": 0x02000100, "stack_top": 0x02000200, "initial_sp": 0x02000200}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(**kwargs)
        data, text = boot_fixture(stack_limit=0x220d0000, stack_top=0x220d0100, initial_sp=0x220d0100)
        with self.assertRaisesRegex(ValueError, "Stack outside allocated"):
            verifier.check_boot(data, text, self.contract, "CM85")
        data, text = boot_fixture()
        with self.assertRaisesRegex(ValueError, "backing"):
            verifier.check_boot(data, text.replace(" RW ", " R "), self.contract, "CM85")

    def test_local_mapping_symbols_are_ignored_but_conflicting_boot_globals_fail(self):
        data, text = boot_fixture()
        locals_text = (" 10: 02000010 0 NOTYPE LOCAL DEFAULT 1 $d\n"
                       " 11: 02000020 0 NOTYPE LOCAL DEFAULT 1 $d\n"
                       " 12: 02000024 0 FUNC LOCAL DEFAULT 1 helper\n"
                       " 13: 02000028 0 FUNC LOCAL DEFAULT 1 helper\n")
        self.assertEqual(verifier.check_boot(data, text + locals_text, self.contract, "CM85")["status"], "checked")
        with self.assertRaisesRegex(ValueError, "Conflicting ELF symbol: Reset_Handler"):
            verifier.check_boot(data, text + " 14: 02000025 0 FUNC GLOBAL DEFAULT 1 Reset_Handler\n",
                                self.contract, "CM85")
        with self.assertRaisesRegex(ValueError, "Missing boot ELF symbol: Reset_Handler"):
            verifier.check_boot(data, text.replace("Reset_Handler", "other") +
                                " 14: 00000000 0 FUNC GLOBAL DEFAULT UND Reset_Handler\n", self.contract, "CM85")

    def test_missing_symbols_contract_and_wrong_byte_order_fail_closed(self):
        data, text = boot_fixture()
        for changed in (text.replace("__StackTop", "missing"), text.replace("little endian", "big endian")):
            with self.subTest(text=changed), self.assertRaises(ValueError):
                verifier.check_boot(data, changed, self.contract, "CM85")
        del self.contract["cores"]["CM85"]["boot"]
        with self.assertRaisesRegex(ValueError, "contract requires boot"):
            verifier.check_boot(data, text, self.contract, "CM85")


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.baseline = self.root / "baseline"
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.contract = contract()
        self.projects = {}
        self.entries = {ALIAS: b"current source\n", MDF: b"<raModuleDescription/>"}
        pdsc = ET.Element("package")
        components = ET.SubElement(pdsc, "components")
        component = ET.SubElement(components, "component", Cclass="BSP", Cgroup="ra8p1", Csub="fsp", Cversion="5.9.0")
        files = ET.SubElement(component, "files")
        ET.SubElement(files, "file", name=ALIAS, category="source")
        self.entries[PDSC] = ET.tostring(pdsc)
        for relative, data in ((SOURCE, self.entries[ALIAS]), (MDF[1:], self.entries[MDF])):
            self.put(self.baseline, relative, data)
        self.write_manifest()
        for core, name in (("CM85", "cpu0"), ("CM33", "cpu1")):
            project = self.root / name
            project.mkdir()
            self.projects[core] = project
            self.put(project, ".project", ("<projectDescription><name>" + name + "</name></projectDescription>").encode())
            self.put(project, SOURCE, self.entries[ALIAS])
            self.put(project, "Debug/" + name + ".elf", bytes(4096))
            self.configuration(core)
            self.launch(core)
            self.compilation(core)
            # Original source/hash fixtures deliberately contain no real ELF boot table.
            self.contract["cores"][core]["legacy_fixture"] = {"skip_boot": True}
        self.reader = patch.object(verifier, "inspect_elf", side_effect=lambda path, _: elf_text(
            cpu="cortex-m85" if path.stem == "cpu0" else "cortex-m33",
            physical=0x02000000 if path.stem == "cpu0" else 0x12080000))
        self.reader.start()
        self.addCleanup(self.reader.stop)
        self.originals_patch = patch.object(verifier, "original_source_hashes", return_value={})
        self.originals = self.originals_patch.start()
        self.addCleanup(self.originals_patch.stop)

    def put(self, root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def configuration(self, core, changes=None):
        cfg = self.contract["cores"][core]
        root = ET.Element("raConfiguration")
        general = ET.SubElement(root, "generalSettings")
        settings = {"Core": core, "#TargetName#": self.contract["part"], "#FSPVersion#": "5.9.0",
                    "#TargetARCHITECTURE#": cfg["compiler"], "#DeviceCommand#": cfg["debugger"], **(changes or {})}
        for key, value in settings.items():
            ET.SubElement(general, "option", key=key, value=value)
        selected = ET.SubElement(root, "raComponentSelection")
        component = ET.SubElement(selected, "component", **{"class": "BSP", "group": "ra8p1", "subgroup": "fsp", "version": "5.9.0"})
        ET.SubElement(component, "originalPack").text = PACK
        self.put(self.projects[core], "configuration.xml", ET.tostring(root))

    def launch(self, core, target=None):
        root = ET.Element("launchConfiguration")
        ET.SubElement(root, "stringAttribute", key="com.renesas.cdt.core.serverParam",
                      value="-g SEGGERJLINKARM -t " + (target or self.contract["cores"][core]["debugger"]))
        self.put(self.projects[core], "Debug.launch", ET.tostring(root))

    def compilation(self, core, changes=None):
        flags = {**self.contract["cores"][core]["compile_flags"], **(changes or {})}
        arguments = ["/tool chain/bin/arm-none-eabi-gcc", "-mthumb"]
        arguments += ["-" + key + "=" + value for key, value in flags.items()]
        arguments += ["-c", SOURCE, "-o", "system.o"]
        self.put(self.projects[core], "Debug/compile_commands.json", json.dumps([
            {"directory": str(self.projects[core] / "Debug"), "file": SOURCE, "arguments": arguments}
        ]).encode())

    def write_manifest(self, extra=None):
        manifest = {"packs": {}}
        for pack, entries in {PACK: self.entries, **(extra or {})}.items():
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            raw = stream.getvalue()
            self.put(self.candidate, pack, raw)
            manifest["packs"][pack] = {"sha256": digest(raw), "entries": {n: digest(d) for n, d in entries.items()}}
        self.put(self.candidate, "manifest.json", json.dumps(manifest).encode())

    def verify(self):
        return verifier.verify(self.candidate, self.contract, self.projects, self.baseline, "readelf")

    def test_pair_freshness_identity_and_physical_disjointness(self):
        result = self.verify()
        self.assertTrue(result["success"])
        self.assertEqual(result["baseline_sources"], 2)
        self.assertEqual(result["projects"]["CM33"]["physical_ranges"], [["0x2080000", "0x2080004"]])
        self.assertEqual(result["projects"]["CM85"]["checked_sources"], 1)

    def preserve_original_variant(self):
        canonical = b"/* original canonical banner */\nint stock;\n"
        variant = b"/* original other banner */\nint stock;\n"
        other = "Renesas.RA.5.9.0.pack"
        self.originals.return_value = {SOURCE: {(PACK, ALIAS): digest(variant), (other, SOURCE): digest(canonical)}}
        self.put(self.baseline, SOURCE, canonical)
        self.entries[ALIAS] = variant
        for project in self.projects.values():
            self.put(project, SOURCE, variant)
        self.write_manifest()
        return canonical, variant, other

    def test_exact_original_variant_is_reported_and_generated_owner_bytes_still_checked(self):
        canonical, variant, _ = self.preserve_original_variant()
        result = self.verify()
        self.originals.assert_called_once_with()
        self.assertEqual(result["baseline_original_variants"], [{
            "pack": PACK, "entry": ALIAS, "checkout_sha256": digest(canonical), "pack_entry_sha256": digest(variant)}])
        # The generated file must match its selected pack, not merely the checkout.
        self.put(self.projects["CM85"], SOURCE, canonical)
        with self.assertRaisesRegex(ValueError, "stale generated project source"):
            self.verify()

    def test_original_variant_needs_exact_original_checkout_and_owner(self):
        canonical, variant, other = self.preserve_original_variant()
        cases = (
            (canonical + b"/* current edit */", variant, self.originals.return_value),
            (canonical, variant + b"/* unknown edit */", self.originals.return_value),
            (canonical, b"third original variant", {SOURCE: {
                (PACK, ALIAS): digest(variant), (other, SOURCE): digest(canonical),
                ("Renesas.third.5.9.0.pack", SOURCE): digest(b"third original variant")}}),
            (canonical, variant, {SOURCE: {(other, SOURCE): digest(canonical)}}),
            (canonical, variant, {"ra/fsp/src/unrelated.c": self.originals.return_value[SOURCE]}),
        )
        for checkout, candidate, originals in cases:
            with self.subTest(checkout=checkout, candidate=candidate, originals=originals):
                self.put(self.baseline, SOURCE, checkout)
                self.entries[ALIAS] = candidate
                self.originals.return_value = originals
                self.write_manifest()
                with self.assertRaisesRegex(ValueError, "Stale baseline-to-pack source"):
                    self.verify()

    def test_changed_shared_source_requires_exact_current_bytes_in_every_owner(self):
        canonical, variant, other = self.preserve_original_variant()
        current = canonical + b"/* approved source edit */\n"
        self.put(self.baseline, SOURCE, current)
        self.entries[ALIAS] = current
        self.write_manifest({other: {SOURCE: canonical}})
        with self.assertRaisesRegex(ValueError, "Stale baseline-to-pack source: " + other):
            self.verify()
        self.write_manifest({other: {SOURCE: current}})
        for project in self.projects.values():
            self.put(project, SOURCE, current)
        self.originals.reset_mock()
        result = self.verify()
        self.assertEqual(result["baseline_original_variants"], [])
        self.originals.assert_not_called()

    def test_original_variant_approval_does_not_survive_checkout_change_or_missing_file(self):
        canonical, _, _ = self.preserve_original_variant()
        for changed in (False, True):
            with self.subTest(changed=changed):
                self.put(self.baseline, SOURCE, canonical)
                def alter_checkout(*args, **kwargs):
                    path = self.baseline / SOURCE
                    if changed:
                        path.write_bytes(canonical + b"/* later edit */")
                    else:
                        path.unlink()
                    return {"status": "fixture"}
                with patch.object(verifier, "check_compile_commands", side_effect=alter_checkout):
                    with self.assertRaisesRegex(ValueError, "Missing/stale owning baseline source"):
                        self.verify()

    def selected_original_variants(self, reverse=False, canonical=None, variant=None, relative=SOURCE):
        canonical = canonical if canonical is not None else (
            b"/*\r\n* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates\r\n"
            b"*\r\n* SPDX-License-Identifier: BSD-3-Clause\r\n*/\r\n\r\nint stock;\r\n")
        variant = variant if variant is not None else b"/* ${REA_DISCLAIMER_PLACEHOLDER} */\r\n\r\nint stock;\r\n"
        other = "Renesas.RA.5.9.0.pack"
        entry = ALIAS if relative == SOURCE else relative
        pdsc = ET.fromstring(self.entries[PDSC])
        pdsc.find("./components/component/files/file").set("name", entry)
        self.entries[PDSC] = ET.tostring(pdsc)
        self.entries.pop(ALIAS, None)
        self.entries[entry] = variant
        extra_pdsc = ET.Element("package")
        component = ET.SubElement(ET.SubElement(extra_pdsc, "components"), "component",
                                  Cclass="Middleware", Cgroup="all", Csub="fixture", Cversion="5.9.0")
        ET.SubElement(ET.SubElement(component, "files"), "file", name=relative, category="header")
        extra = {relative: canonical, "Renesas.RA.pdsc": ET.tostring(extra_pdsc)}
        self.originals.return_value = {relative: {(PACK, entry): digest(variant), (other, relative): digest(canonical)}}
        self.put(self.baseline, relative, canonical)
        for core, project in self.projects.items():
            self.configuration(core)
            config = ET.fromstring((project / "configuration.xml").read_bytes())
            selected = config.find("./raComponentSelection")
            added = ET.Element("component", **{"class": "Middleware", "group": "all", "subgroup": "fixture", "version": "5.9.0"})
            ET.SubElement(added, "originalPack").text = other
            if reverse:
                selected.insert(0, added)
            else:
                selected.append(added)
            self.put(project, "configuration.xml", ET.tostring(config))
            self.put(project, relative, variant)
        self.write_manifest({other: extra})
        return canonical, variant, other, entry

    def test_selected_disclaimer_variants_accept_either_verified_owner_in_both_orders(self):
        for reverse in (False, True):
            for baseline_owner in (0, 1):
                for generated_owner in (0, 1):
                    with self.subTest(reverse=reverse, baseline_owner=baseline_owner, generated_owner=generated_owner):
                        canonical, variant, other, entry = self.selected_original_variants(reverse)
                        values = (canonical, variant)
                        self.put(self.baseline, SOURCE, values[baseline_owner])
                        for project in self.projects.values():
                            self.put(project, SOURCE, values[generated_owner])
                        result = self.verify()
                        for core in self.projects:
                            self.assertEqual(result["projects"][core]["reconciled_original_source_owners"], [{
                                "path": SOURCE, "generated_sha256": digest(values[generated_owner]),
                                "owners": [{"pack": name, "entry": source, "sha256": sha}
                                           for (name, source), sha in sorted({(PACK, entry): digest(variant),
                                                                            (other, SOURCE): digest(canonical)}.items())]}])

    def test_selected_original_variants_reject_body_banner_metadata_and_unproven_owners_both_orders(self):
        for reverse in (False, True):
            for difference in ("body", "banner", "metadata", "missing_proof", "wrong_owner", "changed_pack"):
                with self.subTest(reverse=reverse, difference=difference):
                    kwargs = {}
                    if difference == "body":
                        kwargs["variant"] = b"/* ${REA_DISCLAIMER_PLACEHOLDER} */\r\n\r\nint changed;\r\n"
                    elif difference == "banner":
                        kwargs["variant"] = b"/* arbitrary banner */\r\n\r\nint stock;\r\n"
                    elif difference == "metadata":
                        kwargs["relative"] = "ra/fsp/src/fixture.xml"
                    canonical, variant, other, entry = self.selected_original_variants(reverse, **kwargs)
                    relative = kwargs.get("relative", SOURCE)
                    if difference == "missing_proof":
                        del self.originals.return_value[relative][(other, relative)]
                    elif difference == "wrong_owner":
                        self.originals.return_value[relative][(other, relative)] = digest(variant)
                    elif difference == "changed_pack":
                        self.originals.return_value[relative][(other, relative)] = digest(canonical + b"old bytes")
                    with self.assertRaisesRegex(ValueError, "Conflicting selected source owners|Stale baseline-to-pack source"):
                        self.verify()
                    if difference == "metadata":
                        # Restore the main fixture's source record for the next case.
                        pdsc = ET.fromstring(self.entries[PDSC])
                        pdsc.find("./components/component/files/file").set("name", ALIAS)
                        self.entries[PDSC] = ET.tostring(pdsc)
                        del self.entries[relative]

    def test_selected_disclaimer_variants_reject_unselected_or_edited_generated_bytes_both_orders(self):
        for reverse in (False, True):
            canonical, variant, _, _ = self.selected_original_variants(reverse)
            third = b"/* unselected original banner */\r\n\r\nint stock;\r\n"
            self.originals.return_value[SOURCE][("Third.Original.5.9.0.pack", SOURCE)] = digest(third)
            for generated in (third, variant + b"/* edited */", canonical.replace(b"int stock", b"int changed")):
                with self.subTest(reverse=reverse, generated=generated):
                    self.put(self.projects["CM85"], SOURCE, generated)
                    with self.assertRaisesRegex(ValueError, "Missing/stale generated project source"):
                        self.verify()
            self.put(self.projects["CM85"], SOURCE, variant)
            self.put(self.baseline, SOURCE, canonical + b"/* edited */")
            with self.assertRaisesRegex(ValueError, "Stale baseline-to-pack source"):
                self.verify()

    def test_empty_load_segments_are_explicitly_reported_without_ranges(self):
        text = elf_text() + "  LOAD 0x4d4 0x0 0x0 0x0 0x0     0x1000\n"
        with patch.object(verifier, "inspect_elf", return_value=text):
            result = verifier.verify(self.candidate, self.contract, {"CM85": self.projects["CM85"]},
                                     self.baseline, "readelf")
        project = result["projects"]["CM85"]
        self.assertEqual(project["physical_ranges"], [["0x2000000", "0x2000004"]])
        self.assertEqual(project["ignored_empty_load_segments"], [{"index": 1, "offset": 0x4d4,
                         "virtual": 0, "physical": 0, "filesz": 0, "memsz": 0, "flags": "", "alignment": 0x1000}])

    def test_end_to_end_compile_and_boot_checks_are_required(self):
        texts = {}
        for core, project in self.projects.items():
            cfg = self.contract["cores"][core]
            del cfg["legacy_fixture"]
            vector = int(cfg["MRAM"]["start"], 0)
            ram = int(cfg["SRAM"]["start"], 0)
            data, text = boot_fixture(vector=vector, reset=vector + 0x41, initial_sp=ram + 256,
                                      stack_limit=ram + 128, stack_top=ram + 256)
            text = text.replace("cortex-m85", cfg["compiler"])
            (project / ("Debug/" + project.name + ".elf")).write_bytes(data)
            texts[project.name] = text
        with patch.object(verifier, "inspect_elf", side_effect=lambda path, _: texts[path.stem]):
            result = self.verify()
            for core in self.projects:
                self.assertEqual(result["projects"][core]["boot"]["status"], "checked")
                self.assertEqual(result["projects"][core]["compile_commands"]["checked_entries"], 1)
            path = self.projects["CM85"] / "Debug/cpu0.elf"
            bad = bytearray(path.read_bytes())
            struct.pack_into("<I", bad, 0, 0x220d0008)
            path.write_bytes(bad)
            with self.assertRaisesRegex(ValueError, "stack pointer"):
                self.verify()
        self.compilation("CM85", {"mfpu": "fpv5-sp-d16"})
        with self.assertRaisesRegex(ValueError, "compiler -mfpu"):
            self.verify()

    def test_manifest_archive_and_regular_entry_hashes_are_verified(self):
        manifest = self.candidate / "manifest.json"
        value = json.loads(manifest.read_text())
        value["packs"][PACK]["entries"][ALIAS] = "0" * 64
        manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "Pack entry hash mismatch"):
            self.verify()
        self.write_manifest()
        with (self.candidate / PACK).open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "Pack hash mismatch"):
            self.verify()

    def test_stale_baseline_pack_and_project_bytes_fail_independently(self):
        path = self.baseline / SOURCE
        path.write_bytes(b"newer source")
        with self.assertRaisesRegex(ValueError, "Stale baseline-to-pack"):
            self.verify()
        path.write_bytes(self.entries[ALIAS])
        (self.projects["CM85"] / SOURCE).write_bytes(b"old extraction")
        with self.assertRaisesRegex(ValueError, "stale generated project source"):
            self.verify()

    def test_missing_owning_or_generated_source_is_not_skipped(self):
        path = self.baseline / SOURCE
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing/stale owning"):
            self.verify()
        self.put(self.baseline, SOURCE, self.entries[ALIAS])
        (self.projects["CM85"] / SOURCE).unlink()
        with self.assertRaisesRegex(ValueError, "Missing/stale generated"):
            self.verify()

    def test_wrong_project_core_part_compiler_and_debugger_fail(self):
        for key, value in (("Core", "CM33"), ("#TargetName#", "OTHER"),
                           ("#TargetARCHITECTURE#", "cortex-m33"),
                           ("#DeviceCommand#", "R7KA8P1KF_CPU1")):
            with self.subTest(key=key):
                self.configuration("CM85", {key: value})
                with self.assertRaisesRegex(ValueError, "Wrong project identity"):
                    self.verify()
        self.configuration("CM85")
        self.launch("CM85", "R7KA8P1KF_CPU1")
        with self.assertRaisesRegex(ValueError, "Wrong launch debugger"):
            self.verify()

    def test_explicit_configuration_device_base_does_not_weaken_launch_core_check(self):
        self.contract["cores"]["CM85"]["device_command"] = "R7KA8P1KF"
        self.configuration("CM85", {"#DeviceCommand#": "R7KA8P1KF"})
        self.verify()
        self.launch("CM85", "R7KA8P1KF_CPU1")
        with self.assertRaisesRegex(ValueError, "Wrong launch debugger core"):
            self.verify()

    def test_explicit_attach_launch_avoids_ambiguous_multicore_launch_group(self):
        project = self.projects["CM33"]
        (project / "Debug.launch").rename(project / "Attach.launch")
        self.launch("CM33", "R7KA8P1KF_CPU0")
        with self.assertRaisesRegex(ValueError, "unique launch path"):
            self.verify()
        self.contract["cores"]["CM33"]["launch"] = "Attach.launch"
        self.verify()

    def test_duplicate_project_paths_or_unknown_core_fail(self):
        self.projects["CM33"] = self.projects["CM85"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.verify()
        self.projects = {"unrecognized": self.projects["CM85"]}
        with self.assertRaisesRegex(ValueError, "unknown contract core"):
            self.verify()

    def test_identical_complete_duplicate_components_preserve_source_verification(self):
        pdsc = ET.fromstring(self.entries[PDSC])
        components = pdsc.find("./components")
        component = components[0]
        component.set("Cvendor", "Renesas")
        ET.SubElement(component, "description").text = "Complete fixture record"
        for _ in range(2):
            components.append(ET.fromstring(ET.tostring(component)))
        self.entries[PDSC] = ET.tostring(pdsc)
        self.write_manifest()
        result = self.verify()
        for core in self.projects:
            self.assertEqual(result["projects"][core]["checked_sources"], 1)
        self.put(self.projects["CM85"], SOURCE, b"stale duplicate-owned source")
        with self.assertRaisesRegex(ValueError, "stale generated project source"):
            self.verify()

    def test_duplicate_component_differences_anywhere_are_rejected_before_condition_filtering(self):
        original = self.entries[PDSC]
        for difference in ("vendor", "condition", "description", "file_name", "file_category", "file_version",
                           "file_condition", "file_attribute", "missing_file", "extra_file", "extra_child",
                           "child_order", "nested_text", "child_tail", "component_text"):
            for reverse in (False, True):
                with self.subTest(difference=difference, reverse=reverse):
                    pdsc = ET.fromstring(original)
                    components = pdsc.find("./components")
                    component = components[0]
                    ET.SubElement(component, "description").text = "Description"
                    duplicate = ET.fromstring(ET.tostring(component))
                    source = duplicate.find("./files/file")
                    if difference == "vendor":
                        duplicate.set("Cvendor", "other vendor")
                    elif difference == "condition":
                        duplicate.set("condition", "different condition")
                    elif difference == "description":
                        duplicate.find("description").text = "Other description"
                    elif difference.startswith("file_"):
                        key = difference.removeprefix("file_")
                        source.set(key, "different")
                    elif difference == "missing_file":
                        duplicate.find("files").remove(source)
                    elif difference == "extra_file":
                        ET.SubElement(duplicate.find("files"), "file", name="other.c", category="source")
                    elif difference == "extra_child":
                        ET.SubElement(duplicate, "unsupported_metadata", enabled="true")
                    elif difference == "child_order":
                        duplicate[:] = reversed(list(duplicate))
                    elif difference == "nested_text":
                        source.text = "unexpected content"
                    elif difference == "child_tail":
                        source.tail = "different tail"
                    elif difference == "component_text":
                        duplicate.text = "different component text"
                    components.insert(0, duplicate) if reverse else components.append(duplicate)
                    self.entries[PDSC] = ET.tostring(pdsc)
                    self.write_manifest()
                    with self.assertRaisesRegex(ValueError, "Selected component is not unique"):
                        self.verify()

    def test_missing_component_match_still_fails(self):
        pdsc = ET.fromstring(self.entries[PDSC])
        components = pdsc.find("./components")
        components.remove(components[0])
        self.entries[PDSC] = ET.tostring(pdsc)
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Selected component is not unique"):
            self.verify()

    def test_conditional_other_core_linker_is_excluded_but_current_is_required(self):
        pdsc = ET.fromstring(self.entries[PDSC])
        conditions = ET.SubElement(pdsc, "conditions")
        for core, name in (("CM85", "Cortex-M85"), ("CM33", "Cortex-M33")):
            node = ET.SubElement(conditions, "condition", id=core)
            ET.SubElement(node, "require", Dcore=name)
            relative = "script/" + core + ".ld"
            ET.SubElement(pdsc.find("./components/component/files"), "file", name=relative, condition=core)
            self.entries[relative] = core.encode()
            self.put(self.projects[core], relative, core.encode())
        self.entries[PDSC] = ET.tostring(pdsc)
        self.write_manifest()
        self.verify()
        (self.projects["CM85"] / "script/CM85.ld").unlink()
        with self.assertRaisesRegex(ValueError, "Missing/stale generated"):
            self.verify()

    def test_unknown_condition_fact_and_cycle_fail_closed(self):
        pdsc = ET.fromstring(self.entries[PDSC])
        conditions = ET.SubElement(pdsc, "conditions")
        node = ET.SubElement(conditions, "condition", id="unknown")
        ET.SubElement(node, "require", UnsupportedFact="value")
        with self.assertRaisesRegex(ValueError, "Missing PDSC condition fact"):
            verifier.condition_matches("unknown", pdsc, {})
        node[0].attrib.clear()
        node[0].set("condition", "unknown")
        with self.assertRaisesRegex(ValueError, "Cyclic PDSC"):
            verifier.condition_matches("unknown", pdsc, {})

    def test_symlinked_project_source_and_unsafe_elf_override_fail(self):
        path = self.projects["CM85"] / SOURCE
        path.unlink()
        path.symlink_to(self.baseline / SOURCE)
        with self.assertRaisesRegex(ValueError, "Symlinked path"):
            self.verify()
        path.unlink()
        path.write_bytes(self.entries[ALIAS])
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            verifier.verify(self.candidate, self.contract, self.projects, self.baseline, "readelf", {"CM85": "../outside.elf"})

    def test_cli_assignments_require_unique_explicit_core_paths(self):
        self.assertEqual(verifier.assignments(["CM85=/tmp/a"]), {"CM85": "/tmp/a"})
        for values in (["/tmp/a"], ["CM85="], ["CM85=a", "CM85=b"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                verifier.assignments(values)


class OriginalSourceTests(unittest.TestCase):
    def test_loader_pins_release_hash_and_records_only_declared_per_owner_bytes(self):
        def zipped(entries):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            return stream.getvalue()

        release = {}
        expected = {}
        for name, entry, data in ((PACK, ALIAS, b"original variant"),
                                  ("Renesas.RA.5.9.0.pack", SOURCE, b"original canonical")):
            vendor, package, version = name[:-5].split(".", 2)
            pdsc = ET.Element("package")
            ET.SubElement(pdsc, "vendor").text = vendor
            ET.SubElement(pdsc, "name").text = package
            ET.SubElement(ET.SubElement(pdsc, "releases"), "release", version=version)
            component = ET.SubElement(ET.SubElement(pdsc, "components"), "component",
                                      Cvendor=vendor, Cclass="Projects", Cgroup="fixture", Cversion=version)
            ET.SubElement(ET.SubElement(component, "files"), "file", name=entry, category="source")
            release[verifier.pack_builder.PACK_PREFIX + name] = zipped({
                vendor + "." + package + ".pdsc": ET.tostring(pdsc), entry: data,
                "ra/fsp/src/unowned.c": b"not declared"})
            expected[(name, entry)] = digest(data)
        raw = zipped(release)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(raw)
            with patch.object(verifier, "ROOT", root), patch.object(verifier.pack_builder, "ARCHIVE_SHA256", digest(raw)):
                self.assertEqual(verifier.original_source_hashes(), {SOURCE: expected})
                archive.write_bytes(raw + b"tampered")
                with self.assertRaisesRegex(ValueError, "Release archive hash mismatch"):
                    verifier.original_source_hashes()

    def test_pinned_original_threadx_variants_retain_their_own_hashes(self):
        archive = verifier.ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Original release archive is not materialized")
        originals = verifier.original_source_hashes()
        source = "ra/fsp/src/rm_threadx_port/tx_port_vendor.h"
        self.assertEqual(originals[source], {
            ("Microsoft.ThreadX.6.4.0+fsp.5.9.0.pack", source):
                "60eae286d0a336b0047308c3e5e234647f286043b64ad0e2df0cf60b02216d5a",
            ("Renesas.RA.5.9.0.pack", source):
                "db0f767fd96f6660e353b89412adf5cdc0e0823bfd421ddc6ba8f9addba4e8cd"})


class RealReadelfTests(unittest.TestCase):
    def test_real_gnu_arm_elf_core_attributes_and_load_ranges(self):
        tools = {name: shutil.which("arm-none-eabi-" + name) for name in ("gcc", "ld", "readelf")}
        if not all(tools.values()):
            self.skipTest("ARM toolchain unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.s"
            source.write_text(".syntax unified\n.thumb\n.section .text\n.global _start\n.thumb_func\n_start: b .\n")
            script = root / "test.ld"
            script.write_text("ENTRY(_start)\nPHDRS { text PT_LOAD; }\nSECTIONS { . = 0x02000000; .text : { *(.text*) } :text }\n")
            for cpu, core in (("cortex-m85", "CM85"), ("cortex-m33", "CM33")):
                with self.subTest(cpu=cpu):
                    obj, elf = root / "test.o", root / "test.elf"
                    subprocess.run([tools["gcc"], "-mcpu=" + cpu, "-mthumb", "-c", str(source), "-o", str(obj)],
                                   check=True, capture_output=True)
                    subprocess.run([tools["ld"], "-T", str(script), str(obj), "-o", str(elf)], check=True, capture_output=True)
                    cfg = contract()
                    # GCC 13.2 dispatches the CPU to its architectural assembler target.
                    cfg["cores"]["CM85"]["elf_cpu_name"] = "8.1-M.MAIN"
                    cfg["cores"]["CM33"]["elf_cpu_name"] = "8-M.MAIN"
                    cfg["cores"][core]["MRAM"] = {"start": "0x02000000", "size": "0x80000"}
                    text = verifier.inspect_elf(elf, tools["readelf"])
                    ranges = verifier.elf_ranges(text, elf.stat().st_size, cfg, core)
                    self.assertIn((0x02000000, 0x02000002), ranges)
                    other = "CM33" if core == "CM85" else "CM85"
                    with self.assertRaisesRegex(ValueError, "Wrong ELF CPU"):
                        verifier.elf_ranges(text, elf.stat().st_size, cfg, other)

    def test_real_gnu_effective_default_fpu_both_cores_without_forcing_build_flags(self):
        compiler = shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("ARM compiler unavailable")
        for core, mask in (("CM85", 14), ("CM33", 4)):
            with self.subTest(core=core):
                target = contract()["cores"][core]
                flags = ["-mthumb", "-mcpu=" + target["compile_flags"]["mcpu"], "-mfloat-abi=hard"]
                result = verifier.check_default_fpu(compiler, flags, target["compile_flags"]["mfpu"])
                self.assertEqual(result["observed_macros"]["__ARM_FP"], mask)
                self.assertEqual(result["observed_macros"]["__ARM_PCS_VFP"], 1)
                self.assertFalse(any(flag.startswith("-mfpu") for flag in result["target_flags"]))
                wrong = "fpv5-sp-d16" if core == "CM85" else "fpv5-d16"
                with self.assertRaisesRegex(ValueError, "default FPU/ABI mismatch"):
                    verifier.check_default_fpu(compiler, flags, wrong)

    def test_real_gnu_vectors_reset_stack_and_compile_database_both_cores(self):
        tools = {name: shutil.which("arm-none-eabi-" + name) for name in ("gcc", "ld", "readelf")}
        if not all(tools.values()):
            self.skipTest("ARM toolchain unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "boot.s"
            source.write_text(".syntax unified\n.thumb\n.section .vectors,\"a\"\n.global __Vectors\n"
                              "__Vectors: .word __StackTop, Reset_Handler, Reset_Handler, Reset_Handler\n"
                              ".word Reset_Handler, Reset_Handler, Reset_Handler, Reset_Handler\n"
                              ".word 0, 0, 0, Reset_Handler, Reset_Handler, 0, Reset_Handler, Reset_Handler\n"
                              ".global __Vectors_End\n__Vectors_End:\n"
                              ".section .text,\"ax\"\n.global Reset_Handler\n.thumb_func\nReset_Handler: b .\n"
                              ".section .stack,\"aw\",%nobits\n.balign 8\n.space 256\n")
            for core in ("CM85", "CM33"):
                with self.subTest(core=core):
                    cfg = contract()
                    target = cfg["cores"][core]
                    # GNU 13.2 translates these CPUs to architectural assembler targets.
                    target["elf_cpu_name"] = "8.1-M.MAIN" if core == "CM85" else "8-M.MAIN"
                    vector, ram = target["MRAM"]["start"], target["SRAM"]["start"]
                    obj, elf = root / "boot.o", root / "boot.elf"
                    arguments = [tools["gcc"], "-mthumb", *["-" + key + "=" + value for key, value in target["compile_flags"].items()],
                                 "-c", str(source), "-o", str(obj)]
                    subprocess.run(arguments, check=True, capture_output=True)
                    (root / "compile_commands.json").write_text(json.dumps([
                        {"directory": str(root), "file": str(source), "arguments": arguments}]))
                    target["compile_commands"] = "compile_commands.json"
                    self.assertEqual(verifier.check_compile_commands(root, target)["checked_entries"], 1)
                    script = root / "boot.ld"
                    script.write_text("ENTRY(Reset_Handler)\nPHDRS { text PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(6); }\n"
                                      "SECTIONS { . = " + vector + "; .text : { *(.vectors) *(.text) } :text\n"
                                      ". = " + ram + "; .stack (NOLOAD) : { __StackLimit = .; *(.stack) __StackTop = .; } :ram }\n")
                    subprocess.run([tools["ld"], "-T", str(script), str(obj), "-o", str(elf)], check=True, capture_output=True)
                    text = verifier.inspect_elf(elf, tools["readelf"])
                    verifier.elf_ranges(text, elf.stat().st_size, cfg, core)
                    self.assertEqual(verifier.check_boot(elf.read_bytes(), text, cfg, core)["checked_handlers"], 11)
                    bad = bytearray(elf.read_bytes())
                    _, segments = verifier.parse_readelf(text)
                    struct.pack_into("<I", bad, segments[0]["offset"] + 4, int(vector, 0) + 0x80001)
                    with self.assertRaisesRegex(ValueError, "reset vector"):
                        verifier.check_boot(bad, text, cfg, core)

    def test_real_gnu_explicit_phdr_empty_load_and_nonempty_alignment_controls(self):
        tools = {name: shutil.which("arm-none-eabi-" + name) for name in ("gcc", "ld", "readelf")}
        if not all(tools.values()):
            self.skipTest("ARM toolchain unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, script, obj, elf = [root / name for name in ("empty.s", "empty.ld", "empty.o", "empty.elf")]
            source.write_text(".syntax unified\n.thumb\n.section .text,\"ax\"\n.global _start\n.thumb_func\n"
                              "_start: b .\n.section .bss,\"aw\",%nobits\n.balign 8\n.space 32\n")
            script.write_text("ENTRY(_start)\nPHDRS { text PT_LOAD FLAGS(5); unused PT_LOAD; ram PT_LOAD FLAGS(6); }\n"
                              "SECTIONS { . = 0x02080000; .text : { *(.text*) } :text\n"
                              ".unused : { *(.unused) } :unused\n"
                              ". = 0x220d0000; .bss (NOLOAD) : { *(.bss*) } :ram }\n")
            subprocess.run([tools["gcc"], "-mcpu=cortex-m33", "-mthumb", "-c", str(source), "-o", str(obj)],
                           check=True, capture_output=True)
            subprocess.run([tools["ld"], "-T", str(script), str(obj), "-o", str(elf)], check=True, capture_output=True)
            data = elf.read_bytes()
            text = verifier.inspect_elf(elf, tools["readelf"])
            _, segments = verifier.parse_readelf(text)
            self.assertEqual(len(segments), 3)
            empty = segments[1]
            self.assertEqual((empty["filesz"], empty["memsz"]), (0, 0))
            self.assertGreater(empty["alignment"], 1)
            self.assertNotEqual(empty["offset"] % empty["alignment"], empty["virtual"] % empty["alignment"])
            cfg = contract()
            cfg["cores"]["CM33"]["elf_cpu_name"] = "8-M.MAIN"
            self.assertEqual(verifier.elf_ranges(text, len(data), cfg, "CM33"),
                             [(0x02080000, 0x02080002), (0x220d0000, 0x220d0020)])
            phoff = struct.unpack_from("<I", data, 28)[0]
            phentsize = struct.unpack_from("<H", data, 42)[0]
            self.assertEqual(phentsize, 32)
            # Mutate the real headers, not readelf's text: every nonempty and
            # BSS-only mapping must still satisfy address/offset congruence.
            for index, field, value in ((1, 20, 1), (1, 16, 1),
                                         (0, 4, segments[0]["offset"] + 1),
                                         (2, 4, segments[2]["offset"] + 1)):
                with self.subTest(index=index, field=field):
                    bad = bytearray(data)
                    struct.pack_into("<I", bad, phoff + index * phentsize + field, value)
                    if index == 1 and field == 16:
                        struct.pack_into("<I", bad, phoff + phentsize + 20, value)
                    elf.write_bytes(bad)
                    with self.assertRaisesRegex(ValueError, "Invalid PT_LOAD alignment"):
                        verifier.elf_ranges(verifier.inspect_elf(elf, tools["readelf"]), len(bad), cfg, "CM33")

    def test_readelf_nonzero_or_warning_is_not_a_pass(self):
        for result in (subprocess.CompletedProcess([], 1, "", "bad ELF"),
                       subprocess.CompletedProcess([], 0, "output", "warning")):
            with patch.object(verifier.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(ValueError, "readelf failed"):
                    verifier.inspect_elf(Path("dummy.elf"), "readelf")


if __name__ == "__main__":
    unittest.main()
