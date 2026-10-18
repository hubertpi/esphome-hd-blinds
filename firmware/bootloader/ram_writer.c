/* SPDX-License-Identifier: MIT
 * BG13 second-stage bootloader writer. Executes entirely from SRAM.
 * Source image: 0x20000000, exactly seven padded 2048-byte pages.
 * Result: 0x20007000 (0x4844424c = verified; other values indicate phase/error).
 * Preserves first stage 0x0FE10000..0x0FE107FF and all main/user/lock flash.
 */
#include "em_device.h"
#include "em_msc.h"
#include "em_wdog.h"
#define RESULT (*(volatile uint32_t *)0x20007000u)
#define BASE 0x0fe10800u
#define SIZE 0x3800u
static void feed(void) {
  if((WDOG0->CTRL&WDOG_CTRL_EN) && !(WDOG0->SYNCBUSY&3u)) WDOG0->CMD=1;
}
__attribute__((noreturn,section(".entry"))) void writer(void) {
  __disable_irq();
  RESULT=0x100;
  /* Write-once protection must be clear before modifying a single page. */
  if(MSC->BOOTLOADERCTRL&MSC_BOOTLOADERCTRL_BLWDIS) {RESULT=0xe001;goto done;}
  MSC_Init();
  for(uint32_t page=0;page<SIZE;page+=2048) {
    feed();RESULT=0x200+page/2048;
    MSC_Status_TypeDef rc=MSC_ErasePage((uint32_t *)(BASE+page));
    if(rc!=mscReturnOk) {RESULT=0xe100u+(uint32_t)(-rc);goto lock;}
    RESULT=0x300+page/2048;
    rc=MSC_WriteWord((uint32_t *)(BASE+page),(const void *)(0x20000000u+page),2048);
    if(rc!=mscReturnOk) {RESULT=0xe200u+(uint32_t)(-rc);goto lock;}
    MSC->CACHECMD=MSC_CACHECMD_INVCACHE; __DSB(); __ISB();
    const volatile uint32_t *dst=(const volatile uint32_t *)(BASE+page);
    const uint32_t *src=(const uint32_t *)(0x20000000u+page);
    for(unsigned i=0;i<512;i++) if(dst[i]!=src[i]) {RESULT=0xe300u;goto lock;}
  }
  RESULT=0x4844424c;
lock:
  MSC_Deinit();
done:
  __asm volatile("bkpt #0");
  for(;;) {}
}
