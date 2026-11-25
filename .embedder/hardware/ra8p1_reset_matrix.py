"""Verify repeated system resets of an audited r021 image, without startup breakpoints."""

import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path('validation/ek-ra8p1')
PORT = '/dev/cu.usbmodem0010808410141'
sys.path.insert(0, str(ROOT.resolve()))
from image_guard import audit_elf
from reset_oracle import check_transcript


async def run(profile, evidence):
    image_kind = profile.get('image', 'paired')
    if image_kind not in ('paired', 'standalone'):
        raise ValueError('Image must be paired or standalone')
    count = profile.get('count', 10)
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('Count must be a positive integer at most 50')
    elf = ROOT / 'evidence' / f'r021-{image_kind}-build' / 'ek_ra8p1_cpu0.elf'
    data = elf.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != profile.get('elf_sha256'):
        raise ValueError('The exact audited ELF digest is required')
    tags = re.findall(rb'BOOT EK-RA8P1 (r021 CPU0 [A-Za-z]{3} [ 0-9][0-9] [0-9]{4} [0-9:]{8})\r\n', data)
    if len(set(tags)) != 1:
        raise ValueError('ELF does not identify one r021 boot tag')
    tag = tags[0].decode('ascii')
    image = audit_elf(data, 'cpu0')
    evidence.update(elf_sha256=sha, build_tag=tag, image=image_kind, requested=count, trials=[])
    await serial_read(PORT, timeout_seconds=0.1)
    link = gdb.jlink_connect('R7KA8P1KF_CPU0', str(elf), attach=True, enable_rtt=False)
    if not link.get('ok') or gdb.status().get('halted') is not True:
        raise RuntimeError('Could not establish a symbols-only halt')
    for section in image.sections:
        if gdb.read_memory(section.lma, len(section.data)) != section.data:
            raise RuntimeError(f'Target bytes differ from the audited ELF at {section.lma:#010x}')
    evidence['readback_match'] = True
    for index in range(1, count + 1):
        status = gdb.reset('default')
        trial = {'index': index, 'reset': status, 'start_ns': time.monotonic_ns()}
        evidence['trials'].append(trial)
        if not status.get('ok') or status.get('halted') is not True:
            raise RuntimeError(f'Reset {index} did not establish a halt')
        serial_read_history(PORT, only_new=True)
        # Capture history after resume: UART can finish before the blocking read subscribes.
        gdb.resume()
        await serial_read(PORT, timeout_seconds=0.7, stop_string='READY')
        lines = serial_read_history(PORT, only_new=True)
        trial['uart'] = lines
        trial['oracle'] = check_transcript('\n'.join(lines), build_tag=tag,
                                           cpu1='active' if image_kind == 'paired' else 'inactive')
        if not trial['oracle']['success']:
            raise RuntimeError(f'Reset {index} failed strict clock/boot acceptance: ' +
                               '; '.join(trial['oracle']['errors']))
    gdb.disconnect()


if __name__ == '__main__':
    path = ROOT / 'evidence' / f'r021-system-resets-{time.time_ns()}.json'
    data = {}
    try:
        asyncio.run(run(globals().get('capture_profile', {}), data))
        success = True
        summary = f"{len(data['trials'])} system resets matched the clock and boot profile"
    except Exception as error:
        success = False
        summary = f'{type(error).__name__}: {error}'
    with path.open('x') as stream:
        json.dump({'success': success, 'summary': summary, 'data': data}, stream, indent=2)
    print(json.dumps({'success': success, 'summary': summary, 'data': {'evidence': str(path)}}))
