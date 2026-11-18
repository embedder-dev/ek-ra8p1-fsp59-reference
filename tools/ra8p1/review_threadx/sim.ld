ENTRY(Reset_Handler)
MEMORY {
    FLASH (rx) : ORIGIN = 0x10000000, LENGTH = 512K
    RAM (rwx) : ORIGIN = 0x30000000, LENGTH = 32K
}
SECTIONS {
    .vectors : { KEEP(*(.vectors)) } > FLASH
    .text : { *(.text*) *(.rodata*) } > FLASH
    .ARM.exidx : { *(.ARM.exidx*) } > FLASH
    .data : { *(.data*) } > RAM
    .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
    __RAM_segment_used_end__ = .;
    /DISCARD/ : { *(.comment) *(.note*) }
}
