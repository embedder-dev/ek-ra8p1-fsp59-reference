#ifndef WDT_TEST_BSP_CFG_H
#define WDT_TEST_BSP_CFG_H

#define BSP_FEATURE_WDT_PER_CORE TEST_PER_CORE
#define BSP_CFG_CPU_CORE TEST_CORE

/* Unselected OFS word deliberately disagrees about every relevant field. */
#if TEST_PER_CORE && TEST_CORE == 1
 #define BSP_CFG_ROM_REG_OFS0 TEST_OTHER_OFS
 #define BSP_CFG_ROM_REG_OFS3 TEST_SELECTED_OFS
#else
 #define BSP_CFG_ROM_REG_OFS0 TEST_SELECTED_OFS
 #define BSP_CFG_ROM_REG_OFS3 TEST_OTHER_OFS
#endif

#endif
