/* Execute the actual emitted ScanCfg guard. The CMSE test double grants only
 * explicitly registered byte ranges; no address heuristic stands in for CMSE. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_adc_b.h"
#define BSP_CMSE_NONSECURE_ENTRY
#define CMSE_AU_NONSECURE 1U
#define CMSE_NONSECURE 3U
#define CMSE_MPU_READ 4U
static struct { void * address; size_t size; } ranges[40];
static unsigned range_count, called, checks;
static bool mutate;
static adc_b_scan_cfg_t outer;
static adc_b_group_cfg_t groups[2];
static adc_b_virtual_channel_cfg_t vcs[2];
static adc_b_group_cfg_t * group_ptrs[2];
static adc_b_virtual_channel_cfg_t * vc_ptrs[2][1];
adc_b_instance_ctrl_t g_adc_ctrl;
static void grant(void * address, size_t size)
{ ranges[range_count].address = address; ranges[range_count++].size = size; }
void * cmse_check_address_range(void * address, size_t size, unsigned flags)
{
    assert((flags & (CMSE_NONSECURE | CMSE_MPU_READ)) == (CMSE_NONSECURE | CMSE_MPU_READ));
    checks++;
    for (unsigned i = 0; i < range_count; i++)
    {
        if (ranges[i].address == address && size != 0U && size <= ranges[i].size)
        {
            /* Once the final VC is checked, all parent pointers may change.
             * Secure code must use snapshots, not chase NS pointers again. */
            if (mutate && address == &vcs[1])
            {
                outer.group_count = 255; outer.p_adc_groups = (void *) 1;
                group_ptrs[0] = group_ptrs[1] = (void *) 1;
                groups[0].virtual_channel_count = 255; groups[0].p_virtual_channels = (void *) 1;
                groups[1].virtual_channel_count = 255; groups[1].p_virtual_channels = (void *) 1;
                vc_ptrs[0][0] = vc_ptrs[1][0] = (void *) 1;
            }
            return address;
        }
    }
    return NULL;
}
fsp_err_t R_ADC_B_ScanCfg(adc_ctrl_t * ctrl, void const * data)
{
    assert(ctrl == &g_adc_ctrl);
    adc_b_scan_cfg_t const * scan = data;
    called++;
    assert(scan != &outer && scan->group_count == 2);
    for (unsigned i = 0; i < 2; i++)
    {
        assert(scan->p_adc_groups != group_ptrs);
        adc_b_group_cfg_t const * group = scan->p_adc_groups[i];
        assert(group != &groups[i] && group->virtual_channel_count == 1);
        assert(group->p_virtual_channels != vc_ptrs[i]);
        assert(group->p_virtual_channels[0] != &vcs[i]);
        assert(group->p_virtual_channels[0]->channel_id == (adc_b_virtual_channel_t) i);
    }
    return FSP_SUCCESS;
}
#if !ADC_B_CFG_PARAM_CHECKING_ENABLE
#undef FSP_ASSERT
#define FSP_ASSERT(x) ((void) 0)
#endif
#include "guard_function.h"
int main(int argc, char ** argv)
{
    assert(argc == 3);
    int deny = atoi(argv[1]); mutate = atoi(argv[2]) != 0;
    outer.group_count = 2; outer.p_adc_groups = group_ptrs;
    grant(&outer, sizeof(outer)); grant(group_ptrs, sizeof(group_ptrs));
    for (unsigned i = 0; i < 2; i++)
    {
        group_ptrs[i] = &groups[i]; vc_ptrs[i][0] = &vcs[i];
        groups[i].p_virtual_channels = vc_ptrs[i]; groups[i].virtual_channel_count = 1;
        vcs[i].channel_id = (adc_b_virtual_channel_t) i;
        grant(&groups[i], sizeof(groups[i])); grant(vc_ptrs[i], sizeof(vc_ptrs[i])); grant(&vcs[i], sizeof(vcs[i]));
    }
    if (deny >= 0 && deny < 8) { ranges[deny].size--; }
    if (deny == 8) { outer.group_count = 255; }
    if (deny == 9) { groups[1].virtual_channel_count = 255; }
    if (deny == 10) { outer.group_count = 0; }
    if (deny == 11) { groups[1].virtual_channel_count = 0; }
    if (deny == 12) { groups[1].scan_group_id = (adc_group_id_t) 255; }
    if (deny == 13) { groups[1].converter_selection = (adc_b_unit_id_t) 255; }
    if (deny == 14) { vcs[1].channel_id = (adc_b_virtual_channel_t) 255; }
    fsp_err_t err = g_adc_scan_cfg_guard(NULL, &outer);
    assert(err == (deny < 0 ? FSP_SUCCESS : (deny < 8 ? FSP_ERR_INVALID_ADDRESS : FSP_ERR_INVALID_ARGUMENT)));
    assert(called == (deny < 0 ? 1U : 0U));
    assert(checks > 0);
    puts("nested CMSE guard oracle passed");
    return 0;
}
