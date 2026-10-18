"""Run the real board driver with SDK register stubs to test endpoint lifecycle."""
import pathlib
import subprocess
import tempfile
import unittest

class BoardMotionTests(unittest.TestCase):
    def test_target_completion_clears_after_coast_before_opposite_move(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            work=pathlib.Path(directory)
            (work/'fake_sdk.h').write_text(r'''
#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct {uint32_t ROUTEPEN,ROUTELOC0;} Timer;
static Timer timer;
#define TIMER0 (&timer)
#define gpioPortA 0
#define gpioPortB 1
#define gpioPortC 2
#define gpioPortD 3
#define gpioPortF 5
#define gpioModePushPull 0
#define gpioModeInputPullFilter 1
#define gpioModeInputPull 2
#define gpioModeInput 3
#define cmuClock_GPIO 0
#define cmuClock_TIMER0 1
#define GPIO_ODD_IRQn 0
#define timerPrescale16 0
#define timerCCModePWM 0
#define timerEdgeBoth 0
#define timerOutputActionToggle 0
#define TIMER_ROUTEPEN_CC0PEN 1
#define TIMER_ROUTEPEN_CC1PEN 2
typedef struct {bool enable;int prescale;} TIMER_Init_TypeDef;
typedef struct {int mode,edge,cmoa;} TIMER_InitCC_TypeDef;
#define TIMER_INIT_DEFAULT {false,0}
#define TIMER_INITCC_DEFAULT {0,0,0}
#define CORE_DECLARE_IRQ_STATE
#define CORE_ENTER_ATOMIC()
#define CORE_EXIT_ATOMIC()
static uint32_t pins[6],irq_flags;
static bool timer_enabled;
static void GPIO_PinOutClear(int port,int pin){pins[port]&=~(1u<<pin);}
static void GPIO_PinOutSet(int port,int pin){pins[port]|=1u<<pin;}
static void GPIO_PinModeSet(int port,int pin,int mode,int value){(void)mode;if(value)GPIO_PinOutSet(port,pin);else GPIO_PinOutClear(port,pin);}
static int GPIO_PinInGet(int port,int pin){return !!(pins[port]&(1u<<pin));}
static uint32_t GPIO_IntGetEnabled(void){return irq_flags;}
static void GPIO_IntClear(uint32_t flags){irq_flags&=~flags;}
static void GPIO_ExtIntConfig(int p,int pin,int n,bool r,bool f,bool e){(void)p;(void)pin;(void)n;(void)r;(void)f;(void)e;}
static void NVIC_ClearPendingIRQ(int n){(void)n;}
static void NVIC_EnableIRQ(int n){(void)n;}
static void CMU_ClockEnable(int c,bool e){(void)c;(void)e;}
static void TIMER_Enable(Timer *t,bool enabled){(void)t;timer_enabled=enabled;}
static void TIMER_Init(Timer *t,void *v){(void)t;(void)v;}
static void TIMER_InitCC(Timer *t,int n,void *v){(void)t;(void)n;(void)v;}
static void TIMER_TopSet(Timer *t,unsigned v){(void)t;(void)v;}
static void TIMER_CompareSet(Timer *t,int n,unsigned v){(void)t;(void)n;(void)v;}
static void TIMER_CompareBufSet(Timer *t,int n,unsigned v){(void)t;(void)n;(void)v;}
static void TIMER_CounterSet(Timer *t,unsigned v){(void)t;(void)v;}
''')
            for header in ('em_cmu.h','em_gpio.h','em_timer.h','em_core.h'):
                (work/header).write_text('#include "fake_sdk.h"\n')
            (work/'test.c').write_text(r'''
#include <assert.h>
#include "board.c"
static void pulse(void){irq_flags|=1u<<11;GPIO_ODD_IRQHandler();}
int main(void){
 board_init();board_set_position(2);
 board_drive(1,65);board_target(true,0);
 pulse();assert(board_position()==1 && !board_target_reached());
 pulse();assert(board_position()==0 && board_target_reached());
 assert(!timer_enabled && !(pins[gpioPortD]&(1u<<15)));
 pulse();pulse(); /* coast beyond zero is valid and must remain counted */
 assert(board_position()==-2);
 board_stop();board_finish_stop();
 assert(!board_target_reached()); /* regression: stale latch cancelled next move */
 assert(!(pins[gpioPortF]&(1u<<5)));
 board_target(false,0);
 assert(!board_target_reached());
 board_drive(2,60);board_target(true,10);
 assert(timer_enabled && !board_target_reached());
 for(int n=0;n<12;n++)pulse();
 assert(board_position()==10 && board_target_reached());
 board_stop();board_finish_stop();assert(!board_target_reached());
 pulse();assert(board_position()==10); /* powered-down encoder ignored */
 return 0;
}
''')
            subprocess.run(['gcc','-std=c11','-I'+str(work),'-I'+str(root/'firmware/src'),
                            str(work/'test.c'),'-o',str(work/'test')],check=True)
            subprocess.run([str(work/'test')],check=True)
