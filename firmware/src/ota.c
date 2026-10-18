/* SPDX-License-Identifier: MIT. Staged GBL update; main flash untouched until verified. */
#include <string.h>
#include "ota.h"
#include "btl_interface.h"
#include "btl_interface_storage.h"
#include "sl_sleeptimer.h"
static uint32_t ota_now(void) {uint64_t ms=0;sl_sleeptimer_tick64_to_ms(sl_sleeptimer_get_tick_count64(),&ms);return (uint32_t)ms;}
static uint8_t state;
static uint16_t error;
static uint32_t written,total,erased,reboot_at,last_activity;
static BootloaderStorageSlot_t slot;
static uint32_t context[(BOOTLOADER_STORAGE_VERIFICATION_CONTEXT_SIZE+3)/4];
static uint32_t now(void) {return ota_now();}
static uint32_t get32(const uint8_t *p) {return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put32(uint8_t *p,uint32_t v) {for(unsigned i=0;i<4;i++) p[i]=v>>(8*i);}
static void fail(int32_t rc) {state=6;error=(uint16_t)rc;}
bool hd_ota_busy(void) {return state>=1 && state<=5;}
void hd_ota_disconnect(void) {if(state>=1 && state<=4) fail(0x8001);}
void hd_ota_status(uint8_t out[16]) {
 memset(out,0,16);out[0]=1;out[1]=state;out[2]=error;out[3]=error>>8;
 put32(out+4,written);put32(out+8,total);
 BootloaderInformation_t info;bootloader_getInfo(&info);put32(out+12,info.version);
}
uint8_t hd_ota_control(const uint8_t *p,size_t len) {
 if(len!=16 || p[0]!=1) return 0x0d;
 if(p[1]==3) {if(state==5)return 0x80;state=0;error=0;return 0;}
 if(p[1]==1) {
  if(hd_ota_busy())return 0x80;
  int32_t rc=bootloader_init();if(rc!=BOOTLOADER_OK){fail(rc);return 0x80;}
  rc=bootloader_getStorageSlotInfo(0,&slot);if(rc!=BOOTLOADER_OK){fail(rc);return 0x80;}
  total=get32(p+4);
  /* The installed loader reserves exactly this range, below NVM3 at 0x77000. */
  if(slot.address!=0x40000 || slot.length!=0x37000 || total<32 || total>slot.length || (total&3))return 0x0d;
  written=erased=0;error=0;state=1;last_activity=now();return 0;
 }
 if(p[1]==2) {
  if(state!=3 || written!=total)return 0x80;
  int32_t rc=bootloader_initVerifyImage(0,context,sizeof(context));
  if(rc!=BOOTLOADER_OK){fail(rc);return 0x80;}
  state=4;last_activity=now();return 0;
 }
 return 0x80;
}
uint8_t hd_ota_data(const uint8_t *p,size_t len) {
 if((state!=2 && state!=3) || len<8 || len>244 || (len&3))return 0x80;
 uint32_t offset=get32(p),size=len-4;
 if(offset!=written || size>total-written)return 0x0d;
 uint32_t aligned[60];memcpy(aligned,p+4,size);
 int32_t rc=bootloader_writeStorage(0,written,(uint8_t *)aligned,size);
 if(rc!=BOOTLOADER_OK){fail(rc);return 0x80;}
 written+=size;state=3;last_activity=now();return 0;
}
void hd_ota_tick(void) {
 if(state>=1 && state<=4 && now()-last_activity>120000) {fail(0x8002);return;}
 if(state==1) {
  int32_t rc=bootloader_eraseRawStorage(slot.address+erased,2048);
  if(rc!=BOOTLOADER_OK){fail(rc);return;}
  erased+=2048;
  if(erased>=((total+2047)&~2047u))state=2;
 } else if(state==4) {
  int32_t rc=bootloader_continueVerifyImage(context,NULL);
  if(rc==BOOTLOADER_ERROR_PARSE_CONTINUE)return;
  if(rc!=BOOTLOADER_ERROR_PARSE_SUCCESS){fail(rc);return;}
  rc=bootloader_setImageToBootload(0);
  if(rc!=BOOTLOADER_OK){fail(rc);return;}
  state=5;reboot_at=now()+1500;
 } else if(state==5 && (int32_t)(now()-reboot_at)>=0) bootloader_rebootAndInstall();
}
