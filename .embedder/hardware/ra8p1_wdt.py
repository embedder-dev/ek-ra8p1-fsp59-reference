"""Observe the one-shot WDT0 test over VCOM, without a debugger connection."""
import asyncio
import json
from pathlib import Path
import re
import time

PORT = '/dev/cu.usbmodem0010808410141'


async def main():
    path = Path(f'validation/ek-ra8p1/evidence/wdt-uart-{time.time_ns()}.json')
    data = {'transcript': str(path), 'events': []}
    origin = time.monotonic()

    async def until(marker, seconds):
        start = len(data['events'])
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            await serial_read(PORT, timeout_seconds=min(0.15, remaining),
                              stop_string='\n')
            for line in serial_read_history(PORT, only_new=True):
                data['events'].append({'time_s': round(time.monotonic() - origin, 4), 'line': line.strip()})
            lines = data['events'][start:]
            if any(event['line'].startswith(('WDT BLOCK', 'WDT FAIL')) for event in lines):
                raise RuntimeError(lines[-1]['line'])
            if any(event['line'] == marker for event in lines):
                return lines
        raise TimeoutError(f'Did not see {marker}')

    success = False
    try:
        if globals().get('capture_profile', {}).get('power_cycled_no_debug') is not True:
            raise RuntimeError('Standalone cold power cycle with no debugger is required')
        serial_read_history(PORT, only_new=True)
        serial_send(PORT, 'wdt')
        before = await until('ACK wdt', 2.0)
        if not any(re.fullmatch(r'WDT BOOT RSTSR1=[0-9a-f]{8} WDT0RF=0', e['line']) for e in before):
            raise RuntimeError('Missing clear pre-arm WDT0 reset cause')
        serial_send(PORT, 'wdt-arm')
        trial = await until('READY', 16.0)
        lines = [e['line'] for e in trial]
        starts = [i for i, line in enumerate(lines) if line.startswith('WDT START ')]
        refreshes = [(i, re.fullmatch(r'WDT REFRESH n=([1-7]) count=([0-9a-f]{4}) reload=([0-9a-f]{4})', line))
                     for i, line in enumerate(lines) if line.startswith('WDT REFRESH ')]
        stops = [i for i, line in enumerate(lines) if line.startswith('WDT STOP ')]
        resets = [i for i, line in enumerate(lines)
                  if re.fullmatch(r'WDT BOOT RSTSR1=[0-9a-f]{8} WDT0RF=1', line)]
        if (len(starts) != 1 or len(refreshes) != 7 or len(stops) != 1 or
                len(resets) != 1 or not starts[0] < refreshes[0][0] < refreshes[-1][0] < stops[0] < resets[0]):
            raise RuntimeError('Missing or out-of-order WDT0 events')
        for n, (_, match) in enumerate(refreshes, 1):
            if (not match or int(match[1]) != n or not 0x6ff <= int(match[2], 16) <= 0x7ff or
                    not 0xf00 <= int(match[3], 16) <= 0xfff):
                raise RuntimeError('Refresh count or post-refresh reload outside expected range')
        data['refresh_phase_s'] = trial[stops[0]]['time_s'] - trial[starts[0]]['time_s']
        data['stop_to_reset_report_s'] = trial[resets[0]]['time_s'] - trial[stops[0]]['time_s']
        if data['refresh_phase_s'] < 3 * 2.796 or not 2.50 <= data['stop_to_reset_report_s'] <= 3.50:
            raise RuntimeError('UART-observed timing inconsistent with 2.796 s timeout')
        await serial_read(PORT, timeout_seconds=3.0)
        extra = serial_read_history(PORT, only_new=True)
        data['recovery_observation'] = extra
        if any(line.strip() for line in extra):
            raise RuntimeError('Unexpected console output during unarmed recovery')
        serial_send(PORT, 'wdt')
        after = await until('ACK wdt', 2.0)
        if not any(e['line'].endswith('WDT0RF=1') for e in after):
            raise RuntimeError('Missing WDT0 reset cause after recovery')
        success = True
        summary = 'Seven in-window reloads over three timeouts, WDT0 reset cause and unarmed recovery'
    except Exception as error:
        summary = f'{type(error).__name__}: {error}'
    result = {'success': success, 'summary': summary, 'data': data}
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
