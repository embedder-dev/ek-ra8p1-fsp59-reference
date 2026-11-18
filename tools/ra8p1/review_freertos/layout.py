"""Small stack-instruction interpreter, not an ARM core/runtime emulator.

Consumes the production basic-assembly strings; its independent oracle is the ABI
register order, per-task EXC_RETURN, and the Arm TRM's SP-only limit guarantee.
"""
import re


def register_list(value):
    result = []
    for entry in value.upper().replace(" ", "").split(","):
        if "-" in entry:
            first, last = entry.split("-")
            result += [first[0] + str(i) for i in range(int(first[1:]), int(last[1:]) + 1)]
        else:
            result.append(entry)
    return result


def execute(assembly, regs, memory):
    lines = [line.strip().upper() for line in assembly.splitlines() if line.strip()]
    labels = {line[:-1]: i for i, line in enumerate(lines) if line.endswith(":")}
    zero, pc, saved = False, 0, None
    while pc < len(lines):
        line = lines[pc]
        pc += 1
        if line.startswith("BL      VTASKSWITCHCONTEXT"):
            break
        match = re.fullmatch(r"(V?STM(?:DB|IA)|V?LDMIA)(EQ)?\s+R2!,\s*\{(.*)\}", line)
        if match:
            operation, predicate, names = match.groups()
            if predicate and not zero:
                continue
            names = register_list(names)
            store = "STM" in operation
            if "DB" in operation:
                regs["R2"] -= 4 * len(names)
            address = regs["R2"]
            for name in names:
                if store:
                    memory[address] = regs[name]
                else:
                    regs[name] = memory[address]
                address += 4
            if "DB" not in operation:
                regs["R2"] = address
            continue
        match = re.fullmatch(r"MRS\s+(R\d+),\s*(PSP|PSPLIM)", line)
        if match:
            regs[match[1]] = regs[match[2]]
            continue
        match = re.fullmatch(r"MSR\s+(PSP|PSPLIM),\s*(R\d+)", line)
        if match:
            regs[match[1]] = regs[match[2]]
            continue
        match = re.fullmatch(r"MOV\s+(R\d+|LR),\s*(R\d+|LR)", line)
        if match:
            regs[match[1]] = regs[match[2]]
            continue
        match = re.fullmatch(r"(SUBS|ADDS)\s+R2,\s*R2,\s*#(\d+)", line)
        if match:
            regs["R2"] += int(match[2]) * (-1 if match[1] == "SUBS" else 1)
            continue
        match = re.fullmatch(r"TST\s+LR,\s*#(0X[0-9A-F]+)", line)
        if match:
            zero = not (regs["LR"] & int(match[1], 0))
            continue
        match = re.fullmatch(r"CBZ\s+R0,\s*(\w+)", line)
        if match and regs["R0"] == 0:
            pc = labels[match[1]]
            continue
        match = re.fullmatch(r"BNE\s+(\w+)", line)
        if match and not zero:
            pc = labels[match[1]]
            continue
        if re.fullmatch(r"STR\s+R2,\s*\[R1\]", line):
            saved = regs["R2"]
    return saved


def verify(save, restore, *, fpu, nonsecure, active_fp=False, secure_frame=False):
    top, limit = 0x20001000, 0x20000000
    exc_return = 0xFFFFFFBC if nonsecure else 0xFFFFFFFD
    if active_fp:
        exc_return &= ~0x10
    if secure_frame:
        exc_return |= 0x40
    regs = {"R" + str(i): 0x1000 + i for i in range(13)}
    regs.update({"S" + str(i): 0xF000 + i for i in range(16, 32)})
    regs.update(PSP=top, PSPLIM=limit, LR=exc_return, R0=(5 if secure_frame else 0))
    initial = dict(regs)
    memory = {}
    start = re.search(r"MRS\s+R2,\s*PSP", save).start()
    saved = execute(save[start:], regs, memory)
    header = [initial["R0"], limit, exc_return] if nonsecure else [limit]
    gprs = [initial["R" + str(i)] for i in range(4, 12)]
    expected = header + ([] if secure_frame else gprs + ([] if nonsecure else [exc_return]))
    if active_fp and not secure_frame:
        expected += [initial["S" + str(i)] for i in range(16, 32)]
    assert saved == top - len(expected) * 4, (hex(saved), len(expected))
    assert [memory.get(saved + 4 * i) for i in range(len(expected))] == expected
    # Restore uses the per-task metadata before integer/optional FP registers.
    restored = {name: 0xBAD for name in initial}
    restored.update(R2=saved, R0=initial["R0"])
    start = re.search(r"LDMIA\s+R2!,", restore).start()
    execute(restore[start:], restored, memory)
    assert restored["PSPLIM"] == limit
    assert restored["PSP"] == top
    assert restored["LR"] == exc_return
    if not secure_frame:
        for name in ["R" + str(i) for i in range(4, 12)]:
            assert restored[name] == initial[name], name
        if active_fp:
            for name in ["S" + str(i) for i in range(16, 32)]:
                assert restored[name] == initial[name], name
