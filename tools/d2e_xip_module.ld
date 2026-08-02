OUTPUT_ARCH(xtensa)

SECTIONS
{
    .irom 0x00000000 : ALIGN(4)
    {
        *(.literal.program_region)
        *(.text.program_region)
        *(.literal.d2e_generated_cisc_step)
        *(.text.d2e_generated_cisc_step)
        *(.literal.d2e_generated_cisc_region_*)
        *(.text.d2e_generated_cisc_region_*)
        *(.literal .literal.*)
        *(.text .text.*)
    }

    .drom 0x10000000 : ALIGN(4)
    {
        *(.rodata .rodata.*)
    }

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.xtensa.info)
        *(.xt.lit)
        *(.xt.prop)
    }
}
