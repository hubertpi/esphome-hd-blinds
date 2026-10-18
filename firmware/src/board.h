#pragma once
#include <stdint.h>
#include <stdbool.h>
void board_init(void);
void board_drive(uint8_t direction, uint8_t duty);
void board_stop(void);
void board_leds(bool a, bool b);
bool board_button(void);
uint8_t board_charger_raw(void);
int32_t board_position(void);
uint32_t board_pulses(void);
void board_zero(void);

void board_finish_stop(void);
void board_set_position(int32_t value);
void board_target(bool enabled,int32_t target);
bool board_target_reached(void);

int32_t board_cut_position(void);

/* IRQ-safe callback; application posts a Bluetooth external signal. */
void board_set_wake_callback(void (*callback)(void));
