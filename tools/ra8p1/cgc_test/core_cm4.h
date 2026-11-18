/* Native compilation supplies register qualifiers, not a processor model. */
#ifndef CGC_TEST_CORE_CM4_H
#define CGC_TEST_CORE_CM4_H
#define __CORTEX_M 4U
#define __IM volatile const
#define __OM volatile
#define __IOM volatile
#endif
