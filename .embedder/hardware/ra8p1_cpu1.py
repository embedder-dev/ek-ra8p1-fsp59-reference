"""Verify CPU0 activated CPU1, then observe CPU1-owned TCM using symbols-only attaches."""
import asyncio
import json
from pathlib import Path
import time

ROOT = Path('validation/ek-ra8p1')
PORT = '/dev/cu.usbmodem0010808410141'


def attach(core, build):
    name = f'ek_ra8p1_cpu{core}'
    elf = ROOT / 'evidence' / build / f'{name}.elf'
    link = gdb.jlink_connect(f'R7KA8P1KF_CPU{core}', str(elf), attach=True, enable_rtt=False)
    if not link.get('ok') or gdb.status().get('halted') is not True:
        raise RuntimeError(f'Could not inspect CPU{core} via symbols-only attach')
    return link


def read(width, address):
    return int(gdb.execute(f'x/{width}x {address:#x}').strip().split()[-1], 16)


def resume():
    if gdb.status().get('halted') is True:
        gdb.resume()
    if gdb.status().get('running') is not True:
        raise RuntimeError('Resume not confirmed')


def main():
    profile = globals().get('capture_profile', {})
    build = profile.get('build', 'r020-pair-build')
    phase = profile.get('phase', 'standalone')
    data = {'build': build, 'phase': phase}
    success = False
    attached = False
    try:
        if build not in ('r020-pair-build', 'r020-concurrent-build', 'r021-paired-build') or phase not in (
                'standalone', 'before', 'after'):
            raise ValueError('Unknown paired fixture or phase')
        data['cpu0_attach'] = attach(0, build)
        attached = True
        data['cpu1actcsr_before_cpu1_attach'] = hex(read('h', 0x4000F064))
        data['cpu1initvtor'] = hex(read('w', 0x4000F044))
        data['cpu1waitcr'] = hex(read('b', 0x4000F054))
        if (int(data['cpu1actcsr_before_cpu1_attach'], 16) & 0x80 == 0 or
                int(data['cpu1initvtor'], 16) != 0x02080000 or int(data['cpu1waitcr'], 16) & 1):
            raise RuntimeError('CPU0 did not establish CPU1 active with the expected vector base and wait state')
        resume()
        gdb.disconnect()
        attached = False
        data['cpu1_attach'] = attach(1, build)
        attached = True
        data['cpuid'] = hex(read('w', 0xE000ED00))
        data['cpu1_vtor'] = hex(read('w', 0xE000ED08))
        data['pc'] = gdb.read_register('pc')
        address = int(gdb.eval('(unsigned int)&g_cpu1_counter'), 0)
        data['counter_address'] = hex(address)
        if ((int(data['cpuid'], 16) >> 4) & 0xfff != 0xd21 or
                int(data['cpu1_vtor'], 16) != 0x02080000 or not 0x20000000 <= address <= 0x20002000 - 4):
            raise RuntimeError('Unexpected Cortex-M33 identity, vector base or counter address')
        first = read('w', address)
        resume()
        time.sleep(0.25)  # Allow multiple 10 ms foreground heartbeat intervals.
        stopped = gdb.interrupt()
        if stopped.get('timed_out') or gdb.status().get('halted') is not True:
            raise RuntimeError('Could not sample CPU1 heartbeat again')
        second = read('w', address)
        data['counter_samples'] = [hex(first), hex(second)]
        if not 0xc3310000 <= first < second < 0xc3320000:
            raise RuntimeError('CPU1-owned counter did not advance')
        resume()
        gdb.disconnect()
        attached = False
        serial_read_history(PORT, only_new=True)
        serial_send(PORT, 'clocks')
        asyncio.run(serial_read(PORT, timeout_seconds=2.0, stop_string='ACK clocks'))
        data['cpu0_uart_after_cpu1_attach'] = serial_read_history(PORT, only_new=True)
        if not any(line.strip() == 'ACK clocks' for line in data['cpu0_uart_after_cpu1_attach']):
            raise RuntimeError('CPU0 did not acknowledge clocks after CPU1 activity')
        success = True
        summary = 'CPU0 started Cortex-M33; CPU1 heartbeat advanced with CPU0 console alive'
    except Exception as error:
        summary = str(error)
    finally:
        if attached:
            try:
                resume()
            except Exception as error:
                summary = f'{summary}; resume failed: {error}'
                success = False
    result = {'success': success, 'summary': summary, 'data': data}
    evidence = ROOT / 'evidence' / f'cpu1-live-{time.time_ns()}.json'
    evidence.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
