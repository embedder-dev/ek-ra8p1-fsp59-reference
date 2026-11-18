"""Generate the new MDFs using only the preserved FSP5.9 guard/NSC templates."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MDF = ROOT / "baseline/module_descriptions"


def text(node, tag, value, **attrs):
    child = ET.SubElement(node, tag, attrs)
    child.text = value
    return child


def property_(node, id_, default, display, description=""):
    return ET.SubElement(node, "property", id=id_, default=default, display=display, description=description)


def build(driver, interface, sibling):
    old = ET.parse(MDF / f"Renesas##HAL Drivers##all##r_{sibling}####5.9.0.xml").getroot().find("module")
    root = ET.Element("raModuleDescription")
    cfg = ET.SubElement(root, "config", id=f"config.driver.{driver}", path=f"fsp_cfg/r_{driver}_cfg.h", version="0")
    prop = property_(cfg, f"config.driver.{driver}.param_checking_enable",
                     f"config.driver.{driver}.param_checking_enable.bsp", "Parameter Checking")
    for id_, name, value in [("bsp", "Default (BSP)", "BSP_CFG_PARAM_CHECKING_ENABLE"),
                             ("enabled", "Enabled", "1"), ("disabled", "Disabled", "0")]:
        ET.SubElement(prop, "option", id=f"config.driver.{driver}.param_checking_enable.{id_}",
                      display=name, value=value)
    text(cfg, "content", f"\n#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE "
         f"(${{config.driver.{driver}.param_checking_enable}})\n")
    mod = ET.SubElement(root, "module", id=f"module.driver.{interface}_on_{driver}",
                        config=f"config.driver.{driver}", display=("Storage" if driver == "mram" else "Analog") +
                        f"|${{module.driver.{driver}.name}} {driver.upper()} (r_{driver})", version="1",
                        url="group___" + "_".join(driver.upper()) + ".html")
    text(mod, "constraint", f'"${{interface.driver.{interface}.${{module.driver.{driver}.name}}}}" === "1"',
         display="Unique name required for each instance")
    text(mod, "constraint", f'"${{interface.mcu.{driver}}}" === "1"',
         display=f"Requires {driver.upper()} peripheral")
    ET.SubElement(mod, "requires", id=f"module.driver.{interface}_on_{driver}.requires.mcu",
                  interface=f"interface.mcu.{driver}", visible="false", display=f"Requires {driver.upper()} peripheral")
    for value in [f"interface.driver.{interface}", f"interface.driver.{interface}_on_{driver}",
                  f"interface.driver.{interface}.${{module.driver.{driver}.name}}", f"interface.peripheral.{driver}"]:
        ET.SubElement(mod, "provides", interface=value)
    name = property_(mod, f"module.driver.{driver}.name", f"g_{driver}${{_instance}}", "Name")
    text(name, "constraint", f'testSymbol("${{module.driver.{driver}.name}}")', display="Name must be a valid C symbol")
    for child in old:
        if child.tag in {"symbol", "guard", "nsc"}:
            value = ET.tostring(child, encoding="unicode")
            if driver == "mram":
                value = value.replace("driver.flash", "driver.mram").replace("R_FLASH_HP_", "R_MRAM_")
                value = value.replace("flash_hp_instance_ctrl_t", "mram_instance_ctrl_t").replace("g_flash_on_flash_hp", "g_flash_on_mram")
                # The source window is not enough to authorize reads of secure RAM through an NSC call.
                value = value.replace("    return R_MRAM_Write(&", "    FSP_ERROR_RETURN(num_bytes != 0U, FSP_ERR_INVALID_SIZE);\n"
                                      "    FSP_ERROR_RETURN(cmse_check_address_range((void *)(uintptr_t) src_address, num_bytes, "
                                      "CMSE_NONSECURE | CMSE_MPU_READ) != NULL, FSP_ERR_INVALID_ADDRESS);\n"
                                      "    return R_MRAM_Write(&")
                for fn, arguments in [("StartUpAreaSelect", ["swap_type", "is_temporary"]),
                                       ("AntiRollbackCounterIncrement", ["counter"])]:
                    replacement = "".join(f"FSP_PARAMETER_NOT_USED({arg});\n    " for arg in arguments)
                    value = re.sub(r"return R_MRAM_" + fn + r"\([^\n]+?\);",
                                   replacement + "return FSP_ERR_UNSUPPORTED;", value)
                if child.tag == "guard":
                    value = value.replace("FSP_ASSERT(p_callback_checked != NULL);",
                                          "FSP_ERROR_RETURN(p_callback_checked != NULL, FSP_ERR_INVALID_ADDRESS);")
                    value = value.replace("cmse_check_pointed_object(p_callback_memory, CMSE_AU_NONSECURE);",
                                          "cmse_check_pointed_object(p_callback_memory, CMSE_AU_NONSECURE | CMSE_MPU_READWRITE);")
                    value = value.replace("FSP_ASSERT(p_callback_memory_checked != NULL);",
                                          "FSP_ERROR_RETURN(p_callback_memory_checked != NULL, FSP_ERR_NO_CALLBACK_MEMORY);")
            else:
                value = value.replace("driver.dac", "driver.dac_b").replace("R_DAC_", "R_DAC_B_")
            mod.append(ET.fromstring(value))
    return root, mod


def write(root, driver):
    ET.indent(root, space="    ")
    data = ET.tostring(root, encoding="unicode")
    (MDF / f"Renesas##HAL Drivers##all##r_{driver}####5.9.0.xml").write_text(
        '<?xml version="1.0"?>\n' + data + "\n")


def mram():
    root, mod = build("mram", "flash", "flash_hp")
    for id_, default, display in [("write_start", "0", "Reserved Write Window Start"),
                                  ("write_end", "0", "Reserved Write Window End (exclusive)"),
                                   ("timeout", "1000000", "Polling Iterations Before Timeout")]:
        p = property_(mod, "module.driver.mram." + id_, default, display)
        text(p, "constraint", f'testInteger("${{module.driver.mram.{id_}}}") && '
             f'(Number("${{module.driver.mram.{id_}}}") >= {1 if id_ == "timeout" else 0}) && '
             f'(Number("${{module.driver.mram.{id_}}}") <= 4294967295)',
             display="Must be a nonnegative integer" if id_ != "timeout" else "Must be a positive integer")
    p = property_(mod, "module.driver.mram.extra", "module.driver.mram.extra.disabled", "Secure Extra Commands",
                  "Explicit opt-in for startup selection and irreversible anti-rollback increment. NSC wrappers do not authorize them.")
    for id_, value in [("disabled", "false"), ("enabled", "true")]:
        ET.SubElement(p, "option", id="module.driver.mram.extra." + id_, display=id_.title(), value=value)
    text(mod, "constraint", 'Number("${module.driver.mram.write_start}") <= Number("${module.driver.mram.write_end}")',
         display="Write window end must not precede start")
    p = property_(mod, "module.driver.mram.p_callback", "NULL", "Callback",
                  "Stored for the flash interface only; blocking MRAM operations never invoke completion callbacks.")
    text(p, "constraint", 'testSymbol("${module.driver.mram.p_callback}")', display="Callback must be a valid C symbol")
    property_(mod, "module.driver.mram.p_context", "NULL", "Callback Context")
    # Keep template order consistent with stock: properties, symbols, header/includes/declarations, guard/nsc/api.
    text(mod, "header", '\nextern const flash_instance_t ${module.driver.mram.name};\n'
         'extern mram_instance_ctrl_t ${module.driver.mram.name}_ctrl;\n'
         'extern const flash_cfg_t ${module.driver.mram.name}_cfg;\n'
         '#ifndef ${module.driver.mram.p_callback}\n'
         'void ${module.driver.mram.p_callback}(flash_callback_args_t * p_args);\n#endif\n')
    text(mod, "includes", '#include "r_mram.h"\n#include "r_flash_api.h"')
    text(mod, "declarations", '''
mram_instance_ctrl_t ${module.driver.mram.name}_ctrl;
const mram_extended_cfg_t ${module.driver.mram.name}_ext_cfg =
{
    .write_window_start = ${module.driver.mram.write_start},
    .write_window_end = ${module.driver.mram.write_end},
    .timeout = ${module.driver.mram.timeout},
    .enable_extra_commands = ${module.driver.mram.extra},
};
const flash_cfg_t ${module.driver.mram.name}_cfg =
{
    .data_flash_bgo = false,
    .p_callback = ${module.driver.mram.p_callback},
#if defined(${module.driver.mram.p_context})
    .p_context = ${module.driver.mram.p_context},
#else
    .p_context = &${module.driver.mram.p_context},
#endif
    .p_extend = &${module.driver.mram.name}_ext_cfg,
    .irq = FSP_INVALID_VECTOR,
    .err_irq = FSP_INVALID_VECTOR,
    .ipl = BSP_IRQ_DISABLED,
    .err_ipl = BSP_IRQ_DISABLED,
};
const flash_instance_t ${module.driver.mram.name} =
{
    .p_ctrl = &${module.driver.mram.name}_ctrl,
    .p_cfg = &${module.driver.mram.name}_cfg,
    .p_api = &g_flash_on_mram,
};
''')
    finish(root, mod, "mram", "flash")


def finish(root, mod, driver, interface):
    api = ET.SubElement(mod, "api", configurable="true")
    text(api, "file", f"ra/fsp/inc/instances/r_{driver}.h")
    text(api, "file", f"ra/fsp/inc/api/r_{interface}_api.h")
    order = {name: index for index, name in enumerate(["constraint", "requires", "provides", "property", "peripheral",
                                                      "symbol", "header", "includes", "declarations", "guard", "nsc", "api"])}
    mod[:] = sorted(mod, key=lambda child: order[child.tag])
    write(root, driver)


def dac_b():
    root, mod = build("dac_b", "dac", "dac")
    p = property_(mod, "module.driver.dac_b.channel", "0", "Channel")
    text(p, "constraint", 'testInteger("${module.driver.dac_b.channel}") && '
         '(Number("${module.driver.dac_b.channel}") >= 0) && (Number("${module.driver.dac_b.channel}") <= 1)',
         display="Channel must be 0 or 1")
    text(mod, "constraint", '"${interface.mcu.dac_b.${module.driver.dac_b.channel}}" === "1"',
         display="Channel not available on selected MCU")
    for name, label, choices in [
        ("data_format", "Data Format", [("right", "Right Justified", "DAC_DATA_FORMAT_FLUSH_RIGHT"),
                                          ("left", "Left Justified", "DAC_DATA_FORMAT_FLUSH_LEFT")]),
        ("voltage_mode", "External VREFH Voltage", [("normal", ">= 2.7 V", "DAC_B_VOLTAGE_NORMAL"),
                                                     ("low", "< 2.7 V", "DAC_B_VOLTAGE_LOW")]),
        ("output", "Output Destination", [("pin", "DAn pin", "DAC_B_OUTPUT_PIN"),
                                           ("internal", "Comparator / ADC16H", "DAC_B_OUTPUT_INTERNAL")]),
        ("calibration_preloaded", "Coefficients Preloaded by Secure Startup", [("disabled", "No: Transfer on Open", "false"),
                                                                               ("enabled", "Yes", "true")]),
    ]:
        p = property_(mod, "module.driver.dac_b." + name, "module.driver.dac_b." + name + "." + choices[0][0], label)
        for id_, label_, value in choices:
            ET.SubElement(p, "option", id="module.driver.dac_b." + name + "." + id_, display=label_, value=value)
    p = property_(mod, "module.driver.dac_b.p_pair", "NULL", "Collective Start Peer Control Block",
                  "NULL for independent conversion. Otherwise use the other unit's control-block symbol and configure its reciprocal peer. Both units require matching security attribution.")
    text(p, "constraint", 'testSymbol("${module.driver.dac_b.p_pair}")', display="Must be a C symbol")
    p = property_(mod, "module.driver.dac_b.timeout", "1000000", "Calibration Polling Iterations")
    text(p, "constraint", 'testInteger("${module.driver.dac_b.timeout}") && '
         '(Number("${module.driver.dac_b.timeout}") > 0) && (Number("${module.driver.dac_b.timeout}") <= 4294967295)',
         display="Timeout must be a positive 32-bit integer")
    p = property_(mod, "module.driver.dac_b.elc_trigger", "_disabled", "ELC Trigger Source")
    ET.SubElement(p, "select", enum="enum.disabled")
    ET.SubElement(p, "select", enum="_signal")
    text(p, "linkConstraint", '"${_link}" === "link.dac${module.driver.dac_b.channel}"',
         display="Requires ELC peripheral function for DAC")
    text(mod, "constraint", '(!"${module.driver.dac_b.elc_trigger}".startsWith("_signal.")) || '
         '("1" === "${interface.driver.elc}")', display="ELC signal selection requires an ELC Driver")
    text(mod, "constraint", '("${module.driver.dac_b.elc_trigger}" === "_disabled") || '
         '("${module.driver.dac_b.p_pair}" === "NULL")', display="Collective DAE control cannot be combined with ELC")
    text(mod, "constraint", '("${_project.nonsecure}" !== "1") || '
         '("${module.driver.dac_b.calibration_preloaded}" === "module.driver.dac_b.calibration_preloaded.enabled")',
         display="Nonsecure DAC requires coefficient transfer by secure startup")
    ET.SubElement(mod, "peripheral", name="DAC12${module.driver.dac_b.channel}",
                  component="dac12${module.driver.dac_b.channel}")
    text(mod, "header", '\nextern const dac_instance_t ${module.driver.dac_b.name};\n'
         'extern dac_b_instance_ctrl_t ${module.driver.dac_b.name}_ctrl;\n'
         'extern const dac_cfg_t ${module.driver.dac_b.name}_cfg;\n')
    text(mod, "includes", '#include "r_dac_b.h"\n#include "r_dac_api.h"')
    text(mod, "declarations", '''
dac_b_instance_ctrl_t ${module.driver.dac_b.name}_ctrl;
const dac_b_extended_cfg_t ${module.driver.dac_b.name}_ext_cfg =
{
    .data_format = ${module.driver.dac_b.data_format},
    .voltage_mode = ${module.driver.dac_b.voltage_mode},
    .output = ${module.driver.dac_b.output},
    .trigger = (0 == ${module.driver.dac_b.elc_trigger}) ? DAC_B_TRIGGER_SOFTWARE : DAC_B_TRIGGER_ELC,
#if defined(${module.driver.dac_b.p_pair})
    .p_pair = ${module.driver.dac_b.p_pair},
#else
    .p_pair = &${module.driver.dac_b.p_pair},
#endif
    .timeout = ${module.driver.dac_b.timeout},
    .calibration_preloaded = ${module.driver.dac_b.calibration_preloaded},
};
const dac_cfg_t ${module.driver.dac_b.name}_cfg =
{
    .channel = ${module.driver.dac_b.channel},
    .ad_da_synchronized = false,
    .p_extend = &${module.driver.dac_b.name}_ext_cfg,
};
const dac_instance_t ${module.driver.dac_b.name} =
{
    .p_ctrl = &${module.driver.dac_b.name}_ctrl,
    .p_cfg = &${module.driver.dac_b.name}_cfg,
    .p_api = &g_dac_on_dac_b,
};
''')
    finish(root, mod, "dac_b", "dac")


if __name__ == "__main__":
    mram()
    dac_b()
