#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
void hd_ota_tick(void);
bool hd_ota_busy(void);
void hd_ota_disconnect(void);
void hd_ota_status(uint8_t out[16]);
uint8_t hd_ota_control(const uint8_t *data,size_t length);
uint8_t hd_ota_data(const uint8_t *data,size_t length);
