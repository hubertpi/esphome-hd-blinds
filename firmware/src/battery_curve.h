#pragma once
#include <stdint.h>
/* Approximate resting single-cell Li-ion curve; 255 means unavailable. */
static inline uint8_t hd_battery_estimate(uint16_t millivolts) {
 static const uint16_t volts[]={2800,3300,3500,3600,3700,3750,3800,3900,4000,4100,4200};
 static const uint8_t pct[]={0,5,10,20,40,50,60,75,85,95,100};
 if(millivolts==0xffff)return 255;
 if(millivolts<=volts[0])return 0;
 for(unsigned i=1;i<sizeof(pct);i++)if(millivolts<volts[i])
  return pct[i-1]+(millivolts-volts[i-1])*(pct[i]-pct[i-1])/(volts[i]-volts[i-1]);
 return 100;
}
