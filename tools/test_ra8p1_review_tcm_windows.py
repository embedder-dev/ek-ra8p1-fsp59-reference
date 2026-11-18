"""Separate owning-CPU TCM runtime addresses from load/debug bus aliases."""
import struct
import unittest

from ra8p1 import verify_candidate as verifier
from test_ra8p1_candidate import boot_fixture, contract, elf_text


# HM Figure 5.2 p.238 and Table 2.37 pp.191-192.
TCM = {
    "CM85": {"ITCM": (0, 0x10000000, 0x28000000, 0x38000000),
             "DTCM": (0x20000000, 0x30000000, 0x28020000, 0x38020000)},
    "CM33": {"ITCM": (0, 0x10000000, 0x2a000000, 0x3a000000),
             "DTCM": (0x20000000, 0x30000000, 0x2a010000, 0x3a010000)},
}


class TcmWindowTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()
        for core, regions in TCM.items():
            for name, (_, local_ns, _, bus_ns) in regions.items():
                region = self.contract["cores"][core][name]
                region["aliases"] = [local_ns]
                region["bus_aliases"] = [bus_ns]

    def ranges(self, core, physical, virtual, filesz=4, memsz=None):
        text = elf_text(cpu=self.contract["cores"][core]["compiler"], physical=physical,
                        virtual=virtual, filesz=filesz, memsz=memsz)
        return verifier.elf_ranges(text, 4096, self.contract, core)

    def boot(self, core, vector=None, reset=None, stack=None):
        cfg = self.contract["cores"][core]
        vector = int(cfg["MRAM"]["start"], 0) if vector is None else vector
        reset = vector + 0x41 if reset is None else reset
        stack = int(cfg["SRAM"]["start"], 0) if stack is None else stack
        return boot_fixture(vector=vector, reset=reset, initial_sp=stack + 0x100,
                            stack_limit=stack + 0x80, stack_top=stack + 0x100)

    def test_own_bus_aliases_are_not_runtime_vmas_for_either_core(self):
        for core, regions in TCM.items():
            for name, (_, _, bus, bus_ns) in regions.items():
                for virtual in (bus, bus_ns):
                    for filesz in (0, 4):
                        with self.subTest(core=core, name=name, virtual=hex(virtual), filesz=filesz):
                            with self.assertRaisesRegex(ValueError, "outside explicit"):
                                self.ranges(core, bus, virtual, filesz=filesz, memsz=16)

    def test_bus_load_addresses_and_local_runtime_addresses_share_physical_identity(self):
        for core, regions in TCM.items():
            for name, (local, local_ns, bus, bus_ns) in regions.items():
                for physical in (bus, bus_ns):
                    for virtual in (local, local_ns):
                        with self.subTest(core=core, name=name, physical=hex(physical), virtual=hex(virtual)):
                            self.assertEqual(self.ranges(core, physical, virtual), [(bus, bus + 4)])

    def test_cpu_visible_local_and_nonsecure_aliases_remain_valid(self):
        for core, regions in TCM.items():
            for name, (local, local_ns, bus, _) in regions.items():
                for address in (local, local_ns):
                    with self.subTest(core=core, name=name, address=hex(address)):
                        self.assertEqual(self.ranges(core, address, address), [(bus, bus + 4)])

    def test_own_bus_alias_vector_tables_are_rejected_even_if_boot_contract_names_them(self):
        for core, regions in TCM.items():
            for vector in regions["ITCM"][2:]:
                with self.subTest(core=core, vector=hex(vector)):
                    self.contract["cores"][core]["boot"]["vector_address"] = vector
                    data, text = self.boot(core, vector=vector)
                    with self.assertRaisesRegex(ValueError, "Vector table outside allocated"):
                        verifier.check_boot(data, text, self.contract, core)

    def test_own_bus_alias_reset_entry_nmi_and_hardfault_addresses_are_rejected(self):
        for core, regions in TCM.items():
            for bus in regions["ITCM"][2:]:
                for offset in (4, 8, 12):
                    with self.subTest(core=core, bus=hex(bus), offset=offset):
                        data, text = self.boot(core, reset=bus + 1 if offset == 4 else None)
                        data = bytearray(data)
                        struct.pack_into("<I", data, offset, bus + 1)
                        struct.pack_into("<H", data, 0x60, 0xe7fe)
                        text += f"  LOAD 0x60 0x{bus:x} 0x{bus:x} 0x2 0x2 R E 0x1\n"
                        with self.assertRaisesRegex(ValueError, "Vector handler outside allocated"):
                            verifier.check_boot(data, text, self.contract, core)

    def test_own_bus_alias_stacks_are_rejected_for_either_core(self):
        for core, regions in TCM.items():
            for bus in regions["DTCM"][2:]:
                with self.subTest(core=core, bus=hex(bus)):
                    data, text = self.boot(core, stack=bus)
                    with self.assertRaisesRegex(ValueError, "Stack outside allocated"):
                        verifier.check_boot(data, text, self.contract, core)

    def test_boot_in_local_and_nonsecure_tcm_with_bus_alias_loads_is_valid(self):
        for core, regions in TCM.items():
            itcm, dtcm = regions["ITCM"], regions["DTCM"]
            for nonsecure in (False, True):
                with self.subTest(core=core, nonsecure=nonsecure):
                    vector, stack = itcm[int(nonsecure)], dtcm[int(nonsecure)]
                    load = itcm[2 + int(nonsecure)]
                    self.contract["cores"][core]["boot"]["vector_address"] = vector
                    data, text = self.boot(core, vector=vector, stack=stack)
                    text = text.replace(f"0x{vector:x} 0x{vector:x} 0x60", f"0x{vector:x} 0x{load:x} 0x60")
                    text = text.replace("cortex-m85", self.contract["cores"][core]["compiler"])
                    self.assertEqual(verifier.elf_ranges(text, len(data), self.contract, core),
                                     [(itcm[2], itcm[2] + 96), (dtcm[2] + 0x80, dtcm[2] + 0x100)])
                    self.assertEqual(verifier.check_boot(data, text, self.contract, core)["checked_handlers"], 11)

    def test_cross_core_load_and_runtime_physical_collisions_are_still_rejected(self):
        for name in ("ITCM", "DTCM"):
            with self.subTest(name=name):
                self.contract = contract()
                local0, _, bus0, _ = TCM["CM85"][name]
                local1, _, bus1, _ = TCM["CM33"][name]
                left = self.ranges("CM85", bus0, local0)
                right = self.ranges("CM33", bus1, local1)
                verifier.disjoint({"CM85": left, "CM33": right})
                # A conflicting caller allocation must collide after normalization,
                # even when one ELF uses a bus LMA and the other uses a local LMA.
                self.contract["cores"]["CM33"][name]["bus_alias"] = bus0
                right = self.ranges("CM33", local1, local1)
                with self.assertRaisesRegex(ValueError, "Physical overlap"):
                    verifier.disjoint({"CM85": left, "CM33": right})
                touching = self.ranges("CM33", bus0 + 4, local1 + 4)
                verifier.disjoint({"CM85": left, "CM33": touching})


if __name__ == "__main__":
    unittest.main()
