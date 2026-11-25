"""Read WDT0 boot and OCD state without programming or changing any register."""
import json
from pathlib import Path


out = Path('validation/ek-ra8p1/evidence/wdt-clock-preflight.json')
data = {}
try:
    data['connection'] = gdb.jlink_connect(
        'R7KA8P1KF_CPU0',
        'validation/ek-ra8p1/ek_ra8p1_cpu0/Debug/ek_ra8p1_cpu0.elf',
        attach=True, no_halt=True, enable_rtt=False)
    if not data['connection'].get('ok'):
        raise RuntimeError('symbols-only attach failed')
    for name, fmt, address in (
        ('ofs0', 'wx', 0x02C9F040), ('dbgstopcr', 'wx', 0x4001B010),
        ('dhcsr', 'wx', 0xE000EDF0), ('rstsr1', 'wx', 0x4001E0C0),
        ('cpu1actcsr', 'hx', 0x4000F064), ('sckdivcr', 'wx', 0x4001E020),
        ('sckdivcr2', 'hx', 0x4001E024), ('mrcfreq', 'wx', 0x4013C004),
        ('mrefreq', 'wx', 0x4013C008),
    ):
        data[name] = gdb.execute(f'x/{fmt} {address:#x}').strip().split()[-1]
    data['register_start'] = bool(int(data['ofs0'], 16) & (1 << 17))
    data['ocd_wdt0_masked'] = bool(int(data['dbgstopcr'], 16) & 2)
    data['debug_enabled'] = bool(int(data['dhcsr'], 16) & 1)
    data['wdt0_reset_flag'] = bool(int(data['rstsr1'], 16) & 2)
    state = gdb.status()
    if state.get('halted') is True:
        gdb.resume()
    data['final_status'] = gdb.status()
    success = data['final_status'].get('running') is True
    summary = 'Read WDT0 and MRAM clock preflight; did not arm'
except Exception as error:
    success = False
    summary = str(error)
result = {'success': success, 'summary': summary, 'data': data}
out.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
