"""Compile the actual OTA C state machine against a bounded storage model."""
import pathlib
import subprocess
import tempfile
import unittest

class OTAStateTests(unittest.TestCase):
    def test_ota_storage_guards_and_verification(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)
            (p/'btl_interface.h').write_text('''
#include <stdint.h>
#define BOOTLOADER_OK 0
#define BOOTLOADER_ERROR_PARSE_CONTINUE 0x1001
#define BOOTLOADER_ERROR_PARSE_SUCCESS 0x1000
#define BOOTLOADER_STORAGE_VERIFICATION_CONTEXT_SIZE 384
typedef struct {uint32_t type,version;} BootloaderInformation_t;
int bootloader_init(void);
void bootloader_getInfo(BootloaderInformation_t *p);
void bootloader_rebootAndInstall(void);
''')
            (p/'btl_interface_storage.h').write_text('''
#include <stddef.h>
#include <stdint.h>
typedef struct {uint32_t address,length;} BootloaderStorageSlot_t;
int bootloader_getStorageSlotInfo(uint32_t id,BootloaderStorageSlot_t *p);
int bootloader_writeStorage(uint32_t id,uint32_t off,uint8_t *p,size_t n);
int bootloader_eraseRawStorage(uint32_t address,size_t length);
int bootloader_initVerifyImage(uint32_t id,void *context,size_t n);
int bootloader_continueVerifyImage(void *context,void *cb);
int bootloader_setImageToBootload(uint32_t id);
''')
            (p/'sl_sleeptimer.h').write_text('''
#include <stdint.h>
uint32_t sl_sleeptimer_get_tick_count(void);
uint32_t sl_sleeptimer_tick_to_ms(uint32_t x);
''')
            (p/'test.c').write_text('''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "btl_interface.h"
#include "btl_interface_storage.h"
#include "ota.h"
static uint32_t clock_ms,slot_size=0x37000;
static unsigned erased,writes,scheduled,reboots;
static int verify_result=BOOTLOADER_ERROR_PARSE_SUCCESS;
uint32_t sl_sleeptimer_get_tick_count(void){return clock_ms;}
uint32_t sl_sleeptimer_tick_to_ms(uint32_t x){return x;}
int bootloader_init(void){return 0;}
void bootloader_getInfo(BootloaderInformation_t *p){p->version=1;}
int bootloader_getStorageSlotInfo(uint32_t id,BootloaderStorageSlot_t *p){assert(id==0);p->address=0x40000;p->length=slot_size;return 0;}
int bootloader_eraseRawStorage(uint32_t a,size_t n){assert(a>=0x40000 && a+n<=0x77000 && n==2048);erased++;return 0;}
int bootloader_writeStorage(uint32_t id,uint32_t off,uint8_t *p,size_t n){assert(id==0 && off+n<=slot_size && !(off%4) && !(n%4));writes++;return 0;}
int bootloader_initVerifyImage(uint32_t id,void *c,size_t n){return n>=384?0:1;}
int bootloader_continueVerifyImage(void *c,void *cb){return verify_result;}
int bootloader_setImageToBootload(uint32_t id){scheduled++;return 0;}
void bootloader_rebootAndInstall(void){reboots++;}
static void ctrl(uint8_t *p,unsigned op,unsigned total){memset(p,0,16);p[0]=1;p[1]=op;p[4]=total;p[5]=total>>8;p[6]=total>>16;}
int main(void){
 uint8_t p[16],status[16],data[36]={0};
 ctrl(p,1,32);slot_size=0x40000;assert(hd_ota_control(p,16)!=0);assert(!erased);
 slot_size=0x37000;ctrl(p,1,32);assert(hd_ota_control(p,16)==0);
 hd_ota_tick();assert(erased==1);hd_ota_status(status);assert(status[1]==2);
 data[0]=4;assert(hd_ota_data(data,36)!=0);assert(!writes);
 data[0]=0;assert(hd_ota_data(data,35)!=0);assert(!writes);
 assert(hd_ota_data(data,36)==0);assert(writes==1);
 assert(hd_ota_data(data,36)!=0);assert(writes==1);
 ctrl(p,2,0);assert(hd_ota_control(p,16)==0);
 verify_result=0x1005;hd_ota_tick();hd_ota_status(status);assert(status[1]==6 && !scheduled);
 ctrl(p,3,0);assert(hd_ota_control(p,16)==0);
 ctrl(p,1,32);assert(hd_ota_control(p,16)==0);hd_ota_disconnect();assert(!hd_ota_busy() && !scheduled);
 ctrl(p,3,0);hd_ota_control(p,16);ctrl(p,1,32);hd_ota_control(p,16);hd_ota_tick();
 assert(hd_ota_data(data,36)==0);ctrl(p,2,0);assert(hd_ota_control(p,16)==0);
 verify_result=BOOTLOADER_ERROR_PARSE_CONTINUE;hd_ota_tick();assert(!scheduled);
 verify_result=BOOTLOADER_ERROR_PARSE_SUCCESS;hd_ota_tick();assert(scheduled==1 && !reboots);
 clock_ms=2000;hd_ota_tick();assert(reboots==1);
 return 0;
}
''')
            subprocess.run(['gcc','-std=c11','-I'+temp,'-I'+str(root/'firmware/src'),
                            str(root/'firmware/src/ota.c'),str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)
