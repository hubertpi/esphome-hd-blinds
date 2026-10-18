#pragma once
#include "esphome/core/component.h"
#include "esphome/components/esp32_ble/ble.h"
#include "esphome/components/button/button.h"
#include "esphome/components/esp32_ble_client/ble_client_base.h"
#include <array>
#include <string>

namespace esphome::hd_blinds {
class HDHub : public Component {
 public:
  void set_phone_mac(uint64_t mac);
  void set_ble(esp32_ble::ESP32BLE *ble) { ble_ = ble; }
  void set_phone_name(const std::string &name) { phone_name_ = name; }
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return 900.0f; }
  bool ready() const { return ready_ && !is_failed(); }
 protected:
  esp32_ble::ESP32BLE *ble_{nullptr};
  std::array<uint8_t, 6> phone_mac_{};
  std::string phone_name_;
  bool ready_{false};
};

class HDBlind : public esp32_ble_client::BLEClientBase {
 public:
  void set_hub(HDHub *hub) { hub_ = hub; }
  void set_bond(const std::array<uint8_t, 16> &ltk, const std::array<uint8_t, 8> &rand,
                uint16_t ediv, uint8_t auth_mode);
  void setup() override;
  void loop() override;
  void dump_config() override;
  void command(uint8_t value);
  bool gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                          esp_ble_gattc_cb_param_t *param) override;
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) override;
  void ble_before_disabled_event_handler() override;
 protected:
  void import_bond_();
  void send_pending_();
  void abort_(const char *reason);
  HDHub *hub_{nullptr};
  std::array<uint8_t, 16> ltk_{};
  std::array<uint8_t, 8> rand_{};
  uint16_t ediv_{0};
  uint8_t auth_mode_{9};
  uint16_t control_handle_{0};
  bool imported_{false};
  bool encryption_requested_{false};
  bool encrypted_{false};
  bool discovery_started_{false};
  bool write_pending_{false};
  int pending_{-1};
  uint32_t requested_at_{0};
  uint32_t imported_at_{0};
};

class HDCommandButton : public button::Button {
 public:
  void set_blind(HDBlind *blind) { blind_ = blind; }
  void set_command(uint8_t command) { command_ = command; }
 protected:
  void press_action() override { blind_->command(command_); }
  HDBlind *blind_{};
  uint8_t command_{};
};
}  // namespace esphome::hd_blinds
