/* HM64.2.1/.2/.3/.12-.18/.26/.28/.38 and 66.3.6.1 independent oracles.
 * Register offsets, masks and limits below are transcribed from the HM, not
 * calculated from the driver's private macros. This is a host MMIO model. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bsp_api.h"
#include "r_glcdc.h"
#include "r_mipi_dsi_api.h"
R_GLCDC_Type review_regs;
static unsigned char previous[sizeof(review_regs)];
static unsigned delay_calls, stopped, dsi_starts, dsi_closes;
static int fault;
static fsp_err_t dsi_result;
static unsigned event_count;
static size_t offsets[512];
static void monitor(uint32_t value)
{
    memcpy((unsigned char *) &review_regs + 0x1018, &value, 4);
}
static uint32_t word(size_t offset)
{
    uint32_t v;
    memcpy(&v, (unsigned char *) &review_regs + offset, 4);
    return v;
}
R_GLCDC_Type * review_access(void)
{
    bool changed = memcmp(previous, &review_regs, sizeof(review_regs)) != 0;
    for (size_t off = 0; changed && off < sizeof(review_regs); off += 4)
    {
        uint32_t old;
        memcpy(&old, previous + off, 4);
        uint32_t now = word(off);
        if (now != old)
        {
            if (event_count < 512)
            {
                offsets[event_count] = off;
                ++event_count;
            }
            /* Reflected writes are forbidden during any gamma request. */
            if (fault == 7 && off != 0x1300 && off != 0x1340 && off != 0x1380)
            {
                assert((word(0x1300) | word(0x1340) | word(0x1380)) == 0);
            }
            if ((fault == 7 || fault == 8) && off == 0x1000 &&
                (now & 0x101) && !(old & 0x101))
            {
                assert((now & 0x101) == 0x101); /* One simultaneous EN/VEN store. */
                assert((word(0x1300) | word(0x1340) | word(0x1380)) == 0);
            }
        }
    }
    memcpy(previous, &review_regs, sizeof(review_regs));
    return &review_regs;
}
void review_module(int start) { if (!start) ++stopped; }
void R_BSP_SoftwareDelay(uint32_t n, int unit)
{
    assert(n > 0 && unit == BSP_DELAY_UNITS_MICROSECONDS);
    ++delay_calls;
    if (fault == 2 && delay_calls == 3) monitor(0x10000);
    if (fault == 1 && delay_calls == 3) monitor(0x10000);
}
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t priority, void * context)
{ (void) irq; (void) priority; (void) context; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { (void) irq; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 0; }
static fsp_err_t dsi_open(mipi_dsi_ctrl_t * p, mipi_dsi_cfg_t const * c)
{ (void) p; (void) c; return FSP_SUCCESS; }
static fsp_err_t dsi_close(mipi_dsi_ctrl_t * p)
{ (void) p; ++dsi_closes; return FSP_SUCCESS; }
static fsp_err_t dsi_start(mipi_dsi_ctrl_t * p)
{ (void) p; ++dsi_starts; return dsi_result; }
static fsp_err_t dsi_stop(mipi_dsi_ctrl_t * p)
{ (void) p; return dsi_result; }
static mipi_dsi_api_t const dsi_api = {.open=dsi_open,.close=dsi_close,.start=dsi_start,.stop=dsi_stop};
static mipi_dsi_instance_t const dsi = {.p_api=&dsi_api};
static glcdc_extended_cfg_t ext = {.clock_div_ratio=GLCDC_PANEL_CLK_DIVISOR_1,
    .tcon_hsync=GLCDC_TCON_PIN_NONE,.tcon_vsync=GLCDC_TCON_PIN_NONE,
    .tcon_de=GLCDC_TCON_PIN_NONE,.phy_layer=(void *) &dsi};
static display_cfg_t cfg;
static glcdc_instance_ctrl_t ctrl;
static void setup(void)
{
    cfg.p_extend = &ext;
    cfg.output.htiming = (display_timing_t) {.total_cyc=800,.display_cyc=640,.back_porch=40,.sync_width=20};
    cfg.output.vtiming = (display_timing_t) {.total_cyc=525,.display_cyc=480,.back_porch=20,.sync_width=4};
    cfg.line_detect_irq = cfg.underflow_1_irq = cfg.underflow_2_irq = -1;
    monitor(0x10000);
}
static void opened(void)
{
    assert(R_GLCDC_Open(&ctrl, &cfg) == FSP_SUCCESS);
    (void) review_access();
    event_count = 0;
}
static void displaying(void)
{
    opened();
    assert(R_GLCDC_Start(&ctrl) == FSP_SUCCESS);
    review_regs.BG.EN = 0x10001;
    monitor(0x10001);
    (void) review_access();
    event_count = 0;
}
static display_runtime_cfg_t runtime(void)
{
    return (display_runtime_cfg_t) {.input={.p_base=(uint32_t *) 0x20000000,
        .hsize=64,.hstride=64,.vsize=32,.format=DISPLAY_IN_FORMAT_16BITS_RGB565}};
}
int main(int argc, char ** argv)
{
    assert(argc == 2);
    int scenario = atoi(argv[1]);
    setup();
    if (scenario == 0) /* Global startup includes gamma without premature per-color reflection. */
    {
        uint16_t gain[16], threshold[16];
        for (unsigned i=0;i<16;++i) { gain[i]=1024; threshold[i]=(uint16_t)(i*64); }
        display_gamma_correction_t gamma = {0};
        gamma_correction_t * channels[3]={&gamma.g,&gamma.b,&gamma.r};
        cfg.output.p_gamma_correction=&gamma;
        fault=7;
        for (unsigned mask=0;mask<8;++mask)
        {
            memset(&review_regs,0,sizeof(review_regs));
            memset(previous,0,sizeof(previous));
            ctrl.state=DISPLAY_STATE_CLOSED;
            monitor(0x10000);
            for (unsigned c=0;c<3;++c)
            {
                channels[c]->enable=(mask & (1U<<c))!=0;
                channels[c]->gain=channels[c]->enable ? gain : NULL;
                channels[c]->threshold=channels[c]->enable ? threshold : NULL;
            }
            opened();
            assert((word(0x1300)|word(0x1340)|word(0x1380)) == 0);
            assert(word(0x1304) == (mask!=0));
            for (unsigned c=0;mask && c<3;++c)
            {
                for (unsigned i=0;i<8;++i) assert(word(0x1308+64*c+4*i)==0x04000400);
                for (unsigned i=0;i<5;++i)
                {
                    uint32_t a=64U*(i*3U+1U), b=a+64U, d=b+64U;
                    assert(word(0x1328+64*c+4*i)==((a<<20)|(b<<10)|d));
                }
            }
            assert(R_GLCDC_Start(&ctrl) == FSP_SUCCESS);
            (void) review_access();
            assert(word(0x1000)==0x10101);
        }
    }
    else if (scenario == 1) /* readiness timeout and successful delayed monitor */
    {
        monitor(0);
        assert(R_GLCDC_Open(&ctrl,&cfg)==FSP_ERR_TIMEOUT);
        assert(ctrl.state==DISPLAY_STATE_CLOSED && stopped==1 && delay_calls>0);
        assert(review_regs.GR[0].FLMRD==0);
        fault=1; delay_calls=0;
        opened();
        assert(delay_calls>=3);
    }
    else if (scenario == 2) /* Stop waits for end-of-frame, including timeout retry. */
    {
        displaying();
        assert(R_GLCDC_Stop(&ctrl)==FSP_ERR_TIMEOUT);
        assert(ctrl.state==DISPLAY_STATE_DISPLAYING && delay_calls>0);
        display_runtime_cfg_t r=runtime();
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_UPDATE_TIMING);
        assert(R_GLCDC_Start(&ctrl)!=FSP_SUCCESS);
        fault=2; delay_calls=0;
        assert(R_GLCDC_Stop(&ctrl)==FSP_SUCCESS);
        assert(ctrl.state==DISPLAY_STATE_OPENED && delay_calls>=3);
    }
    else if (scenario == 3) /* Close cannot tear down a pending or failed stop. */
    {
        displaying();
        review_regs.GR[0].VEN=1;
        assert(R_GLCDC_Close(&ctrl)==FSP_ERR_INVALID_UPDATE_TIMING);
        assert(!stopped && !dsi_closes && ctrl.state==DISPLAY_STATE_DISPLAYING);
        review_regs.GR[0].VEN=0;
        assert(R_GLCDC_Close(&ctrl)==FSP_ERR_TIMEOUT);
        assert(!stopped && !dsi_closes && ctrl.state==DISPLAY_STATE_DISPLAYING);
    }
    else if (scenario == 4)
    {
        opened(); dsi_result=FSP_ERR_TIMEOUT;
        assert(R_GLCDC_Start(&ctrl)==FSP_ERR_TIMEOUT);
        assert(!review_regs.BG.EN_b.EN && !review_regs.BG.EN_b.VEN);
        assert(ctrl.state==DISPLAY_STATE_OPENED && dsi_starts==1);
    }
    else if (scenario == 5)
    {
        uint32_t palette[256]={0x12345678};
        display_clut_cfg_t clut={.p_base=palette,.start=255,.size=256};
        displaying();
        assert(R_GLCDC_ClutUpdate(&ctrl,&clut,0)==FSP_ERR_INVALID_CLUT_ACCESS);
        clut.size=1;
        assert(R_GLCDC_ClutUpdate(&ctrl,&clut,0)==FSP_SUCCESS);
        assert(review_regs.GR1_CLUT1[255]==palette[0] && review_regs.GR[0].VEN_b.PVEN);
        assert(R_GLCDC_ClutUpdate(&ctrl,&clut,0)==FSP_ERR_INVALID_UPDATE_TIMING);
    }
    else if (scenario == 6)
    {
        displaying();
        assert(R_GLCDC_ClutEdit(&ctrl,0,4,0x12345678)==FSP_SUCCESS);
        assert(review_regs.GR1_CLUT1[4]==0x12345678 && review_regs.GR[0].VEN_b.PVEN);
        assert(R_GLCDC_ClutEdit(&ctrl,0,5,0xabcdef)==FSP_ERR_INVALID_UPDATE_TIMING);
        review_regs.GR[0].VEN=0;
        assert(R_GLCDC_ClutEdit(&ctrl,0,5,0xabcdef)==FSP_SUCCESS);
        assert(review_regs.GR1_CLUT0[4]==0x12345678 && review_regs.GR1_CLUT0[5]==0xabcdef);
    }
    else if (scenario == 7)
    {
        displaying(); display_runtime_cfg_t r=runtime();
        r.input.p_base++;
        uint32_t old=review_regs.GR[0].FLM2;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_ALIGNMENT);
        assert(review_regs.GR[0].FLM2==old && review_regs.GR[0].VEN==0);
        r=runtime(); r.input.hstride=63;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_ALIGNMENT);
        r=runtime(); r.input.hstride=32768;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_LAYER_SETTING);
        r=runtime(); r.input.hsize=63;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_LAYER_SETTING);
        r=runtime(); r.input.lines_repeat_enable=true; r.input.lines_repeat_times=0;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_LAYER_SETTING);
        r=runtime(); r.input.vsize=2045;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_ERR_INVALID_LAYER_SETTING);
        assert(review_regs.GR[0].FLM2==old && review_regs.GR[0].VEN==0);
    }
    else if (scenario == 8)
    {
        displaying(); display_runtime_cfg_t r=runtime();
        r.layer.coordinate.x=640;
        review_regs.GR[0].FLM5=0x12345678;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_SUCCESS);
        assert(review_regs.GR[0].FLMRD==0 && review_regs.GR[0].AB1_b.DISPSEL==1);
        assert(review_regs.GR[0].FLM5==0x12345678);
        review_regs.GR[0].VEN=0; r=runtime(); r.layer.coordinate.y=-32;
        assert(R_GLCDC_LayerChange(&ctrl,&r,0)==FSP_SUCCESS);
        assert(review_regs.GR[0].FLMRD==0 && review_regs.GR[0].FLM5==0x12345678);
    }
    else if (scenario == 9)
    {
        displaying(); display_runtime_cfg_t r=runtime();
        review_regs.GR[1].CLUTINT=0x100a5;
        assert(R_GLCDC_LayerChange(&ctrl,&r,1)==FSP_SUCCESS);
        assert(review_regs.GR[1].CLUTINT==0x100a5);
        assert(review_regs.GR[1].FLM5==((31U<<16)|1U));
    }
    else if (scenario == 10)
    {
        cfg.output.htiming.total_cyc=cfg.output.vtiming.total_cyc=2048;
        opened(); assert(review_regs.BG.PERI==0x07ff07ff);
    }
    else if (scenario == 11)
    {
#if GLCDC_CFG_PARAM_CHECKING_ENABLE && GLCDC_CFG_COLOR_CORRECTION_ENABLE
        uint16_t gain[16], threshold[16];
        for (unsigned i=0;i<16;++i) { gain[i]=1024; threshold[i]=(uint16_t)(i*64); }
        threshold[2]=threshold[1];
        display_gamma_correction_t gamma = {.g={.enable=true,.gain=gain,.threshold=threshold}};
        cfg.output.p_gamma_correction=&gamma;
        assert(R_GLCDC_Open(&ctrl,&cfg)==FSP_ERR_INVALID_GAMMA_SETTING);
        threshold[0]=1; threshold[2]=128;
        assert(R_GLCDC_Open(&ctrl,&cfg)==FSP_ERR_INVALID_GAMMA_SETTING);
        threshold[0]=0;
        for (unsigned i=1;i<16;++i) threshold[i]=1023;
        opened();
#endif
    }
    else if (scenario == 12) /* no reflection or palette access without readiness */
    {
        opened(); monitor(0); event_count=0;
        assert(R_GLCDC_Start(&ctrl)==FSP_ERR_TIMEOUT);
        assert(!dsi_starts && !review_regs.BG.EN_b.EN);
        uint32_t p=1; display_clut_cfg_t c={.p_base=&p,.size=1};
        assert(R_GLCDC_ClutUpdate(&ctrl,&c,0)==FSP_ERR_TIMEOUT);
        assert(R_GLCDC_ClutEdit(&ctrl,0,0,1)==FSP_ERR_TIMEOUT);
    }
    else if (scenario == 13) /* MON.VEN and gamma pending are independently unsafe. */
    {
        displaying(); monitor(0x10101);
        assert(R_GLCDC_Stop(&ctrl)==FSP_ERR_INVALID_UPDATE_TIMING);
        monitor(0x10001); review_regs.GAM[2].LATCH=1;
        assert(R_GLCDC_Stop(&ctrl)==FSP_ERR_INVALID_UPDATE_TIMING);
    }
    else if (scenario == 14) /* Atomic enable independently of gamma initialization. */
    {
        opened(); fault=8;
        assert(R_GLCDC_Start(&ctrl)==FSP_SUCCESS);
        (void) review_access();
        assert(word(0x1000)==0x10101);
    }
    else if (scenario == 15) /* Standalone full-table update requests reflection after data and SEL. */
    {
        displaying();
        uint32_t p=0xdeadbeef;
        display_clut_cfg_t c={.p_base=&p,.size=1};
        assert(R_GLCDC_ClutUpdate(&ctrl,&c,0)==FSP_SUCCESS);
        (void) review_access();
        assert(review_regs.GR1_CLUT1[0]==p && review_regs.GR[0].VEN_b.PVEN);
        size_t palette=512, select=512, reflect=512;
        for (size_t i=0;i<event_count;++i)
        {
            if (offsets[i]==0x400) palette=i;
            if (offsets[i]==0x1150) select=i;
            if (offsets[i]==0x1100) reflect=i;
        }
        assert(palette<select && select<reflect);
    }
    else if (scenario == 16) /* Pending per-module requests cannot overlap startup's global request. */
    {
        opened(); review_regs.GR[1].VEN=1;
        assert(R_GLCDC_Start(&ctrl)==FSP_ERR_INVALID_UPDATE_TIMING);
        assert(!dsi_starts && !review_regs.BG.EN_b.EN);
        review_regs.GR[1].VEN=0;
        uint32_t p=0x5555;
        display_clut_cfg_t c={.p_base=&p,.size=1};
        assert(R_GLCDC_ClutUpdate(&ctrl,&c,0)==FSP_SUCCESS);
        assert(!review_regs.GR[0].VEN_b.PVEN);
        assert(R_GLCDC_ClutEdit(&ctrl,1,3,p)==FSP_SUCCESS);
        assert(!review_regs.GR[1].VEN_b.PVEN);
        assert(R_GLCDC_Start(&ctrl)==FSP_SUCCESS);
        (void) review_access();
        assert(word(0x1000)==0x10101);
    }
    else abort();
    puts("GLCDC review passed");
    return 0;
}
