"""Take two short onboard MIC1 captures and retain the firmware's UART evidence."""
import asyncio
import json
from pathlib import Path
import re
import time

PORT = '/dev/cu.usbmodem0010808410141'


async def main():
    path = Path(f'validation/ek-ra8p1/evidence/pdm-uart-{time.time_ns()}.json')
    data = {'transcript': str(path), 'captures': []}
    success = False
    try:
        for _ in range(2):
            serial_read_history(PORT, only_new=True)
            serial_send(PORT, 'pdm')
            await serial_read(PORT, timeout_seconds=4, stop_string='ACK pdm')
            lines = [line.strip() for line in serial_read_history(PORT, only_new=True)]
            data['captures'].append(lines)
            if 'PDM PASS' not in lines or 'ACK pdm' not in lines or any('PDM FAIL' in line for line in lines):
                raise RuntimeError('PDM firmware did not report a valid capture and cleanup')
            statuses = [dict(re.findall(r'(\w+)=([^\s]+)', line)) for line in lines if 'samples=' in line]
            if len(statuses) != 1:
                raise RuntimeError('Missing or ambiguous PDM status line')
            values = statuses[0]
            for key, want in {'samples': 2048, 'complete': 1, 'errors': 0, 'overruns': 0, 'flags': 0,
                              'timeout': 0}.items():
                if int(values[key], 0) != want:
                    raise RuntimeError(f'PDM {key} not {want}')
        success = True
        summary = 'Two non-constant MIC1 captures, 2048 samples each, with no errors or overruns'
    except Exception as error:
        summary = f'{type(error).__name__}: {error}'
    result = {'success': success, 'summary': summary, 'data': data}
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
