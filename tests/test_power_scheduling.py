"""Exercise the actual app scheduler/command path with a deterministic SDK clock."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class PowerSchedulingTests(unittest.TestCase):
    def test_idle_deadlines_movement_stop_and_gpio_wake(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            w=Path(d)
            fake=r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#define SL_STATUS_OK 0
#define SL_POWER_MANAGER_EM1 1
#define ECODE_NVM3_OK 0
#define MBEDTLS_MD_SHA256 0
#define SL_BT_MSG_ID(x) (x)
#define sl_bt_advertiser_general_discoverable 0
#define sl_bt_legacy_advertiser_connectable 0
#define SL_BT_IN_PLACE_OTA_DFU_SECURITY_DENY 0
typedef int sl_bt_in_place_ota_dfu_security_sts_t;
typedef struct {uint8_t addr[6];} bd_addr;
typedef struct {int unused;} app_timer_t;
typedef struct {uint8_t connection;uint16_t characteristic,offset;struct{size_t len;uint8_t data[256];}value;} Request;
typedef Request sl_bt_evt_gatt_server_user_read_request_t;
typedef Request sl_bt_evt_gatt_server_user_write_request_t;
typedef struct {uint32_t header;struct {struct{uint8_t connection;}evt_connection_opened;struct{uint16_t characteristic,client_config_flags;}evt_gatt_server_characteristic_status;Request evt_gatt_server_user_read_request,evt_gatt_server_user_write_request;}data;} sl_bt_msg_t;
enum {sl_bt_evt_system_boot_id=1,sl_bt_evt_connection_opened_id,sl_bt_evt_connection_closed_id,sl_bt_evt_connection_set_parameters_failed_id,sl_bt_evt_system_external_signal_id,sl_bt_evt_gatt_server_characteristic_status_id,sl_bt_evt_gatt_server_user_read_request_id,sl_bt_evt_gatt_server_user_write_request_id};
enum {gattdb_hd_status=1,gattdb_hd_ota_control,gattdb_hd_battery,gattdb_hd_calibration,gattdb_hd_settings,gattdb_hd_auth,gattdb_hd_enroll,gattdb_hd_ota_data,gattdb_hd_command,gattdb_device_name,gattdb_firmware_revision_string};
static uint64_t clock_ms=100;
static uint32_t timeout_ms,starts,notifications,signals;
static bool periodic,button,ota_busy,drive;
static uint8_t charger=3;
static int em1;
static void (*gpio_callback)(void);
static uint32_t battery_delay=21600000;
static uint64_t sl_sleeptimer_get_tick_count64(void){return clock_ms;}
static int sl_sleeptimer_tick64_to_ms(uint64_t t,uint64_t *m){*m=t;return 0;}
static int app_timer_start(app_timer_t *t,uint32_t ms,void(*cb)(app_timer_t*,void*),void *d,bool p){timeout_ms=ms;periodic=p;starts++;return 0;}
static int app_timer_stop(app_timer_t *t){return 0;}
static void sl_bt_external_signal(unsigned x){signals|=x;}
static int sl_bt_connection_set_parameters(uint8_t c,int a,int b,int l,int t,int m,int n){return 0;}
#define sl_bt_connection_disable_slave_latency(...) 0
#define sl_bt_advertiser_set_timing(...) 0
#define sl_bt_legacy_advertiser_start(...) 0
#define sl_bt_legacy_advertiser_generate_data(...) 0
#define sl_bt_advertiser_create_set(...) 0
#define sl_bt_advertiser_stop(...) 0
#define sl_bt_connection_close(...) 0
#define sl_bt_gatt_server_write_attribute_value(...) 0
#define sl_bt_gatt_server_send_user_read_response(...) 0
#define sl_bt_gatt_server_send_user_write_response(...) 0
static int sl_bt_gatt_server_send_notification(uint8_t c,int ch,int len,uint8_t *d){notifications++;return 0;}
static int sl_bt_system_get_random_data(size_t a,size_t b,size_t *n,uint8_t *out){*n=b;memset(out,0,b);return 0;}
static int sl_bt_system_get_identity_address(bd_addr *a,uint8_t *t){memset(a,0,sizeof(*a));return 0;}
static int nvm3_defaultHandle;
#define nvm3_readData(...) 1
#define nvm3_writeData(...) 0
#define mbedtls_md_info_from_type(...) 0
#define mbedtls_md_hmac(...) 0
static void sl_power_manager_add_em_requirement(int n){em1++;}
static void sl_power_manager_remove_em_requirement(int n){em1--;}
'''
            (w/'fake_sdk.h').write_text(fake)
            for name in ['sl_bluetooth.h','gatt_db.h','app_timer.h','sl_sleeptimer.h','sl_power_manager.h','nvm3_default.h','sl_bt_in_place_ota_dfu.h','mbedtls/md.h']:
                p=w/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "fake_sdk.h"\n')
            (w/'test.c').write_text(r'''
#include <assert.h>
#include "app.c"
void board_init(void){}
void board_set_wake_callback(void(*cb)(void)){gpio_callback=cb;}
void board_stop(void){drive=false;}
void board_finish_stop(void){}
void board_drive(uint8_t d,uint8_t p){drive=true;}
void board_target(bool b,int32_t t){}
bool board_target_reached(void){return false;}
int32_t board_cut_position(void){return 0;}
int32_t board_position(void){return 0;}
uint32_t board_pulses(void){return 0;}
bool board_button(void){return button;}
uint8_t board_charger_raw(void){return charger;}
void board_leds(bool a,bool b){}
void board_zero(void){}
void board_set_position(int32_t p){}
void hd_ota_tick(void){}
bool hd_ota_busy(void){return ota_busy;}
void hd_ota_disconnect(void){}
void hd_ota_status(uint8_t p[16]){}
uint8_t hd_ota_control(const uint8_t *p,size_t n){return 0;}
uint8_t hd_ota_data(const uint8_t *p,size_t n){return 0;}
void hd_battery_tick(bool idle){}
uint32_t hd_battery_delay(void){return battery_delay;}
uint16_t hd_battery_mv(void){return 4000;}
uint16_t hd_battery_raw(void){return 2091;}
uint8_t hd_battery_percent(void){return 85;}
static void fire(void){clock_ms=timer_due;tick(&ticker,NULL);}
int main(void){
 app_init();assert(gpio_callback);
 conn=0;subscribed=true;authenticated=paired=true;link_fast=false;
 last_idle_notify=now_ms();notify();schedule();
 assert(timeout_ms==21600000 && !periodic && !em1);
 unsigned before=notifications;
 clock_ms+=1000;tick(NULL,NULL);assert(notifications==before);
 /* Raw counter changes do not imply a periodic idle notification. */
 assert(timeout_ms==21600000);
 /* Six-hour heartbeat is still available to HA. */
 fire();assert(notifications==before+1);assert(timeout_ms==21600000);
 /* Movement selects fast timing; incoming events cannot postpone it. */
 assert(start_motion(1,1000,false,0)==0);schedule();
 assert(drive && em1==1 && timeout_ms==10 && link_fast);
 uint32_t deadline=timer_due;clock_ms+=1;schedule();assert(timer_due==deadline);
 clock_ms+=250;tick(&ticker,NULL);assert(notifications>before+1);
 /* Stop acts in the command handler, before any timer fires. */
 uint8_t cmd[8]={1,3,1,0,0,0,0,0};assert(command(cmd,8)==0);
 assert(!drive && !direction && settling && em1==0);
 fire();if(settling)fire();assert(!settling);
 /* Physical button edge wakes and uses short polling only during the hold. */
 button=true;gpio_callback();assert(signals==1);tick(NULL,NULL);assert(timeout_ms<=50);
 clock_ms+=3000;tick(NULL,NULL);assert(pairing());
 button=false;tick(NULL,NULL);assert(timeout_ms<=500);
 /* Pairing expiry returns to sparse idle; charger changes still wake. */
 clock_ms=pairing_until;tick(&ticker,NULL);assert(!pairing());
 charger=2;gpio_callback();tick(NULL,NULL);assert(timeout_ms<=2400);
 charger=3;tick(NULL,NULL);
 /* OTA keeps an active service timer rather than sleeping for six hours. */
 ota_busy=true;tick(NULL,NULL);assert(timeout_ms<=10);
 return 0;
}
''')
            subprocess.run(['gcc','-std=c11','-I'+d,'-I'+str(root/'firmware'),str(w/'test.c'),'-o',str(w/'test')],check=True)
            subprocess.run([str(w/'test')],check=True)
