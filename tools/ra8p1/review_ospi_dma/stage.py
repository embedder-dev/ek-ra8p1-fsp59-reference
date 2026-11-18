"""Build the OSPI008..012 proposal in memory; never modify an owning source file."""
from pathlib import Path
import difflib

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c"
HERE = Path(__file__).resolve().parent


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise AssertionError("Staging context is no longer unique: " + old[:100])
    return source.replace(old, new, 1)


def proposed(source):
    source = replace_once(source, "#define OSPI_B_PRV_OPEN                   (0x78535049U)", """#define OSPI_B_PRV_OPEN                   (0x78535049U)

#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
 #define OSPI_B_PRV_DMA_RECOVERY           (OSPI_B_PRV_OPEN | 0x80000000U)
#endif""")
    marker = "static bool      r_ospi_b_status_sub(ospi_b_instance_ctrl_t * p_instance_ctrl, uint8_t bit_pos);"
    source = replace_once(source, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
static fsp_err_t r_ospi_b_dma_quiesce(ospi_b_instance_ctrl_t * p_ctrl);
#endif

""" + marker)
    # Lower Open succeeds before this attempt acquires any OSPI module or register resources.
    marker = "    /* Enable clock to the xSPI block */"
    source = replace_once(source, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    FSP_ERROR_RETURN(OSPI_B_PRV_DMA_RECOVERY != p_instance_ctrl->open, FSP_ERR_IN_USE);
    FSP_ERROR_RETURN(OSPI_B_PRV_OPEN != p_instance_ctrl->open, FSP_ERR_ALREADY_OPEN);
    FSP_ERROR_RETURN(0U == (g_ospi_b_channels_open_flags & OSPI_B_PRV_CH_MASK(p_cfg_extend)), FSP_ERR_ALREADY_OPEN);
    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;
 #if OSPI_B_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_transfer);
 #endif
    dmac_extended_cfg_t const * p_dmac_extend = p_transfer->p_cfg->p_extend;
    dmac_instance_ctrl_t const * p_dmac_ctrl = (dmac_instance_ctrl_t const *) p_transfer->p_ctrl;
    FSP_ERROR_RETURN(p_dmac_extend->channel < BSP_FEATURE_DMAC_MAX_CHANNEL, FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    FSP_ERROR_RETURN(0U == p_dmac_ctrl->open, FSP_ERR_ALREADY_OPEN);
    ret = p_transfer->p_api->open(p_transfer->p_ctrl, p_transfer->p_cfg);
    FSP_ERROR_RETURN(FSP_SUCCESS == ret, ret);
#endif

""" + marker)
    source = replace_once(source, "#if OSPI_B_CFG_DMAC_SUPPORT_ENABLE\n    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;", "#if OSPI_B_CFG_DMAC_SUPPORT_ENABLE && !BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP\n    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;")
    marker = "    /* Disable memory-mapping for this slave. It will be enabled later on after initialization. */"
    source = replace_once(source, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    uint32_t bmctl0 = p_reg->BMCTL0;
    uint32_t wrapcfg = p_reg->WRAPCFG;
#endif

""" + marker)
    marker = "    /* Return response after issuing write transaction to xSPI bus, Enable prefetch function and combination if desired. */"
    source = replace_once(source, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    if (FSP_SUCCESS != ret)
    {
        /* Restore shared registers before releasing only the resources acquired by this attempt. */
        p_reg->WRAPCFG = wrapcfg;
        p_reg->BMCTL0 = bmctl0;
        fsp_err_t cleanup = r_ospi_b_dma_quiesce(p_instance_ctrl);
        if (FSP_SUCCESS == cleanup)
        {
            cleanup = p_transfer->p_api->close(p_transfer->p_ctrl);
        }

        if (FSP_SUCCESS != cleanup)
        {
            p_instance_ctrl->open = OSPI_B_PRV_DMA_RECOVERY;
            g_ospi_b_channels_open_flags |= OSPI_B_PRV_CH_MASK(p_cfg_extend);
            return FSP_ERR_IN_USE;
        }

        p_instance_ctrl->open = 0U;
        if (0U == (g_ospi_b_channels_open_flags & OSPI_B_PRV_UNIT_MASK(p_cfg_extend)))
        {
            R_BSP_MODULE_STOP(FSP_IP_OSPI, p_cfg_extend->ospi_b_unit);
        }

        return ret;
    }
#endif

""" + marker)
    # Transfer length validation precedes all MMIO and the uint16_t assignment, checks on or off.
    marker = "    R_XSPI0_Type * const p_reg = p_instance_ctrl->p_reg;\n\n    FSP_ERROR_RETURN(false == r_ospi_b_status_sub"
    source = replace_once(source, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    FSP_ERROR_RETURN((byte_count > 0U) && (byte_count <= UINT16_MAX), FSP_ERR_INVALID_SIZE);
#endif

""" + marker)
    first = source.index("fsp_err_t R_OSPI_B_Write (")
    dma_start = source.index("    /* Setup and start DMAC transfer. */", first)
    dma_end = source.index("    /* If this number of bytes is less than the combination count", dma_start)
    legacy = source[dma_start:dma_end]
    new = """    /* Setup and start DMAC transfer. */
    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;
    dmac_extended_cfg_t const * p_dmac_extend = p_transfer->p_cfg->p_extend;
    FSP_ERROR_RETURN(p_dmac_extend->channel < BSP_FEATURE_DMAC_MAX_CHANNEL, FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    R_DMAC0_Type * p_dma_reg = (R_DMAC0_Type *) ((uintptr_t) R_DMAC0 +
                                             ((uintptr_t) R_DMAC1 - (uintptr_t) R_DMAC0) *
                                             p_dmac_extend->channel);

    /* Do not enable or configure DMA after a rejected write-enable command. */
    err = r_ospi_b_write_enable(p_instance_ctrl);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    p_dma_reg->DMBWR = R_DMAC0_DMBWR_BWE_Msk;

    p_transfer->p_cfg->p_info->p_src = p_src;
    p_transfer->p_cfg->p_info->p_dest = p_dest;
    p_transfer->p_cfg->p_info->transfer_settings_word_b.size = TRANSFER_SIZE_1_BYTE;
    p_transfer->p_cfg->p_info->transfer_settings_word_b.mode = TRANSFER_MODE_NORMAL;
    p_transfer->p_cfg->p_info->length = (uint16_t) byte_count;
    err = p_transfer->p_api->reconfigure(p_transfer->p_ctrl, p_transfer->p_cfg->p_info);
    if (FSP_SUCCESS == err)
    {
        err = p_transfer->p_api->softwareStart(p_transfer->p_ctrl, TRANSFER_START_MODE_REPEAT);
    }

    transfer_properties_t properties = {0U};
    while (FSP_SUCCESS == err)
    {
        err = p_transfer->p_api->infoGet(p_transfer->p_ctrl, &properties);
        if ((FSP_SUCCESS != err) || (0U == properties.transfer_length_remaining))
        {
            break;
        }
    }

    /* A failed abort retains BWE and the buffer references until Close succeeds. */
    fsp_err_t cleanup = r_ospi_b_dma_quiesce(p_instance_ctrl);
    FSP_ERROR_RETURN(FSP_SUCCESS == cleanup, cleanup);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);

"""
    source = source[:dma_start] + " #if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP\n" + new + " #else\n" + legacy + " #endif\n\n" + source[dma_end:]
    # Private recovery is represented by a distinct existing open-word value: no control-layout change.
    marker = "    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;\n    p_transfer->p_api->close(p_transfer->p_ctrl);"
    source = replace_once(source, marker, """    transfer_instance_t const * p_transfer = p_cfg_extend->p_lower_lvl_transfer;
 #if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP
    err = r_ospi_b_dma_quiesce(p_instance_ctrl);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    err = p_transfer->p_api->close(p_transfer->p_ctrl);
    if (FSP_SUCCESS != err)
    {
        p_instance_ctrl->open = OSPI_B_PRV_DMA_RECOVERY;
        return FSP_ERR_IN_USE;
    }
 #else
    p_transfer->p_api->close(p_transfer->p_ctrl);
 #endif""")
    start = source.index("fsp_err_t R_OSPI_B_Close (")
    end = source.index("\n/****************************************************************", start)
    close = source[start:end]
    old = "    FSP_ERROR_RETURN(OSPI_B_PRV_OPEN == p_instance_ctrl->open, FSP_ERR_NOT_OPEN);"
    close = replace_once(close, old, """ #if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    FSP_ERROR_RETURN((OSPI_B_PRV_OPEN == p_instance_ctrl->open) ||
                     (OSPI_B_PRV_DMA_RECOVERY == p_instance_ctrl->open), FSP_ERR_NOT_OPEN);
 #else
""" + old + "\n #endif")
    marker = "    ospi_b_extended_cfg_t * p_cfg_extend = (ospi_b_extended_cfg_t *) (p_instance_ctrl->p_cfg->p_extend);"
    close = replace_once(close, marker, """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    FSP_ERROR_RETURN((OSPI_B_PRV_OPEN == p_instance_ctrl->open) ||
                     (OSPI_B_PRV_DMA_RECOVERY == p_instance_ctrl->open), FSP_ERR_NOT_OPEN);
#endif

""" + marker)
    source = source[:start] + close + source[end:]
    # Every supported device operation must respect a retained-buffer recovery state, even checks=0.
    for name in ("Open", "DirectTransfer", "XipEnter", "XipExit", "Write", "Erase", "StatusGet", "SpiProtocolSet", "AutoCalibrate"):
        start = source.index("fsp_err_t R_OSPI_B_" + name + " (")
        end = source.index("\n/****************************************************************", start)
        body = source[start:end]
        pattern = "    ospi_b_instance_ctrl_t * p_instance_ctrl = (ospi_b_instance_ctrl_t *) p_ctrl;"
        if pattern not in body:
            raise AssertionError("Missing operation control declaration: " + name)
        body = replace_once(body, pattern, pattern + """
#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
    FSP_ERROR_RETURN((NULL == p_instance_ctrl) || (OSPI_B_PRV_DMA_RECOVERY != p_instance_ctrl->open), FSP_ERR_IN_USE);
#endif""")
        source = source[:start] + body + source[end:]
    helper = """#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP && OSPI_B_CFG_DMAC_SUPPORT_ENABLE
static fsp_err_t r_ospi_b_dma_quiesce (ospi_b_instance_ctrl_t * p_ctrl)
{
    ospi_b_extended_cfg_t const * p_extend = (ospi_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    transfer_instance_t const * p_transfer = p_extend->p_lower_lvl_transfer;
    dmac_extended_cfg_t const * p_dmac_extend = p_transfer->p_cfg->p_extend;
    FSP_ERROR_RETURN(p_dmac_extend->channel < BSP_FEATURE_DMAC_MAX_CHANNEL, FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    R_DMAC0_Type * p_dma_reg = (R_DMAC0_Type *) ((uintptr_t) R_DMAC0 +
                                             ((uintptr_t) R_DMAC1 - (uintptr_t) R_DMAC0) *
                                             p_dmac_extend->channel);
    fsp_err_t err = p_transfer->p_api->disable(p_transfer->p_ctrl);
    if ((FSP_SUCCESS != err) || (0U != (p_dma_reg->DMCNT & R_DMAC0_DMCNT_DTE_Msk)) ||
        (0U != (p_dma_reg->DMSTS & R_DMAC0_DMSTS_ACT_Msk)))
    {
        p_ctrl->open = OSPI_B_PRV_DMA_RECOVERY;
        return FSP_ERR_IN_USE;
    }

    p_dma_reg->DMBWR = 0U;
    return FSP_SUCCESS;
}
#endif

"""
    marker = "    return (offset < size) && (bytes > 0U) && (bytes <= size - offset);\n}\n#endif\n"
    source = replace_once(source, marker, marker + "\n" + helper.rstrip() + "\n")
    # The externally visible recovery result includes an explicit buffer-lifetime contract.
    marker = " * @retval FSP_ERR_WRITE_FAILED        Write operation failed."
    at = source.index(marker, source.index(" * Program a page of data"))
    source = source[:at] + """ * @retval FSP_ERR_IN_USE              DMA cleanup is pending. Keep source and destination buffers valid until Close succeeds.
""" + source[at:]
    return source


def patch_bytes(source):
    old = source.decode().replace("\r\n", "\n")
    new = proposed(old)
    # CRLF hunks apply directly without changing the original driver's line endings.
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                       fromfile="a/baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c",
                       tofile="b/baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c")).replace("\n", "\r\n").encode()


if __name__ == "__main__":
    (HERE / "ospi008.patch").write_bytes(patch_bytes(SOURCE.read_bytes()))
