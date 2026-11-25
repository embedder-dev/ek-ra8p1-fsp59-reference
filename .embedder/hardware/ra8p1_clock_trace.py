"""Read-only MMIO at hardware breakpoints in the already programmed CPU0 ELF."""

import hashlib
import json
from pathlib import Path

ELF = 'validation/ek-ra8p1/ek_ra8p1_cpu0/Debug/ek_ra8p1_cpu0.elf'
REGS = {'sckdivcr': (0x4001E020, 4), 'sckdivcr2': (0x4001E024, 2),
        'sckscr': (0x4001E026, 1), 'prcr_s': (0x4001E3FA, 2),
        'mrcfreq': (0x4013C004, 4), 'mrefreq': (0x4013C008, 4),
        'vscr': (0x4001E014, 1), 'mosccr': (0x4001E032, 1), 'oscsf': (0x4001E03C, 1)}


def state():
    return {name: f'0x{int.from_bytes(gdb.read_memory(address, width), "little"):x}'
            for name, (address, width) in REGS.items()}


def register(name):
    # The bridge can return bare decimal values for general registers.
    return int(gdb.read_register(name).split()[0], 0)


def run():
    trace = {}
    try:
        trace['connection'] = gdb.jlink_connect(device='R7KA8P1KF_CPU0', elf=ELF,
                                               attach=True, enable_rtt=False)
        trace['reset'] = gdb.reset('default')
        checkpoints = globals().get('capture_profile', {}).get('checkpoints')
        if checkpoints:
            trace['checkpoints'] = []
            if profile := globals().get('capture_profile', {}).get('qualification'):
                hashes = {'pdm-r020': '70047b64b024918fcb912497a1719ca33cb69b6af129f2d73cd7534e29439824',
                          'concurrent-r020': '43aecd9d415ba26df1b35e8247980e2e817fb6e830dd161f709996b1a8a5a07e'}
                if hashlib.sha256(Path(ELF).read_bytes()).hexdigest() != hashes.get(profile):
                    raise ValueError('Qualification checkpoints require an audited r020 PDM ELF')
                allowed = {0x02003aea, 0x02003afa, 0x02003b02, 0x02003b06, 0x02003b08, 0x02003b14,
                           0x02003b1c, 0x02003b20, 0x02003b2e, 0x020036b8, 0x02003b32}
            else:
                # Instruction boundaries in the audited r019 boot ELF.
                allowed = {0x02001b76, 0x02001b7a, 0x02001b7e, 0x02001bae, 0x02001bb2,
                           0x02001bba, 0x02001bc6, 0x02001bc8, 0x02001bd4, 0x02001bee, 0x02001bf2}
            for address in checkpoints:
                if address not in allowed:
                    raise ValueError('Checkpoint is not a reviewed instruction address')
                gdb.execute(f'thbreak *{address:#x}')
                stop = gdb.continue_until_break(timeout_seconds=8)
                reached = not stop.get('timed_out') and register('pc') == address
                trace['checkpoints'].append({'wanted': hex(address), 'stop': stop, 'state': state(),
                                             'registers': {name: hex(register(name)) for name in
                                                           ('r0', 'r1', 'r2', 'r6', 'lr')},
                                             'faults': gdb.execute('x/2wx 0xe000ed28'),
                                             'core_ccr': gdb.execute('x/wx 0xe000ed14'),
                                             'core_mscr': gdb.execute('x/wx 0xe001e000')})
                if not reached:
                    if not stop.get('timed_out'):
                        trace['exception_stack'] = gdb.execute('x/8wx $sp')
                        trace['backtrace'] = gdb.execute('bt 8')
                        # RA8P1 HM §§15.3.26, 15.3.30 and 60.5.43; preserve explicit MMIO widths.
                        trace['silicon'] = gdb.execute('x/bx 0x02c1ec48')
                        trace['bus_cpu0'] = gdb.execute('x/bx 0x40004a00')
                        trace['bus_buffered_write'] = gdb.execute('x/wx 0x40004b00')
                        trace['core_ccr'] = gdb.execute('x/wx 0xe000ed14')
                        trace['pll1_config'] = [gdb.execute(command) for command in
                                                ('x/wx 0x4001e0ac', 'x/hx 0x4001e04c', 'x/bx 0x4001e02a')]
                    raise RuntimeError(f'CPU0 did not reach {address:#x}')
            gdb.resume()
            print(json.dumps({'success': True, 'summary': 'Traced BSP startup checkpoints', 'data': trace}))
            return
        gdb.execute('thbreak *bsp_prv_clock_set')
        event = gdb.continue_until_break(timeout_seconds=8)
        trace['entry_event'] = event
        trace['first_stop'] = state()
        trace['first_registers'] = {name: hex(register(name)) for name in ('pc', 'lr', 'xpsr', 'sp')}
        trace['faults'] = gdb.execute('x/6wx 0xe000ed28')
        trace['stack_words'] = gdb.execute('x/16wx $sp')
        trace['backtrace'] = gdb.execute('bt 8')
        if event.get('timed_out') or event.get('event', {}).get('functionName') != 'bsp_prv_clock_set':
            raise RuntimeError('CPU0 did not stop at clock set entry')
        trace['entry'] = state()
        trace['args'] = [hex(register(f'r{i}')) for i in range(3)]
        address = register('lr') & ~1
        gdb.execute(f'thbreak *{address:#x}')
        event = gdb.continue_until_break(timeout_seconds=8)
        trace['return_event'] = event
        if event.get('timed_out') or register('pc') != address:
            raise RuntimeError('CPU0 did not reach the clock set return')
        trace['return'] = state()
        gdb.resume()
        print(json.dumps({'success': True, 'summary': 'Traced clock entry and return', 'data': trace}))
    except Exception as exc:
        print(json.dumps({'success': False, 'summary': str(exc), 'data': trace}))


if __name__ == '__main__':
    run()
