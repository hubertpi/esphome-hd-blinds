"""Test real ADC lifecycle, six-hour cadence and extended-clock scheduling."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class BatterySamplingTests(unittest.TestCase):
 def test_sampling_sleep_abort_and_long_uptime(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as d:
   w=Path(d)
   (w/'fake.h').write_text(r'''
#pragma once
#include <stdint.h>
#include <stdbool.h>
static uint64_t clock_ms;
static int em1;
static bool divider,adc_clock;
typedef struct {uint32_t STATUS;} ADC;
static ADC adc={1};
#define ADC0 (&adc)
#define ADC_STATUS_SINGLEDV 1
#define cmuClock_ADC0 0
#define gpioPortF 5
#define gpioModePushPull 0
#define adcRef2V5 0
#define adcPosSelAPORT1XCH20 0
#define adcNegSelVSS 0
#define adcAcqTime256 0
#define adcStartSingle 0
#define SL_POWER_MANAGER_EM1 1
typedef struct {int timebase,prescale;} ADC_Init_TypeDef;
typedef struct {int reference,posSel,negSel,acqTime;} ADC_InitSingle_TypeDef;
#define ADC_INIT_DEFAULT {0,0}
#define ADC_INITSINGLE_DEFAULT {0,0,0,0}
static uint64_t sl_sleeptimer_get_tick_count64(void){return clock_ms;}
static int sl_sleeptimer_tick64_to_ms(uint64_t t,uint64_t *m){*m=t;return 0;}
static void ADC_Reset(ADC *a){}
static void ADC_Init(ADC *a,void *p){}
static void ADC_InitSingle(ADC *a,void *p){}
static void ADC_Start(ADC *a,int m){}
static int ADC_TimebaseCalc(int v){return 0;}
static int ADC_PrescaleCalc(int a,int b){return 0;}
static unsigned ADC_DataSingleGet(ADC *a){return 2091;}
static void CMU_ClockEnable(int c,bool v){adc_clock=v;}
static void GPIO_PinOutClear(int p,int n){divider=false;}
static void GPIO_PinModeSet(int p,int n,int m,int v){divider=v;}
static void sl_power_manager_add_em_requirement(int e){em1++;}
static void sl_power_manager_remove_em_requirement(int e){em1--;}
''')
   for name in ['em_adc.h','em_cmu.h','em_gpio.h','sl_sleeptimer.h','sl_power_manager.h']:
    (w/name).write_text('#include "fake.h"\n')
   (w/'test.c').write_text(r'''
#include <assert.h>
#include "battery.c"
int main(void){
 hd_battery_tick(true);assert(divider && adc_clock && em1==1 && hd_battery_delay()==100);
 clock_ms+=100;hd_battery_tick(true);
 for(int n=0;n<8;n++)hd_battery_tick(true);
 assert(!divider && !adc_clock && em1==0);
 assert(hd_battery_mv()>=3900 && hd_battery_mv()<=4100);
 assert(hd_battery_delay()==21600000);
 clock_ms+=21600000-1;hd_battery_tick(true);assert(!divider && hd_battery_delay()==1);
 clock_ms++;hd_battery_tick(true);assert(divider);
 hd_battery_tick(false);assert(!divider && !adc_clock && em1==0);
 /* Former 32-bit hardware tick conversion wrapped after about 36 h. */
 clock_ms=131072000ull+1234;hd_battery_tick(true);assert(divider);
 clock_ms+=100;hd_battery_tick(true);
 for(int n=0;n<8;n++)hd_battery_tick(true);
 assert(hd_battery_delay()==21600000 && !em1);
 return 0;
}
''')
   subprocess.run(['gcc','-std=c11','-I'+d,'-I'+str(root/'firmware/src'),str(w/'test.c'),'-o',str(w/'test')],check=True)
   subprocess.run([str(w/'test')],check=True)
