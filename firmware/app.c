/* HD Blind experimental replacement firmware. SPDX-License-Identifier: MIT */
#include <string.h>
#include <stdio.h>
#include "app.h"
#include "sl_bluetooth.h"
#include "gatt_db.h"
#include "app_timer.h"
#include "sl_sleeptimer.h"
#include "sl_power_manager.h"
#include "nvm3_default.h"
#include "mbedtls/md.h"
#include "sl_bt_in_place_ota_dfu.h"
#include "src/board.h"

#define KEY_OBJECT 0x48001
#define SETTINGS_OBJECT 0x48002
static uint8_t adv=0xff,conn=0xff,nonce[16],key[32];
static bool paired,authenticated,subscribed;
static uint32_t pairing_until,pressed_at,start_at,stop_at,last_notify;
static uint8_t direction,result,fault;
static bool motor_em1;
static uint16_t sequence;
/* version, up, down, startup, ramp milliseconds LE, run timeout milliseconds LE */
static uint8_t settings[8]={1,65,60,75,250,0,0x10,0x27};
static app_timer_t ticker;
static uint32_t now_ms(void) {return sl_sleeptimer_tick_to_ms(sl_sleeptimer_get_tick_count());}
static uint16_t u16(const uint8_t *p) {return p[0]|((uint16_t)p[1]<<8);}
static uint32_t u32(const uint8_t *p) {return u16(p)|((uint32_t)u16(p+2)<<16);}
static void put16(uint8_t *p,uint16_t v) {p[0]=v;p[1]=v>>8;}
static void put32(uint8_t *p,uint32_t v) {put16(p,v);put16(p+2,v>>16);}
static bool pairing(void) {return (int32_t)(pairing_until-now_ms())>0;}
static void stop(void) {
  board_stop();direction=0;
  if(motor_em1) {sl_power_manager_remove_em_requirement(SL_POWER_MANAGER_EM1);motor_em1=false;}
}
static void status(uint8_t out[20]) {
  memset(out,0,20);out[0]=1;out[1]=fault?3:direction;
  uint8_t charge=board_charger_raw(); /* PC7 active-low; PB13 wall power active-low. */
  put16(out+2,(paired?1:0)|(pairing()?2:0)|(authenticated?4:0)|(!(charge&1)?8:0)|(!(charge&2)?16:0)|128);
  put16(out+4,sequence);out[6]=result;out[7]=255;out[8]=255;out[9]=fault;
  put32(out+10,(uint32_t)board_position());put32(out+14,board_pulses());
  put16(out+18,(uint16_t)(now_ms()/1000));
}
static void notify(void) {
  uint8_t data[20];status(data);
  if(conn!=0xff && subscribed) sl_bt_gatt_server_send_notification(conn,gattdb_hd_status,20,data);
}
static void tick(app_timer_t *timer,void *data) {
  (void)timer;(void)data;
  uint32_t now=now_ms();
  if(board_button()) {
    if(!pressed_at) pressed_at=now?now:1;
    if(pressed_at!=UINT32_MAX && now-pressed_at>=3000) {
      stop();pairing_until=now+90000;pressed_at=UINT32_MAX;
    }
  } else pressed_at=0;
  if(direction) {
    if((int32_t)(now-stop_at)>=0) {stop();fault=2;}
    else if(now-start_at>=20) {
      uint32_t elapsed=now-start_at-20,ramp=u16(settings+4);
      uint8_t target=settings[direction],duty=target;
      if(elapsed<ramp) duty=50+(settings[3]-50)*elapsed/(ramp?ramp:1);
      board_drive(direction,duty);
    }
  }
  /* Factory pairing: PD14 blue, 500 ms on per second. Charging: PD13 red. */
  bool charging=!(board_charger_raw()&1);
  board_leds(fault?((now/500)&1):(charging && now%2400<500), pairing() && ((now/500)&1));
  if(now-last_notify>=250) {last_notify=now;notify();}
}
void app_init(void) {board_init();}
void app_process_action(void) {}
static bool valid_settings(const uint8_t *p,size_t len) {
  return len==8 && p[0]==1 && p[1]<=100 && p[2]<=100 && p[3]>=50 && p[3]<=100
    && u16(p+4)<=2000 && u16(p+6)>=100 && u16(p+6)<=10000;
}
static uint8_t command(const uint8_t *p,size_t len) {
  if(len!=8 || p[0]!=1) return 2;
  if(!authenticated) return 1;
  sequence=u16(p+2);
  uint32_t duration=u32(p+4);
  switch(p[1]) {
    case 0:return 0;
    case 1:case 2:
      if(!settings[p[1]]) {stop();return 0;}
      if(fault) return 6;
      if(duration>u16(settings+6)) return 3;
      stop();sl_power_manager_add_em_requirement(SL_POWER_MANAGER_EM1);motor_em1=true;
      direction=p[1];start_at=now_ms();stop_at=start_at+(duration?duration:u16(settings+6));return 0;
    case 3:stop();return 0;
    case 4:if(direction) return 4;board_zero();return 0;
    case 5:stop();pairing_until=now_ms()+90000;return 0;
    case 9:stop();fault=0;return 0;
    default:return 5;
  }
}
void sl_bt_on_event(sl_bt_msg_t *evt) {
  switch(SL_BT_MSG_ID(evt->header)) {
    case sl_bt_evt_system_boot_id: {
      if(nvm3_readData(nvm3_defaultHandle,KEY_OBJECT,key,32)==ECODE_NVM3_OK) paired=true;
      else {
        size_t n=0;
        if(sl_bt_system_get_random_data(32,32,&n,key)!=SL_STATUS_OK || n!=32) {fault=3;break;}
        if(nvm3_writeData(nvm3_defaultHandle,KEY_OBJECT,key,32)!=ECODE_NVM3_OK) {fault=3;break;}
        paired=true;pairing_until=now_ms()+90000;
      }
      uint8_t saved[8];
      if(nvm3_readData(nvm3_defaultHandle,SETTINGS_OBJECT,saved,8)==ECODE_NVM3_OK && valid_settings(saved,8)) memcpy(settings,saved,8);
      app_timer_start(&ticker,10,tick,NULL,true);
      bd_addr identity; uint8_t address_type; char name[14];
      if(sl_bt_system_get_identity_address(&identity,&address_type)==SL_STATUS_OK) {
        snprintf(name,sizeof(name),"HD Blind %02X%02X",identity.addr[1],identity.addr[0]);
        sl_bt_gatt_server_write_attribute_value(gattdb_device_name,0,13,(const uint8_t *)name);
      }
      sl_bt_advertiser_create_set(&adv);
      sl_bt_legacy_advertiser_generate_data(adv,sl_bt_advertiser_general_discoverable);
      sl_bt_advertiser_set_timing(adv,160,320,0,0);
      sl_bt_legacy_advertiser_start(adv,sl_bt_legacy_advertiser_connectable);
      break;
    }
    case sl_bt_evt_connection_opened_id: {
      conn=evt->data.evt_connection_opened.connection;authenticated=false;subscribed=false;
      size_t n=0;
      if(sl_bt_system_get_random_data(16,16,&n,nonce)!=SL_STATUS_OK || n!=16) sl_bt_connection_close(conn);
      break;
    }
    case sl_bt_evt_connection_closed_id:
      stop();conn=0xff;authenticated=false;subscribed=false;
      sl_bt_legacy_advertiser_start(adv,sl_bt_legacy_advertiser_connectable);break;
    case sl_bt_evt_gatt_server_characteristic_status_id:
      if(evt->data.evt_gatt_server_characteristic_status.characteristic==gattdb_hd_status)
        subscribed=(evt->data.evt_gatt_server_characteristic_status.client_config_flags&1)!=0;
      break;
    case sl_bt_evt_gatt_server_user_read_request_id: {
      sl_bt_evt_gatt_server_user_read_request_t *e=&evt->data.evt_gatt_server_user_read_request;
      uint8_t buf[32],error=0;size_t length=0;uint16_t sent;
      if(e->characteristic==gattdb_hd_status) {status(buf);length=20;}
      else if(e->characteristic==gattdb_hd_settings) {memcpy(buf,settings,8);length=8;}
      else if(e->characteristic==gattdb_hd_auth) {memcpy(buf,nonce,16);length=16;}
      else if(e->characteristic==gattdb_hd_enroll && pairing()) {memcpy(buf,key,32);length=32;}
      else error=0x08;
      if(e->offset>length) error=0x07;
      sl_bt_gatt_server_send_user_read_response(e->connection,e->characteristic,error,
        error?0:length-e->offset,buf+(error?0:e->offset),&sent);
      break;
    }
    case sl_bt_evt_gatt_server_user_write_request_id: {
      sl_bt_evt_gatt_server_user_write_request_t *e=&evt->data.evt_gatt_server_user_write_request;
      uint8_t error=0;
      if(e->characteristic==gattdb_hd_auth) {
        uint8_t mac[32],different=0;
        int rc=mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),key,32,nonce,16,mac);
        if(rc || e->value.len!=16) error=0x08;
        else {for(unsigned i=0;i<16;i++) different|=mac[i]^e->value.data[i];if(different) error=0x08;}
        authenticated=error==0;
      } else if(e->characteristic==gattdb_hd_command) result=command(e->value.data,e->value.len);
      else if(e->characteristic==gattdb_hd_settings) {
        if(!authenticated) error=0x08;
        else if(direction) error=0x80;
        else if(!valid_settings(e->value.data,e->value.len)) error=0x0d;
        else if(nvm3_writeData(nvm3_defaultHandle,SETTINGS_OBJECT,e->value.data,8)!=ECODE_NVM3_OK) error=0x80;
        else memcpy(settings,e->value.data,8);
      } else { /* OTA component handles its own characteristic. */ break; }
      sl_bt_gatt_server_send_user_write_response(e->connection,e->characteristic,error);notify();break;
    }
    default:break;
  }
}
/* Leave OTA entry disabled until matched bootloader and recovery are verified.
 * AppLoader is linked so the firmware layout already reserves its space. */
sl_bt_in_place_ota_dfu_security_sts_t sl_bt_in_place_ota_dfu_security_status(bd_addr a,uint8_t c,uint8_t b) {
  (void)a;(void)c;(void)b;return SL_BT_IN_PLACE_OTA_DFU_SECURITY_DENY;
}
