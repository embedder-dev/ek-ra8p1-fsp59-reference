"""Arm the installed analog fixture once and retain the complete UART transcript."""

import asyncio
import json
from pathlib import Path
import time

PORT = '/dev/cu.usbmodem0010808410141'


async def main():
    directory = Path('validation/ek-ra8p1/evidence')
    path = directory / f'analog-uart-{time.time_ns()}.log'
    lines = []
    status = 'No final analog verdict'
    success = False
    try:
        serial_read_history(PORT, only_new=True)
        serial_send(PORT, 'analog')
        await serial_read(PORT, timeout_seconds=10, stop_string='ACK analog')
        lines = serial_read_history(PORT, only_new=True)
        levels = sum(line.startswith('ANALOG level ') for line in lines)
        ramp = sum(line.startswith('ANALOG ramp i=') for line in lines)
        success = ('ANALOG PASS' in [line.strip() for line in lines] and levels == 5 and ramp == 33
                   and not any(line.startswith('ANALOG FAIL') for line in lines))
        status = f'{levels} level rows and {ramp} ramp rows'
    except Exception as error:
        status = str(error)
    finally:
        path.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'success': success, 'summary': status,
                      'data': {'transcript': str(path), 'uart': lines}}))


if __name__ == '__main__':
    asyncio.run(main())
