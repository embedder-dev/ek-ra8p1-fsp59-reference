"""Execute exactly one guarded scratch command and retain its UART evidence."""
import asyncio
import json
from pathlib import Path
import time

EVIDENCE = Path('validation/ek-ra8p1/evidence')
PORT = '/dev/cu.usbmodem0010808410141'
ORACLES = {
    'arm': ('MRAM ARMED 0207f800..02080000; no writes',),
    'write': ('MRAM ERASE verified 2048 bytes of ff',
              'MRAM WRITE verified 2048 bytes; awaiting host readback'),
    'resume': ('MRAM RESUMED verified pattern; cleanup only; no writes',),
    'clean': ('MRAM CLEAN verified 2048 bytes of ff',),
}


def require_snapshot(phase):
    if not json.loads((EVIDENCE / f'mram-{phase}.json').read_text())['success']:
        raise RuntimeError(f'MRAM {phase} debugger snapshot did not pass')


async def main():
    phase = globals().get('capture_profile', {}).get('phase')
    result = {'success': False, 'data': {'phase': phase, 'uart': []}}
    path = EVIDENCE / f'mram-uart-{time.time_ns()}.json'
    result['data']['transcript'] = str(path)
    try:
        expected = ORACLES[phase]
        require_snapshot('before' if phase in ('arm', 'write') else 'pattern')
        cmd = f'mram-{phase}'
        ack = f'ACK {cmd}'
        serial_read_history(PORT, only_new=True)
        serial_send(PORT, cmd)
        await serial_read(PORT, timeout_seconds=3.0, stop_string=ack)
        lines = [line.strip() for line in serial_read_history(PORT, only_new=True)]
        result['data']['uart'] = lines
        if any(line.startswith(('MRAM BLOCK', 'MRAM FAIL')) for line in lines):
            raise RuntimeError(next(line for line in lines if line.startswith(('MRAM BLOCK', 'MRAM FAIL'))))
        if ack not in lines or any(not any(line.startswith(marker) for line in lines) for marker in expected):
            raise RuntimeError(f'Incomplete {cmd} response')
        result['success'] = True
        result['summary'] = f'{cmd} confirmed by firmware'
    except Exception as error:
        result['summary'] = str(error)
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
