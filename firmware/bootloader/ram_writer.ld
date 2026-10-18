ENTRY(writer)
MEMORY { RAM (rwx) : ORIGIN = 0x20008000, LENGTH = 0x4000 }
SECTIONS {
  .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) *(.ram*) } > RAM
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }
}
