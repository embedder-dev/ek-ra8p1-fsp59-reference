/* generated vector header file - do not edit */
        #ifndef VECTOR_DATA_H
        #define VECTOR_DATA_H
        #ifdef __cplusplus
        extern "C" {
        #endif
                /* Number of interrupts allocated */
        #ifndef VECTOR_DATA_IRQ_COUNT
        #define VECTOR_DATA_IRQ_COUNT    (7)
        #endif
        /* ISR prototypes */
        void sci_b_uart_rxi_isr(void);
        void sci_b_uart_txi_isr(void);
        void sci_b_uart_tei_isr(void);
        void sci_b_uart_eri_isr(void);
        void gpt_counter_overflow_isr(void);
        void pdm_dat_isr(void);
        void pdm_err_isr(void);

        /* Vector table allocations */
        #define VECTOR_NUMBER_SCI8_RXI ((IRQn_Type) 0) /* SCI8_RXI */
        #define SCI8_RXI_IRQn          ((IRQn_Type) 0) /* SCI8_RXI */
        #define VECTOR_NUMBER_SCI8_TXI ((IRQn_Type) 1) /* SCI8_TXI */
        #define SCI8_TXI_IRQn          ((IRQn_Type) 1) /* SCI8_TXI */
        #define VECTOR_NUMBER_SCI8_TEI ((IRQn_Type) 2) /* SCI8_TEI */
        #define SCI8_TEI_IRQn          ((IRQn_Type) 2) /* SCI8_TEI */
        #define VECTOR_NUMBER_SCI8_ERI ((IRQn_Type) 3) /* SCI8_ERI */
        #define SCI8_ERI_IRQn          ((IRQn_Type) 3) /* SCI8_ERI */
        #define VECTOR_NUMBER_GPT0_COUNTER_OVERFLOW ((IRQn_Type) 4) /* GPT0 COUNTER OVERFLOW (Overflow) */
        #define GPT0_COUNTER_OVERFLOW_IRQn          ((IRQn_Type) 4) /* GPT0 COUNTER OVERFLOW (Overflow) */
        #define VECTOR_NUMBER_PDM_DAT2 ((IRQn_Type) 5) /* PDM_DAT2 */
        #define PDM_DAT2_IRQn          ((IRQn_Type) 5) /* PDM_DAT2 */
        #define VECTOR_NUMBER_PDM_ERR2 ((IRQn_Type) 6) /* PDM_ERR2 */
        #define PDM_ERR2_IRQn          ((IRQn_Type) 6) /* PDM_ERR2 */
        /* The number of entries required for the ICU vector table. */
        #define BSP_ICU_VECTOR_NUM_ENTRIES (7)

        #ifdef __cplusplus
        }
        #endif
        #endif /* VECTOR_DATA_H */
