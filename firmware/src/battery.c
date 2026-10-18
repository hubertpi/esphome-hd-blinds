/* SPDX-License-Identifier: MIT. Factory divider: PF6, APORT1XCH20, 2.5 V, 147/47.
 * Percentage is an approximate single-cell Li-ion resting-voltage estimate.
 */
#include "battery.h"
#include "battery_curve.h"
#include "em_adc.h"
#include "em_cmu.h"
#include "em_gpio.h"
#include "sl_sleeptimer.h"
#include "sl_power_manager.h"
static uint16_t millivolts=0xffff,raw=0xffff;
static uint8_t phase,count;
static uint32_t deadline,next,samples;
static void off(void) {
 ADC_Reset(ADC0);CMU_ClockEnable(cmuClock_ADC0,false);GPIO_PinOutClear(gpioPortF,6);sl_power_manager_remove_em_requirement(SL_POWER_MANAGER_EM1);phase=0;
}
void hd_battery_tick(bool idle) {
 uint32_t now=sl_sleeptimer_tick_to_ms(sl_sleeptimer_get_tick_count());
 if(!idle) {if(phase)off();return;}
 if(!phase) {
  if((int32_t)(now-next)<0)return;
  GPIO_PinModeSet(gpioPortF,6,gpioModePushPull,1);
  CMU_ClockEnable(cmuClock_ADC0,true);
  ADC_Init_TypeDef init=ADC_INIT_DEFAULT;
  init.timebase=ADC_TimebaseCalc(0);init.prescale=ADC_PrescaleCalc(4000000,0);
  ADC_Init(ADC0,&init);
  ADC_InitSingle_TypeDef single=ADC_INITSINGLE_DEFAULT;
  single.reference=adcRef2V5;single.posSel=adcPosSelAPORT1XCH20;
  single.negSel=adcNegSelVSS;single.acqTime=adcAcqTime256;
  ADC_InitSingle(ADC0,&single);
  sl_power_manager_add_em_requirement(SL_POWER_MANAGER_EM1);
  deadline=now+100;phase=1;samples=count=0;
 } else if(phase==1 && (int32_t)(now-deadline)>=0) {
  ADC_Start(ADC0,adcStartSingle);deadline=now+100;phase=2;
 } else if(phase==2) {
  if(ADC0->STATUS&ADC_STATUS_SINGLEDV) {
   samples+=ADC_DataSingleGet(ADC0);count++;
   if(count==8) {
    raw=(samples+4)/8;
    uint32_t mv=((uint32_t)raw*2500u*147u)/(4096u*47u);
    millivolts=(mv>=2500 && mv<=4350)?mv:0xffff;
    off();next=now+60000;
   } else {ADC_Start(ADC0,adcStartSingle);deadline=now+100;}
  } else if((int32_t)(now-deadline)>=0) {millivolts=raw=0xffff;off();next=now+60000;}
 }
}
uint16_t hd_battery_mv(void) {return millivolts;}
uint16_t hd_battery_raw(void) {return raw;}
uint8_t hd_battery_percent(void) {return hd_battery_estimate(millivolts);}
