"""Read programmed code and live CPU0 state without a reset or download."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path.cwd() / 'validation' / 'ek-ra8p1'
sys.path.insert(0, str(ROOT))
from image_guard import audit_elf  # noqa: E402

ELF = ROOT / 'ek_ra8p1_cpu0' / 'Debug' / 'ek_ra8p1_cpu0.elf'


def main():
    data = {}
    profile = globals().get('capture_profile', {})
    qualification = profile.get('qualification')
    try:
        if qualification not in (None, 'cold', 'button'):
            raise ValueError('Unknown qualification readback')
        elf = ROOT / 'evidence' / 'r020-pdm-build' / ELF.name if qualification else ELF
        content = elf.read_bytes()
        data['elf_sha256'] = hashlib.sha256(content).hexdigest()
        image = audit_elf(content, 'cpu0')
        data['connection'] = gdb.jlink_connect(device='R7KA8P1KF_CPU0', elf=str(elf),
                                              attach=True, enable_rtt=False)
        if qualification:
            data['qualification'] = qualification
        if profile.get('reset_halt') is True:
            data['reset'] = gdb.reset('default')
        data['status'] = gdb.status()
        if profile.get('reset_halt') is True and data['status'].get('halted') is not True:
            raise RuntimeError('Could not establish reset/halt state')
        data['pc'] = gdb.read_register('pc')
        data['fault_registers'] = gdb.execute('x/2wx 0xe000ed28')
        if data['pc'].endswith('<Default_Handler>'):
            data['backtrace'] = gdb.execute('bt 12')
            data['exception_stack'] = gdb.execute('x/16wx $sp')
            data['exception_return'] = gdb.read_register('lr')
        data['system_dividers'] = gdb.execute('x/wx 0x4001e020')
        if profile.get('timer') is True:
            data['timer_clock'] = {'source': gdb.execute('x/bx 0x4001e05d'),
                                   'divider': gdb.execute('x/bx 0x4001e05c'),
                                   'bypass': gdb.execute('x/wx 0x40323f10'),
                                   'module_stop': gdb.execute('x/wx 0x40203010')}
        data['readback'] = []
        for section in image.sections:
            actual = gdb.read_memory(section.lma, len(section.data))
            mismatch = next((section.lma + i for i, (x, y) in enumerate(zip(actual, section.data)) if x != y), None)
            data['readback'].append({'section': section.name, 'lma': hex(section.lma),
                                     'length': len(actual), 'sha256': hashlib.sha256(actual).hexdigest(),
                                     'first_mismatch': hex(mismatch) if mismatch is not None else None,
                                     'match': actual == section.data})
        success = all(row['match'] for row in data['readback'])
        if 'timer_clock' in data and success and not profile.get('reset_halt') and not data['pc'].endswith('<Default_Handler>'):
            gdb.resume()
        result = {'success': success, 'summary': 'Application MRAM readback (not a boot verdict)', 'data': data}
        if qualification:
            from time import time_ns
            evidence = ROOT / 'evidence' / f'qual-{qualification}-readback-{time_ns()}.json'
            evidence.write_text(json.dumps(result, indent=2) + '\n')
            data['evidence'] = str(evidence.relative_to(Path.cwd()))
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'success': False, 'summary': str(exc), 'data': data}))


if __name__ == '__main__':
    main()
