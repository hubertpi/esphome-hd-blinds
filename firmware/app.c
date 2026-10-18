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
#include "src/ota.h"
#include "src/battery.h"
#include "src/motion.h"

#define KEY_OBJECT 0x48001
#define SETTINGS_OBJECT 0x48002
#define POSITION_OBJECT 0x48003
#define MOTION_SETTINGS_OBJECT 0x48004
static uint8_t adv=0xff,conn=0xff,nonce[16],key[32];
static bool paired,authenticated,subscribed;
static uint32_t pairing_until,pressed_at,start_at,stop_at,last_notify;
static uint8_t direction,result,fault;
static bool motor_em1;
static uint16_t sequence;
/* version, up, down, startup, ramp milliseconds LE, run timeout milliseconds LE */
static uint8_t settings[10]={2,65,60,75,250,0,0xc0,0xd4,0x01,0};
static app_timer_t ticker;
static hd_motion_t motion={.slow_up_pwm=60,.slow_down_pwm=55,.slow_counts=32};
static bool settling, save_pending, learn_stop;
static uint32_t settled_at, last_encoder_at, last_pulses;
static int32_t cut_position;
static uint8_t cut_direction;
/* Version 1 durable record: version/flags, travel, position, directional coast. */
static bool save_position(bool valid) {
  int32_t record[6];hd_motion_record(&motion,board_position(),valid,record);
  return nvm3_writeData(nvm3_defaultHandle,POSITION_OBJECT,record,sizeof(record))==ECODE_NVM3_OK;
}
static uint32_t now_ms(void) {return sl_sleeptimer_tick_to_ms(sl_sleeptimer_get_tick_count());}
static uint16_t u16(const uint8_t *p) {return p[0]|((uint16_t)p[1]<<8);}
static uint32_t u32(const uint8_t *p) {return u16(p)|((uint32_t)u16(p+2)<<16);}
static void put16(uint8_t *p,uint16_t v) {p[0]=v;p[1]=v>>8;}
static void put32(uint8_t *p,uint32_t v) {put16(p,v);put16(p+2,v>>16);}
static bool pairing(void) {return (int32_t)(pairing_until-now_ms())>0;}
static void stop(void) {
  if(direction) {
    cut_direction=direction;cut_position=board_target_reached()?board_cut_position():board_position();
    settled_at=now_ms()+HD_SETTLE_MS;settling=true;save_pending=true;
  }
  board_stop();direction=0;
  if(motor_em1) {sl_power_manager_remove_em_requirement(SL_POWER_MANAGER_EM1);motor_em1=false;}
}
static void status(uint8_t out[20]) {
  memset(out,0,20);out[0]=1;out[1]=hd_ota_busy()?4:(fault?3:direction);
  uint8_t charge=board_charger_raw(); /* PC7 active-low; PB13 wall power active-low. */
  put16(out+2,(paired?1:0)|(pairing()?2:0)|(authenticated?4:0)|(!(charge&1)?8:0)|(!(charge&2)?16:0)|128|256|hd_motion_flags(&motion)|(hd_battery_percent()!=255?64:0));
  put16(out+4,sequence);out[6]=result;out[7]=hd_battery_percent();out[8]=hd_motion_percent(&motion,board_position());out[9]=fault;
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
  hd_ota_tick();
  hd_battery_tick(!direction && !settling && !hd_ota_busy());
  if(settling && (int32_t)(now-settled_at)>=0) {
    board_finish_stop();settling=false;
    if(learn_stop)hd_motion_learn(&motion,cut_direction,cut_position,board_position());
    learn_stop=false;motion.targeting=false;
    if(save_pending && !save_position(motion.referenced && !motion.stage))fault=4;
    save_pending=false;notify();
  }
  if(board_button()) {
    if(!pressed_at) pressed_at=now?now:1;
    if(pressed_at!=UINT32_MAX && now-pressed_at>=3000) {
      stop();pairing_until=now+90000;pressed_at=UINT32_MAX;
    }
  } else pressed_at=0;
  if(direction) {
    hd_motion_sample(&motion,board_position(),now);
    if(board_pulses()!=last_pulses) {last_pulses=board_pulses();last_encoder_at=now;}
    if(board_target_reached() || hd_motion_should_stop(&motion,board_position(),direction)) {
      learn_stop=true;stop();
    } else if((int32_t)(now-stop_at)>=0) {
      bool was_targeting=motion.targeting;stop();if(was_targeting)fault=2;
    } else if(now-last_encoder_at>2000) {stop();fault=5;motion.referenced=false;}
    else if(now-start_at>=20) {
      uint32_t elapsed=now-start_at-20,ramp=u16(settings+4);
      uint8_t cruise=settings[direction],duty=cruise;
      if(elapsed<ramp)duty=50+(settings[3]-50)*elapsed/(ramp?ramp:1);
      uint8_t capped=hd_motion_duty(&motion,board_position(),direction,cruise);
      if(motion.targeting && duty>capped)duty=capped;
      board_drive(direction,duty);
      if(motion.targeting)board_target(true,motion.target);
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
  if((len!=8 || p[0]!=1) && (len!=10 || p[0]!=2))return false;
  uint32_t run=len==8?u16(p+6):u32(p+6);
  return p[1]<=100 && p[2]<=100 && p[3]>=50 && p[3]<=100 &&
    u16(p+4)<=2000 && run>=100 && run<=120000;
}
static uint8_t start_motion(uint8_t dir,uint32_t duration,bool targeting,int32_t target) {
  if(fault)return 6;
  if(direction || settling)return 4;
  if(!settings[dir])return 3;
  if(!save_position(false))return 6;
  motion.targeting=targeting;motion.target=target;
  motion.sampled_at=now_ms();motion.last_position=board_position();motion.velocity=0;
  last_pulses=board_pulses();last_encoder_at=now_ms();
  sl_power_manager_add_em_requirement(SL_POWER_MANAGER_EM1);motor_em1=true;
  direction=dir;start_at=now_ms();stop_at=start_at+duration;return 0;
}
static uint8_t move_target(uint8_t percent) {
  if(!motion.calibrated || !motion.referenced || motion.stage)return 3;
  int32_t target=hd_motion_target(&motion,percent),pos=board_position();
  if(target==pos)return 0;
  return start_motion(target<pos?1:2,u32(settings+6),true,target);
}
static uint8_t command(const uint8_t *p,size_t len) {
  if(len!=8 || p[0]!=1)return 2;
  if(!authenticated)return 1;
  if(hd_ota_busy())return 4;
  sequence=u16(p+2);uint32_t arg=u32(p+4);
  switch(p[1]) {
    case 0:return 0;
    case 1:case 2:
      if(motion.stage)return 4;
      if(motion.calibrated && !motion.referenced)return 3;
      if(motion.calibrated && motion.referenced) {if(arg)return 3;return move_target(p[1]==1?100:0);}
      if(arg>u32(settings+6))return 3;
      /* Preserve bounded manual bench commands until calibrated. */
      return start_motion(p[1],arg?arg:u32(settings+6),false,0);
    case 3:learn_stop=false;stop();return 0;
    case 4:
      if(direction || settling || motion.calibrated || motion.stage)return 4;
      board_zero();return 0;
    case 5:stop();pairing_until=now_ms()+90000;return 0;
    case 9:if(direction || settling)return 4;fault=0;return 0;
    case 10: /* Begin upper calibration, invalidate previous coordinate frame. */
      if(direction || settling)return 4;
      motion.calibrated=false;motion.referenced=false;motion.targeting=false;motion.stage=1;
      motion.lead_up=motion.lead_down=0;motion.travel=0;
      if(!save_position(false)){fault=4;return 6;}return 0;
    case 11: /* Upper limit is always zero. */
      if(direction || settling || motion.stage!=1)return 4;
      board_set_position(0);motion.stage=2;return 0;
    case 12: /* Commit both endpoints as one durable record. */
      if(direction || settling || motion.stage!=2)return 4;
      if(board_position()<4 || board_position()>10000000)return 3;
      motion.travel=board_position();motion.calibrated=true;motion.referenced=true;
      if(!save_position(true)) {motion.calibrated=false;motion.referenced=false;fault=4;return 6;}
      motion.stage=0;return 0;
    case 13:if(!motion.stage)return 4;stop();motion.stage=0;motion.referenced=false;return 0;
    case 14:case 15:
      if(!motion.stage)return 4;
      if(arg<50 || arg>1000)return 3;
      return start_motion(p[1]==14?1:2,arg,false,0);
    case 16:if(arg>100)return 3;return move_target((uint8_t)arg);
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
      uint8_t saved[10];
      if(nvm3_readData(nvm3_defaultHandle,SETTINGS_OBJECT,saved,10)==ECODE_NVM3_OK && valid_settings(saved,10))memcpy(settings,saved,10);
      else if(nvm3_readData(nvm3_defaultHandle,SETTINGS_OBJECT,saved,8)==ECODE_NVM3_OK && valid_settings(saved,8)) {
        memcpy(settings+1,saved+1,5); /* Preserve PWM/ramp; new travel timeout defaults to 120 s. */
      }
      uint8_t tuning[4];
      if(nvm3_readData(nvm3_defaultHandle,MOTION_SETTINGS_OBJECT,tuning,4)==ECODE_NVM3_OK &&
         tuning[0]>=40 && tuning[0]<=100 && tuning[1]>=40 && tuning[1]<=100 &&
         u16(tuning+2)>=4 && u16(tuning+2)<=2000) {
        motion.slow_up_pwm=tuning[0];motion.slow_down_pwm=tuning[1];motion.slow_counts=u16(tuning+2);
      }
      int32_t record[6],restored_position;
      if(nvm3_readData(nvm3_defaultHandle,POSITION_OBJECT,record,sizeof(record))==ECODE_NVM3_OK &&
         hd_motion_restore(&motion,record,&restored_position))board_set_position(restored_position);
      app_timer_start(&ticker,10,tick,NULL,true);
      bd_addr identity; uint8_t address_type; char name[14];
      if(sl_bt_system_get_identity_address(&identity,&address_type)==SL_STATUS_OK) {
        snprintf(name,sizeof(name),"HD Blind %02X%02X",identity.addr[1],identity.addr[0]);
        sl_bt_gatt_server_write_attribute_value(gattdb_device_name,0,13,(const uint8_t *)name);
      }
      const uint8_t firmware_version[]="0.3.0";
      sl_bt_gatt_server_write_attribute_value(gattdb_firmware_revision_string,0,5,firmware_version);
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
      stop();hd_ota_disconnect();conn=0xff;authenticated=false;subscribed=false;
      sl_bt_legacy_advertiser_start(adv,sl_bt_legacy_advertiser_connectable);break;
    case sl_bt_evt_gatt_server_characteristic_status_id:
      if(evt->data.evt_gatt_server_characteristic_status.characteristic==gattdb_hd_status)
        subscribed=(evt->data.evt_gatt_server_characteristic_status.client_config_flags&1)!=0;
      break;
    case sl_bt_evt_gatt_server_user_read_request_id: {
      sl_bt_evt_gatt_server_user_read_request_t *e=&evt->data.evt_gatt_server_user_read_request;
      uint8_t buf[32],error=0;size_t length=0;uint16_t sent;
      if(e->characteristic==gattdb_hd_status) {status(buf);length=20;}
      else if(e->characteristic==gattdb_hd_ota_control) {hd_ota_status(buf);length=16;}
      else if(e->characteristic==gattdb_hd_battery) {put16(buf,hd_battery_mv());put16(buf+2,hd_battery_raw());length=4;}
      else if(e->characteristic==gattdb_hd_calibration) {
        memset(buf,0,24);buf[0]=1;buf[1]=motion.stage;put16(buf+2,hd_motion_flags(&motion));
        put32(buf+4,motion.travel);put32(buf+8,motion.target);
        put16(buf+12,motion.lead_up);put16(buf+14,motion.lead_down);
        put16(buf+16,motion.slow_counts);put16(buf+18,HD_SETTLE_MS);
        buf[20]=motion.slow_up_pwm;buf[21]=motion.slow_down_pwm;length=24;
      }
      else if(e->characteristic==gattdb_hd_settings) {memcpy(buf,settings,10);length=10;}
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
      } else if(e->characteristic==gattdb_hd_ota_control) {
        if(!authenticated) error=0x08;
        else if(direction || settling || motion.stage)error=0x80;
        else error=hd_ota_control(e->value.data,e->value.len);
      } else if(e->characteristic==gattdb_hd_ota_data) {
        error=authenticated?hd_ota_data(e->value.data,e->value.len):0x08;
      } else if(e->characteristic==gattdb_hd_command) result=command(e->value.data,e->value.len);
      else if(e->characteristic==gattdb_hd_calibration) {
        const uint8_t *v=e->value.data;
        if(!authenticated)error=0x08;
        else if(direction || settling || motion.stage || hd_ota_busy())error=0x80;
        else if(e->value.len!=24 || v[0]!=1 || v[20]<40 || v[20]>100 ||
                v[21]<40 || v[21]>100 || u16(v+16)<4 || u16(v+16)>2000)error=0x0d;
        else {
          uint8_t tuning[4]={v[20],v[21],v[16],v[17]};
          if(nvm3_writeData(nvm3_defaultHandle,MOTION_SETTINGS_OBJECT,tuning,4)!=ECODE_NVM3_OK)error=0x80;
          else {motion.slow_up_pwm=v[20];motion.slow_down_pwm=v[21];motion.slow_counts=u16(v+16);}
        }
      }
      else if(e->characteristic==gattdb_hd_settings) {
        if(!authenticated) error=0x08;
        else if(direction || settling || motion.stage || hd_ota_busy()) error=0x80;
        else if(!valid_settings(e->value.data,e->value.len)) error=0x0d;
        else {
          uint8_t updated[10];memcpy(updated,settings,10);memcpy(updated+1,e->value.data+1,5);
          put32(updated+6,e->value.len==8?u16(e->value.data+6):u32(e->value.data+6));
          if(nvm3_writeData(nvm3_defaultHandle,SETTINGS_OBJECT,updated,10)!=ECODE_NVM3_OK)error=0x80;
          else memcpy(settings,updated,10);
        }
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
