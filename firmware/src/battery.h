#pragma once
#include <stdint.h>
#include <stdbool.h>
void hd_battery_tick(bool idle);
uint8_t hd_battery_percent(void);
uint16_t hd_battery_mv(void);
uint16_t hd_battery_raw(void);
