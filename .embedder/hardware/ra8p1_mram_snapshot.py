"""Symbols-only debugger readback of the entire code MRAM before and after the scratch test."""
import hashlib
import json
from pathlib import Path

ROOT = Path('validation/ek-ra8p1')
ELF = ROOT / 'ek_ra8p1_cpu0/Debug/ek_ra8p1_cpu0.elf'
EVIDENCE = ROOT / 'evidence'
BASE, SCRATCH, END = 0x02000000, 0x0207F800, 0x02100000
BLOCK_SIZE = 0x800


def main():
    phase = globals().get('capture_profile', {}).get('phase')
    result = {'success': False, 'data': {'phase': phase}}
    data = result['data']
    try:
        if phase not in ('preflight', 'diagnostic', 'before', 'pattern', 'blank'):
            raise ValueError('Expected preflight, diagnostic, before, pattern or blank')
        path = EVIDENCE / f'mram-{phase}.json'
        if path.exists():
            raise RuntimeError(f'Refusing to overwrite {path}')
        connection = gdb.jlink_connect('R7KA8P1KF_CPU0', str(ELF), attach=True, enable_rtt=False)
        data['connection'] = connection
        if not connection.get('ok') or gdb.status().get('halted') is not True:
            raise RuntimeError('Could not establish symbols-only CPU0 halt')
        gdb.execute('set code-cache off')
        gdb.execute('set stack-cache off')
        for name, width, address in (
            ('cpu1actcsr', 'h', 0x4000F064), ('sas', 'w', 0x02C9F074),
            ('cmsamon', 'w', 0x40204030), ('bps_sec7', 'w', 0x02C9F21C),
            ('pbps_sec1', 'w', 0x02E17704),
            ('mrcpc0', 'h', 0x4013F000), ('mrcpc1', 'h', 0x4013F004),
            ('mrcbprot0', 'h', 0x4013F008), ('mrcbprot1', 'h', 0x4013F00C),
            ('mrcps', 'b', 0x4013F010), ('ofs0', 'w', 0x02C9F040), ('wdtsr', 'h', 0x40202604),
            ('mre_zs', 'b', 0x4013C400), ('mastat', 'b', 0x4013E010),
            ('mctrstatr', 'b', 0x4013E06C), ('mstatr', 'w', 0x4013E080), ('mentryr', 'h', 0x4013E084),
            ('mrcraes', 'b', 0x4013C018), ('mrceecc', 'h', 0x4013F804), ('mrcdecc', 'h', 0x4013C010),
        ):
            data[name] = gdb.execute(f'x/{width}x {address:#x}').strip().split()[-1]
        if int(data['cpu1actcsr'], 16) & 0x81:
            raise RuntimeError('CPU1 is active or activation requested')
        cms = (int(data['cmsamon'], 16) >> 15) & 0x1ff
        if (cms not in (*range(16, 33), 0x1ff) or
                any(not int(data[key], 16) & 0x80000000 for key in ('bps_sec7', 'pbps_sec1'))):
            raise RuntimeError('Scratch block security attribution or protection does not permit this test')
        if int(data['mrcps'], 16) != 0x20 or any(int(data[key], 16) for key in
                ('mrcpc0', 'mrcpc1', 'mrcbprot0', 'mrcbprot1')):
            raise RuntimeError('Unexpected code MRAM sequencer or protection state')
        scratch = gdb.read_memory(SCRATCH, BLOCK_SIZE)
        if len(scratch) != BLOCK_SIZE:
            raise RuntimeError('Incomplete scratch readback')
        (EVIDENCE / f'mram-{phase}-scratch.bin').write_bytes(scratch)
        data['scratch_sha256'] = hashlib.sha256(scratch).hexdigest()
        data['scratch_nonblank_bytes'] = sum(x != 0xff for x in scratch)
        if phase not in ('preflight', 'diagnostic'):
            data['outside_ranges'] = []
            for start, stop in ((BASE, SCRATCH), (SCRATCH + BLOCK_SIZE, END)):
                digest = hashlib.sha256()
                for address in range(start, stop, 0x4000):
                    length = min(stop - address, 0x4000)
                    block = gdb.read_memory(address, length)
                    if len(block) != length:
                        raise RuntimeError(f'Incomplete code readback at {address:#x}')
                    digest.update(block)
                data['outside_ranges'].append({'start': hex(start), 'end': hex(stop), 'sha256': digest.hexdigest()})
            if phase != 'before':
                baseline = json.loads((EVIDENCE / 'mram-before.json').read_text())
                if not baseline['success'] or baseline['data']['outside_ranges'] != data['outside_ranges']:
                    raise RuntimeError('Outside-block code MRAM changed')
        if phase == 'pattern':
            expected = bytes((0xa5 ^ (i & 0xff) ^ (0x1d * (i >> 8))) & 0xff for i in range(BLOCK_SIZE))
            if scratch != expected:
                raise RuntimeError('Full debugger readback did not match the expected pattern')
        if phase == 'blank' and scratch != bytes([0xff]) * BLOCK_SIZE:
            raise RuntimeError('Cleanup readback is not blank')
        if phase == 'before' and scratch != (EVIDENCE / 'scratch-before-boot.bin').read_bytes():
            raise RuntimeError('Scratch changed since the original snapshot')
        result['success'] = True
        result['summary'] = f'MRAM {phase} readback complete'
    except Exception as error:
        result['summary'] = str(error)
    finally:
        if data.get('connection', {}).get('ok'):
            try:
                if gdb.status().get('halted') is True:
                    gdb.resume()
                if gdb.status().get('running') is not True:
                    raise RuntimeError('CPU0 did not resume after readback')
            except Exception as error:
                result['success'] = False
                result['summary'] = f'{result["summary"]}; {error}'
        if phase in ('preflight', 'diagnostic', 'before', 'pattern', 'blank'):
            path = EVIDENCE / f'mram-{phase}.json'
            if not path.exists():
                path.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
