"""Render the new PDM MDF from its scoped, FSP-5.9-style contract (no IDE calls)."""
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_pdm####5.9.0.xml"
P = "module.driver.pdm."
N = "${module.driver.pdm.name}"


def render():
    root = ET.Element("raModuleDescription")
    config = ET.SubElement(root, "config", id="config.driver.pdm", path="fsp_cfg/r_pdm_cfg.h", version="0")
    prop = ET.SubElement(config, "property", id="config.driver.pdm.param_checking_enable",
                         default="config.driver.pdm.param_checking_enable.bsp", display="Parameter Checking")
    for key, label, value in (("bsp", "Default (BSP)", "BSP_CFG_PARAM_CHECKING_ENABLE"),
                               ("enabled", "Enabled", "1"), ("disabled", "Disabled", "0")):
        ET.SubElement(prop, "option", id="config.driver.pdm.param_checking_enable." + key,
                      display=label, value=value)
    ET.SubElement(config, "content").text = "\n#define PDM_CFG_PARAM_CHECKING_ENABLE (${config.driver.pdm.param_checking_enable})\n"
    mod = ET.SubElement(root, "module", id="module.driver.pdm_on_pdm", config="config.driver.pdm",
                        display="Audio|${module.driver.pdm.name} PDM (r_pdm)", version="0", url="group___p_d_m.html")

    def constraint(label, text, parent=mod):
        ET.SubElement(parent, "constraint", display=label).text = text

    constraint("Unique name required for each instance", '"${interface.driver.pdm.${module.driver.pdm.name}}" === "1"')
    constraint("Processing channel already in use", '"${interface.driver.pdm.channel.${module.driver.pdm.channel}}" === "1"')
    constraint("Requires PDM peripheral", '"${interface.mcu.pdm}" === "1"')
    constraint("Processing channel unavailable", '"${interface.mcu.pdm.${module.driver.pdm.channel}}" === "1"')
    constraint("Physical input must match channel and edge (falling channel 0 wraps to input 2)",
               '(Number("${module.driver.pdm.physical_input}") === '
               '((Number("${module.driver.pdm.channel}") + '
               '("${module.driver.pdm.input}" === "module.driver.pdm.input.falling" ? 2 : 0)) % 3))')
    # Source signature contains only table50.18 mandatory configurable settings.
    # Clock-divider encodings 12/13 and 14/15 yield identical M/range (table50.7);
    # the falling channel's own CKDIV is unused, so those pairs are interchangeable.
    source_prefix = "interface.driver.pdm.stereo.${module.driver.pdm.physical_input}.module.driver.pdm.input.rising.${module.driver.pdm.sinc_order}."
    source_suffix = ".${module.driver.pdm.fifo_threshold}"

    def source_present(div):
        return '"${' + source_prefix + div + source_suffix + '}" === "1"'

    stereo = '"${module.driver.pdm.input}" !== "module.driver.pdm.input.falling" || ('
    stereo += source_present("${module.driver.pdm.clock_div}")
    for pair in ((12, 13), (14, 15)):
        ids = [P + "clock_div." + str(div) for div in pair]
        stereo += ' || (("${module.driver.pdm.clock_div}" === "' + ids[0] + '" || '
        stereo += '"${module.driver.pdm.clock_div}" === "' + ids[1] + '") && ('
        stereo += source_present(ids[0]) + " || " + source_present(ids[1]) + "))"
    stereo += ")"
    constraint("Falling stereo requires a rising source with matched sinc mode, decimation/range and FIFO threshold", stereo)
    constraint("PDMIF bus clock PCLKB must be 1 to 62.5 MHz", 
               '(Number("${board.clock.peripheral.pdm}") >= 1000000) && '
               '(Number("${board.clock.peripheral.pdm}") <= 62500000)')
    ET.SubElement(mod, "requires", id=P + "requires.pdm", interface="interface.mcu.pdm",
                  visible="false", display="Requires PDM peripheral")
    for iface in ("interface.driver.pdm", "interface.driver.pdm_on_pdm", "interface.driver.pdm." + N,
                   "interface.driver.pdm.channel.${module.driver.pdm.channel}",
                   "interface.driver.pdm.stereo.${module.driver.pdm.channel}.${module.driver.pdm.input}.${module.driver.pdm.sinc_order}.${module.driver.pdm.clock_div}.${module.driver.pdm.fifo_threshold}"):
        ET.SubElement(mod, "provides", interface=iface)

    def integer(key, label, default, low, high):
        prop = ET.SubElement(mod, "property", id=P + key, default=str(default), display=label)
        ref = "${" + P + key + "}"
        constraint(f"{label}: integer {low} to {high} required",
                   f'testInteger("{ref}") && (Number("{ref}") >= {low}) && (Number("{ref}") <= {high})', prop)
        return prop

    def choice(key, label, options, default):
        prop = ET.SubElement(mod, "property", id=P + key, default=P + key + "." + default, display=label)
        for key2, value, text in options:
            ET.SubElement(prop, "option", id=P + key + "." + key2, display=text, value=str(value))
        return prop

    name = ET.SubElement(mod, "property", id=P + "name", display="Name", default="g_pdm${_instance}")
    constraint("Name must be a valid C symbol", 'testSymbol("${module.driver.pdm.name}")', name)
    channel = integer("channel", "Processing Channel", 2, 0, 2)
    channel.set("description", "Assign the entire PDMIF peripheral, shared clock and interrupts exclusively to one core. "
                "All instances and IRQ handlers run on that core; serialize API calls except documented callback-safe calls. "
                "Duplicate processing channels are rejected within this project only. Open's local IRQ-context/channel "
                "checks detect sequential duplicates, not atomic reservations; no cross-core synchronization is provided.")
    integer("physical_input", "Pins|Physical Input Channel", 2, 0, 2)
    input_prop = choice("input", "Input Edge", (("rising", "PDM_INPUT_RISING", "Rising (this physical input)"),
                                   ("falling", "PDM_INPUT_PREVIOUS_FALLING", "Falling (previous physical input)")), "rising")
    input_prop.set("description", "Falling stereo uses physical input CH(n-1), wrapping CH0 to CH2 (HM50.2.19). "
                   "Add the source instance in rising mode with matching sinc order, decimation/range and FIFO threshold. "
                   "Open the source first; stop/close the falling consumer first. The source supplies the clock; "
                   "the falling channel's CKDIV is unused. Shifts, word format and coefficients may differ.")
    choice("sample_format", "Output|FIFO Word Format", tuple(
        (str(value), symbol, label) for value, symbol, label in (
            (0, "PDM_SAMPLE_FORMAT_20_BITS", "20-bit, no shift"),
            (1, "PDM_SAMPLE_FORMAT_20_BITS_SHIFT1", "20-bit, right shift 1"),
            (2, "PDM_SAMPLE_FORMAT_20_BITS_SHIFT2", "20-bit, right shift 2"),
            (3, "PDM_SAMPLE_FORMAT_20_BITS_SHIFT3", "20-bit, right shift 3"),
            (8, "PDM_SAMPLE_FORMAT_16_BITS_18_4", "16-bit, sign and bits 18:4"),
            (9, "PDM_SAMPLE_FORMAT_16_BITS_17_3", "16-bit, sign and bits 17:3"),
            (10, "PDM_SAMPLE_FORMAT_16_BITS_16_2", "16-bit, sign and bits 16:2"),
            (11, "PDM_SAMPLE_FORMAT_16_BITS_15_1", "16-bit, sign and bits 15:1"),
            (12, "PDM_SAMPLE_FORMAT_16_BITS_14_0", "16-bit, sign and bits 14:0"))), "0")
    choice("clock_div", "Clock|PDM Clock Divider (8 MHz MOCO)",
           tuple((str(i), i, f"Divide by {2 * (i + 1)}") for i in range(16)), "0")
    choice("sinc_order", "Filter|Sinc Order (HM table 50.7 decimation and clipping)",
           tuple((str(i), i, str(i)) for i in range(1, 5)), "4")
    for key, label in (("high_pass_shift", "High-pass"), ("compensation_shift", "Compensation"),
                        ("low_pass_shift", "Low-pass")):
        choice(key, f"Filter|{label} Input Right Shift", tuple((str(i), i, str(i)) for i in range(4)), "0")
    choice("fifo_threshold", "Reception|FIFO Interrupt Threshold", tuple(
        (str(i), i, f"{1 << i} words") for i in range(5)), "4")
    integer("microphone_delay_us", "Clock|Additional Microphone Settling Time (us)", 0, 0, 1000000)
    coeff = ET.SubElement(mod, "property", id=P + "p_coefficients", display="Filter|Coefficient Structure",
                          default="NULL", description="NULL uses HM reset coefficients; otherwise name a const pdm_coefficients_t.")
    constraint("Coefficient structure must be a C symbol", 'testSymbol("${module.driver.pdm.p_coefficients}")', coeff)
    choice("error_enable", "Errors|Additional Detectors (FIFO overflow always enabled)",
           (("none", "0", "None"), ("short", "PDM_ERROR_SHORT_CIRCUIT", "Short-circuit"),
            ("limits", "PDM_ERROR_LOWER_LIMIT | PDM_ERROR_UPPER_LIMIT", "Lower and upper limits"),
            ("all", "PDM_ERROR_SHORT_CIRCUIT | PDM_ERROR_LOWER_LIMIT | PDM_ERROR_UPPER_LIMIT", "All")), "none")
    integer("short_circuit_low", "Errors|Short Circuit Low Limit", 0, 0, 8191)
    integer("short_circuit_high", "Errors|Short Circuit High Limit", 0, 0, 8191)
    integer("lower_limit", "Errors|Lower Limit (raw signed 20-bit)", "0x80000", 0, 1048575)
    integer("upper_limit", "Errors|Upper Limit (raw signed 20-bit)", "0x7FFFF", 0, 1048575)
    cb = ET.SubElement(mod, "property", id=P + "p_callback", default="NULL", display="Interrupts|Callback")
    constraint("Callback must be a valid C symbol", 'testSymbol("${module.driver.pdm.p_callback}")', cb)
    ET.SubElement(mod, "property", id=P + "p_context", default="NULL")
    ipl = ET.SubElement(mod, "property", id=P + "ipl", display="Interrupts|Data and Error Priority",
                        default="board.icu.common.irq.priority12")
    ET.SubElement(ipl, "select", enum="enum.mcu.nvic.priorities.mandatory")
    ET.SubElement(ipl, "interrupt", event="event.pdm${module.driver.pdm.channel}.dat", isr="pdm_dat_isr")
    ET.SubElement(ipl, "interrupt", event="event.pdm${module.driver.pdm.channel}.err", isr="pdm_err_isr")
    ET.SubElement(mod, "peripheral", name="PDM${module.driver.pdm.physical_input}",
                  component="pdm${module.driver.pdm.physical_input}")

    signatures = {
        "open": ("Open", "pdm_cfg_t const * const p_cfg", ""),
        "start": ("Start", "uint32_t * const p_buffer, uint32_t const samples", "p_buffer, samples"),
        "stop": ("Stop", "", ""),
        "status_get": ("StatusGet", "pdm_status_t * const p_status", "p_status"),
        "close": ("Close", "", ""),
        "callback_set": ("CallbackSet", "void (* p_callback)(pdm_callback_args_t *), void const * const p_context, pdm_callback_args_t * const p_callback_memory", "p_callback, p_context, p_callback_memory"),
    }
    for key in signatures:
        ET.SubElement(mod, "symbol", id=P + "guard." + key, value=N + "_" + key + "_guard")
    header = f"\nextern pdm_instance_t const {N};\nextern pdm_instance_ctrl_t {N}_ctrl;\nextern pdm_cfg_t const {N}_cfg;\n"
    header += "#ifndef ${module.driver.pdm.p_callback}\nvoid ${module.driver.pdm.p_callback}(pdm_callback_args_t * p_args);\n#endif\n"
    header += "#ifndef ${module.driver.pdm.p_coefficients}\nextern pdm_coefficients_t const ${module.driver.pdm.p_coefficients};\n#endif\n"
    ET.SubElement(mod, "header").text = header
    ET.SubElement(mod, "includes").text = '\n#include "r_pdm.h"\n'
    fields = ("input", "sample_format", "clock_div", "sinc_order", "high_pass_shift",
              "compensation_shift", "low_pass_shift", "fifo_threshold", "microphone_delay_us", "error_enable",
              "short_circuit_low", "short_circuit_high", "lower_limit", "upper_limit")
    decl = f"\npdm_instance_ctrl_t {N}_ctrl;\npdm_extended_cfg_t const {N}_ext_cfg =\n{{\n"
    decl += "".join(f"    .{key} = ${{{P + key}}},\n" for key in fields)
    ref = "${module.driver.pdm.p_coefficients}"
    decl += f"#if defined({ref})\n    .p_coefficients = {ref},\n#else\n    .p_coefficients = &{ref},\n#endif\n"
    decl += f"}};\npdm_cfg_t const {N}_cfg =\n{{\n    .p_extend = &{N}_ext_cfg,\n"
    decl += "".join(f"    .{key} = ${{{P + key}}},\n" for key in ("channel", "ipl", "p_callback"))
    ref = "${module.driver.pdm.p_context}"
    decl += f"#if defined({ref})\n    .p_context = {ref},\n#else\n    .p_context = &{ref},\n#endif\n"
    for key, event in (("dat", "DAT"), ("err", "ERR")):
        vector = "VECTOR_NUMBER_PDM_" + event + "${module.driver.pdm.channel}"
        decl += f"#if defined({vector})\n    .{key}_irq = {vector},\n#else\n    .{key}_irq = FSP_INVALID_VECTOR,\n#endif\n"
    decl += f"}};\npdm_instance_t const {N} = {{ .p_ctrl = &{N}_ctrl, .p_cfg = &{N}_cfg, .p_api = &g_pdm_on_pdm }};\n"
    ET.SubElement(mod, "declarations").text = decl
    ET.SubElement(mod, "functions")
    guard = ET.SubElement(mod, "guard")
    protos, bodies, macros = [], [], []
    for key, (api, extra, args) in signatures.items():
        signature = "pdm_ctrl_t * const p_ctrl" + (", " + extra if extra else "")
        proto = f"BSP_CMSE_NONSECURE_ENTRY fsp_err_t {N}_{key}_guard({signature})"
        protos.append(proto + ";\n")
        body = proto + "\n{\n    FSP_PARAMETER_NOT_USED(p_ctrl);\n"
        if key == "open":
            body += f"    FSP_PARAMETER_NOT_USED(p_cfg);\n    return R_PDM_Open(&{N}_ctrl, &{N}_cfg);\n}}\n"
        else:
            if key == "start":
                body += "    FSP_ERROR_RETURN((samples > 0U) && (samples <= UINT32_MAX / sizeof(uint32_t)), FSP_ERR_INVALID_SIZE);\n"
                body += "    FSP_ERROR_RETURN(NULL != cmse_check_address_range(p_buffer, samples * sizeof(uint32_t), CMSE_AU_NONSECURE | CMSE_MPU_READWRITE), FSP_ERR_INVALID_ADDRESS);\n"
            elif key == "status_get":
                body += "    FSP_ERROR_RETURN(NULL != cmse_check_pointed_object(p_status, CMSE_AU_NONSECURE | CMSE_MPU_READWRITE), FSP_ERR_INVALID_ADDRESS);\n"
            elif key == "callback_set":
                body += "    FSP_ERROR_RETURN(NULL != cmse_check_address_range((void *) p_callback, sizeof(void *), CMSE_AU_NONSECURE), FSP_ERR_INVALID_ADDRESS);\n"
                body += "    FSP_ERROR_RETURN(NULL != cmse_check_pointed_object(p_callback_memory, CMSE_AU_NONSECURE | CMSE_MPU_READWRITE), FSP_ERR_NO_CALLBACK_MEMORY);\n"
            body += f"    return R_PDM_{api}(&{N}_ctrl" + (", " + args if args else "") + ");\n}\n"
        bodies.append(body)
        param_names = args if key != "open" else ""
        call_args = "FSP_SECURE_ARGUMENT" + (", FSP_SECURE_ARGUMENT" if key == "open" else (", " + args if args else ""))
        macros.append(f"#define FSP_GUARD_{N}_R_PDM_{api}({param_names}) {N}_{key}_guard({call_args})\n")
    ET.SubElement(guard, "header").text = "\n" + "\n".join(protos)
    ET.SubElement(guard, "template", name=N + "_guard.c").text = '#include "guard.h"\n\n' + "\n".join(bodies)
    nsc = ET.SubElement(mod, "nsc")
    ET.SubElement(nsc, "header").text = "\n" + "\n".join(macros + protos) + f"\nextern pdm_instance_t const {N};\n"
    entries = {"open": "open", "start": "start", "stop": "stop", "statusGet": "status_get", "close": "close", "callbackSet": "callback_set"}
    nsc_decl = f"\nstatic pdm_api_t const {N}_nsc_api =\n{{\n"
    nsc_decl += "".join(f"    .{field} = {N}_{guard_key}_guard,\n" for field, guard_key in entries.items())
    nsc_decl += f"}};\npdm_instance_t const {N} = {{ .p_api = &{N}_nsc_api, .p_ctrl = FSP_SECURE_ARGUMENT, .p_cfg = FSP_SECURE_ARGUMENT }};\n"
    ET.SubElement(nsc, "declarations").text = nsc_decl
    api = ET.SubElement(mod, "api", configurable="true")
    ET.SubElement(api, "file").text = "ra/fsp/inc/instances/r_pdm.h"
    ET.SubElement(api, "file").text = "ra/fsp/inc/api/r_pdm_api.h"
    ET.indent(root, "    ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


if __name__ == "__main__":
    MDF.write_text(render())
