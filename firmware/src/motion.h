/* SPDX-License-Identifier: MIT. Encoder position control, independent of the SDK. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#define HD_SETTLE_MS 300u
#define HD_SLOW_COUNTS 32u
#define HD_CAL_CAPABLE 512u
#define HD_CALIBRATED 1024u
#define HD_CALIBRATING 2048u
#define HD_POSITION_VALID 4096u
#define HD_UPPER_SET 8192u

typedef struct {
  int32_t travel, target, last_position;
  uint32_t sampled_at;
  uint16_t velocity, lead_up, lead_down, slow_counts;
  uint8_t slow_up_pwm, slow_down_pwm;
  uint8_t stage; /* 0 normal, 1 upper adjustment, 2 lower adjustment */
  bool calibrated, referenced, targeting;
} hd_motion_t;
static inline uint8_t hd_motion_percent(const hd_motion_t *m,int32_t pos) {
  if(!m->calibrated || !m->referenced || m->travel<=0) return 255;
  if(pos<=0)return 100;
  if(pos>=m->travel)return 0;
  return (uint8_t)(100-((int64_t)pos*100+m->travel/2)/m->travel);
}
static inline uint16_t hd_motion_flags(const hd_motion_t *m) {
  return HD_CAL_CAPABLE|(m->calibrated?HD_CALIBRATED:0)|
    (m->referenced?HD_POSITION_VALID:0)|(m->stage?HD_CALIBRATING:0)|
    (m->stage==2?HD_UPPER_SET:0);
}
static inline int32_t hd_motion_target(const hd_motion_t *m,uint8_t open_percent) {
  return (int32_t)(((int64_t)m->travel*(100-open_percent)+50)/100);
}
static inline void hd_motion_sample(hd_motion_t *m,int32_t pos,uint32_t now) {
  uint32_t elapsed=now-m->sampled_at;
  if(elapsed>=50) {
    int64_t delta=(int64_t)pos-m->last_position;if(delta<0)delta=-delta;
    uint32_t speed=(uint32_t)(delta*1000/elapsed);
    m->velocity=(uint16_t)(speed>65535?65535:speed);
    m->last_position=pos;m->sampled_at=now;
  }
}
/* Return remaining counts in the commanded direction; negative means crossed. */
static inline int32_t hd_motion_remaining(const hd_motion_t *m,int32_t pos,uint8_t dir) {
  return dir==1?pos-m->target:m->target-pos;
}
static inline uint16_t hd_motion_lead(const hd_motion_t *m,uint8_t dir) {
  return dir==1?m->lead_up:m->lead_down;
}
static inline bool hd_motion_should_stop(const hd_motion_t *m,int32_t pos,uint8_t dir) {
  return m->targeting && hd_motion_remaining(m,pos,dir)<=(int32_t)hd_motion_lead(m,dir);
}
static inline uint8_t hd_motion_duty(const hd_motion_t *m,int32_t pos,uint8_t dir,uint8_t cruise) {
  if(!m->targeting)return cruise;
  int32_t remaining=hd_motion_remaining(m,pos,dir);
  uint32_t window=(m->slow_counts?m->slow_counts:HD_SLOW_COUNTS)+(uint32_t)m->velocity/5; /* 200 ms lookahead */
  uint8_t configured=dir==1?m->slow_up_pwm:m->slow_down_pwm;
  if(!configured)configured=dir==1?60:55;
  uint8_t floor=cruise<configured?cruise:configured;
  if(remaining<=0)return floor;
  if((uint32_t)remaining>=window)return cruise;
  return floor+(uint32_t)(cruise-floor)*remaining/window;
}
/* Learn observed coast distance; never auto-reverse or hide physical overshoot. */
static inline void hd_motion_learn(hd_motion_t *m,uint8_t dir,int32_t cut,int32_t settled) {
  int64_t coast=dir==1?(int64_t)cut-settled:(int64_t)settled-cut;
  if(coast<0)coast=0;
  if(coast>16)coast=16;
  uint16_t *lead=dir==1?&m->lead_up:&m->lead_down;
  *lead=(uint16_t)((*lead+coast+1)/2);
}
/* Save once before motion (valid=false), then once after coast settles. */
static inline void hd_motion_record(const hd_motion_t *m,int32_t pos,bool valid,int32_t record[6]) {
  record[0]=1;record[1]=m->calibrated?1:0;record[2]=m->travel;record[3]=pos;
  record[4]=valid?1:0;record[5]=(int32_t)(m->lead_up|((uint32_t)m->lead_down<<16));
}
static inline bool hd_motion_restore(hd_motion_t *m,const int32_t record[6],int32_t *pos) {
  if(record[0]!=1 || record[2]<4 || record[2]>10000000)return false;
  m->travel=record[2];m->calibrated=(record[1]&1)!=0;
  m->referenced=m->calibrated && record[4]==1;
  m->lead_up=(uint16_t)record[5];m->lead_down=(uint16_t)((uint32_t)record[5]>>16);
  if(m->lead_up>16)m->lead_up=0;
  if(m->lead_down>16)m->lead_down=0;
  *pos=record[3];return true;
}
