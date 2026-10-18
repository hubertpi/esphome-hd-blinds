/* Board REV.J, BGM13P22. Pin mapping recovered from factory firmware.
 * Factory LED task: pairing flag 4 drives PD14; wall-charge flag 16 drives PD13.
 */
#include "board.h"
#include "em_cmu.h"
#include "em_gpio.h"
#include "em_timer.h"
#include "em_core.h"
static volatile int32_t position;
static volatile uint32_t pulses;
static volatile uint8_t direction;
void board_stop(void) {
  GPIO_PinOutClear(gpioPortD,15); /* Disable bridge before changing inputs. */
  TIMER_Enable(TIMER0,false);
  TIMER0->ROUTEPEN=0;
  for(unsigned i=0;i<4;i++) GPIO_PinOutClear(gpioPortA,i);
  GPIO_PinOutClear(gpioPortF,5);
  direction=0;
}
void board_init(void) {
  CMU_ClockEnable(cmuClock_GPIO,true);
  CMU_ClockEnable(cmuClock_TIMER0,true);
  GPIO_PinModeSet(gpioPortD,15,gpioModePushPull,0);
  GPIO_PinModeSet(gpioPortF,5,gpioModePushPull,0);
  for(unsigned i=0;i<4;i++) GPIO_PinModeSet(gpioPortA,i,gpioModePushPull,0);
  GPIO_PinModeSet(gpioPortD,13,gpioModePushPull,0);
  GPIO_PinModeSet(gpioPortD,14,gpioModePushPull,0);
  GPIO_PinModeSet(gpioPortB,13,gpioModeInputPullFilter,1);
  GPIO_PinModeSet(gpioPortC,7,gpioModeInputPull,1);
  GPIO_PinModeSet(gpioPortC,8,gpioModeInputPullFilter,1);
  GPIO_PinModeSet(gpioPortC,11,gpioModeInput,0);
  GPIO_ExtIntConfig(gpioPortC,11,11,true,false,true);
  NVIC_ClearPendingIRQ(GPIO_ODD_IRQn); NVIC_EnableIRQ(GPIO_ODD_IRQn);
  TIMER_Init_TypeDef ti=TIMER_INIT_DEFAULT;
  ti.enable=false; ti.prescale=timerPrescale16;
  TIMER_Init(TIMER0,&ti);
  TIMER_InitCC_TypeDef cc=TIMER_INITCC_DEFAULT;
  cc.mode=timerCCModePWM; cc.edge=timerEdgeBoth; cc.cmoa=timerOutputActionToggle;
  TIMER_InitCC(TIMER0,0,&cc); TIMER_InitCC(TIMER0,1,&cc);
  TIMER_TopSet(TIMER0,120);
  board_stop();
}
void GPIO_ODD_IRQHandler(void) {
  uint32_t flags=GPIO_IntGetEnabled(); GPIO_IntClear(flags);
  if((flags&(1u<<11)) && direction) {
    pulses++;
    /* Match factory signed count: direction 1 decreases, direction 2 increases. */
    if(direction==1) { if(position>INT32_MIN) position--; }
    else { if(position<INT32_MAX) position++; }
  }
}
void board_drive(uint8_t dir,uint8_t duty) {
  if(!duty || (dir!=1 && dir!=2)) {board_stop();return;}
  if(dir!=direction) {
    board_stop();
    TIMER0->ROUTELOC0=dir==1?2u:0x1f03u;
    TIMER_CompareSet(TIMER0,0,121u*duty/100u);
    TIMER_CompareSet(TIMER0,1,121u*duty/100u);
    TIMER_CounterSet(TIMER0,0);
    direction=dir;
    GPIO_PinOutSet(gpioPortF,5);
    TIMER0->ROUTEPEN=TIMER_ROUTEPEN_CC0PEN|TIMER_ROUTEPEN_CC1PEN;
    TIMER_Enable(TIMER0,true);
    GPIO_PinOutSet(gpioPortD,15);
  } else {
    TIMER_CompareBufSet(TIMER0,0,121u*duty/100u);
    TIMER_CompareBufSet(TIMER0,1,121u*duty/100u);
  }
}
void board_leds(bool a,bool b) {
  if(a) GPIO_PinOutSet(gpioPortD,13); else GPIO_PinOutClear(gpioPortD,13);
  if(b) GPIO_PinOutSet(gpioPortD,14); else GPIO_PinOutClear(gpioPortD,14);
}
bool board_button(void) {return !GPIO_PinInGet(gpioPortC,8);}
uint8_t board_charger_raw(void) {
  return GPIO_PinInGet(gpioPortC,7)|(GPIO_PinInGet(gpioPortB,13)<<1);
}
int32_t board_position(void) {return position;}
uint32_t board_pulses(void) {return pulses;}
void board_zero(void) {CORE_DECLARE_IRQ_STATE;CORE_ENTER_ATOMIC();position=0;pulses=0;CORE_EXIT_ATOMIC();}
