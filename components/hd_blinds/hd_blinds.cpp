#include "hd_blinds.h"
#include "esphome/components/esp32_ble/ble.h"
#include "esphome/core/log.h"
#include <esp_mac.h>
#include <esp_idf_version.h>
#include <cstring>
#include <cstddef>

// Bluedroid has a public bond export API but no public bond import API.
// These exported internal BTA functions copy the key into the BT task queue.
// ABI checked against ESP-IDF 5.5's bta_api.h and btm_api.h. No flash bond
// database is edited. Refuse other IDF minors rather than silently guessing.
#if ESP_IDF_VERSION_MAJOR != 5 || ESP_IDF_VERSION_MINOR != 5
#error "hd_blinds bond import supports ESP-IDF 5.5.x only; check the Bluedroid ABI before porting"
#endif
struct HDBondEncryptionKey {
  uint8_t ltk[16];
  uint8_t rand[8];
  uint16_t ediv;
  uint8_t sec_level;
  uint8_t key_size;
};
union HDBondKey {
  HDBondEncryptionKey encryption;
  uint32_t alignment[7];
};
static_assert(sizeof(HDBondKey) == 28);
static_assert(offsetof(HDBondEncryptionKey, ediv) == 24);
extern "C" {
void BTA_DmAddBleDevice(uint8_t *bd_addr, uint8_t addr_type, int auth_mode, uint8_t dev_type);
void BTA_DmAddBleKey(uint8_t *bd_addr, HDBondKey *key, uint8_t key_type);
}

namespace esphome::hd_blinds {
static const char *const TAG = "hd_blinds";
namespace espbt = esp32_ble_tracker;

void HDHub::set_phone_mac(uint64_t mac) {
  for (int i = 5; i >= 0; --i) { phone_mac_[i] = mac & 0xFF; mac >>= 8; }
}
void HDHub::setup() {
  // Runs before ESP32BLE::setup(), which initializes global_ble. Use the
  // already-constructed instance injected by codegen, never that global.
  if (ble_ == nullptr) {
    ESP_LOGE(TAG, "Bluetooth component was not injected");
    mark_failed();
    return;
  }
  if ((phone_mac_[0] & 1) != 0) {
    ESP_LOGE(TAG, "Phone identity must be a unicast public MAC");
    mark_failed();
    return;
  }
  auto err = esp_iface_mac_addr_set(phone_mac_.data(), ESP_MAC_BT);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Cannot set Bluetooth identity: %s", esp_err_to_name(err));
    mark_failed();
    return;
  }
  ble_->set_name(phone_name_.c_str());
  ready_ = true;
}
void HDHub::dump_config() {
  ESP_LOGCONFIG(TAG, "HDC phone identity: %s; bond material is never logged", ready() ? "configured" : "FAILED");
}
void HDBlind::set_bond(const std::array<uint8_t, 16> &ltk, const std::array<uint8_t, 8> &rand,
                       uint16_t ediv, uint8_t auth_mode) {
  ltk_ = ltk; rand_ = rand; ediv_ = ediv; auth_mode_ = auth_mode;
}
void HDBlind::setup() {
  BLEClientBase::setup();
  set_auto_connect(false);
}
void HDBlind::import_bond_() {
  HDBondKey key{};
  std::memcpy(key.encryption.ltk, ltk_.data(), 16);
  std::memcpy(key.encryption.rand, rand_.data(), 8);
  key.encryption.ediv = ediv_;
  // Bluedroid SMP security levels: 1=unauthenticated encryption; 4=MITM.
  key.encryption.sec_level = (auth_mode_ & 4) ? 4 : 1;
  key.encryption.key_size = 16;
  BTA_DmAddBleDevice(remote_bda_, BLE_ADDR_TYPE_PUBLIC, auth_mode_, 2 /* BLE */);
  BTA_DmAddBleKey(remote_bda_, &key, 1 /* BTM_LE_KEY_PENC */);
  imported_ = true;
  imported_at_ = millis();
  ESP_LOGI(TAG, "[%s] Imported captured bond into RAM", address_str());
}
void HDBlind::loop() {
  if (hub_ == nullptr || !hub_->ready()) return;
  if (esp32_ble::global_ble->is_active() && !imported_) import_bond_();
  BLEClientBase::loop();
  if (pending_ >= 0) enable_loop();
  if (pending_ >= 0 && millis() - requested_at_ > 25000) {
    abort_("Command timed out; it was not retried");
    return;
  }
  if (pending_ >= 0 && imported_ && millis() - imported_at_ >= 500 && !write_pending_) {
    if (encrypted_ && connected()) send_pending_();
    else set_auto_connect(true);
  }
}
void HDBlind::dump_config() {
  BLEClientBase::dump_config();
  ESP_LOGCONFIG(TAG, "  HDC encrypted command client; Stop/Favorite 0x04 is experimental");
}
void HDBlind::command(uint8_t value) {
  if (value != 0 && value != 1 && value != 4) return;
  if (hub_ == nullptr || !hub_->ready()) {
    ESP_LOGE(TAG, "Bluetooth identity unavailable; refusing command");
    return;
  }
  if (write_pending_) {
    ESP_LOGW(TAG, "[%s] A write is still awaiting acknowledgment; try again", address_str());
    return;
  }
  pending_ = value;
  requested_at_ = millis();
  enable_loop();
  ESP_LOGI(TAG, "[%s] Queued command 0x%02X", address_str(), value);
}
void HDBlind::abort_(const char *reason) {
  ESP_LOGW(TAG, "[%s] %s", address_str(), reason);
  pending_ = -1;
  write_pending_ = false;
  set_auto_connect(false);
  if (state() != espbt::ClientState::IDLE && state() != espbt::ClientState::INIT) disconnect();
}
void HDBlind::send_pending_() {
  if (pending_ < 0 || !encrypted_ || !connected() || write_pending_ || control_handle_ == 0) return;
  uint8_t value = static_cast<uint8_t>(pending_);
  auto err = esp_ble_gattc_write_char(gattc_if_, conn_id_, control_handle_, 1, &value,
                                     ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);
  if (err != ESP_OK) { abort_("Could not submit command write"); return; }
  write_pending_ = true;
}
bool HDBlind::gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                                 esp_ble_gattc_cb_param_t *param) {
  if (event != ESP_GATTC_REG_EVT && gattc_if != ESP_GATT_IF_NONE && gattc_if != gattc_if_) return false;
  // Suppress the base class's immediate discovery: this blind requires
  // encryption first and otherwise disconnects before discovery completes.
  if (event == ESP_GATTC_OPEN_EVT && check_addr(param->open.remote_bda) &&
      (param->open.status == ESP_GATT_OK || param->open.status == ESP_GATT_ALREADY_OPEN)) {
    conn_id_ = param->open.conn_id;
    service_count_ = 0;
    set_state(espbt::ClientState::CONNECTED);
    ESP_LOGI(TAG, "[%s] Link open; waiting for encryption before discovery", address_str());
    if (!encryption_requested_) {
      encryption_requested_ = true;
      if (pair() != ESP_OK) abort_("Could not request bond encryption");
    }
    return true;
  }
  bool ours = BLEClientBase::gattc_event_handler(event, gattc_if, param);
  if (!ours) return false;
  if (event == ESP_GATTC_CONNECT_EVT && check_addr(param->connect.remote_bda)) {
    encrypted_ = false;
    discovery_started_ = false;
    encryption_requested_ = true;
    if (pair() != ESP_OK) abort_("Could not request bond encryption");
  } else if (event == ESP_GATTC_SEARCH_CMPL_EVT && conn_id_ == param->search_cmpl.conn_id) {
    if (param->search_cmpl.status != ESP_GATT_OK || !encrypted_) { abort_("Encrypted discovery failed"); return true; }
    auto *chr = get_characteristic(espbt::ESPBTUUID::from_raw("a2be20e1-cecf-4cfb-ac97-d656cb5b0e24"),
                                  espbt::ESPBTUUID::from_raw("9d85a52d-4596-4076-b3ce-fd2fedf93c8b"));
    if (chr == nullptr) { abort_("Expected HDC command UUID is absent"); return true; }
    control_handle_ = chr->handle;
    ESP_LOGI(TAG, "[%s] Encrypted and ready; control handle 0x%04X", address_str(), control_handle_);
    send_pending_();
  } else if (event == ESP_GATTC_WRITE_CHAR_EVT && conn_id_ == param->write.conn_id &&
             param->write.handle == control_handle_) {
    if (param->write.status == ESP_GATT_OK) ESP_LOGI(TAG, "[%s] Command acknowledged", address_str());
    else ESP_LOGW(TAG, "[%s] Command rejected: GATT status %d", address_str(), param->write.status);
    pending_ = -1;
    write_pending_ = false;
    set_auto_connect(false);
    // Keep the encrypted connection briefly for a subsequent Stop command.
    // The motor's own idle timeout may close it sooner.
    set_timeout("idle_disconnect", 20000, [this]() {
      if (pending_ < 0 && !write_pending_) disconnect();
    });
  } else if ((event == ESP_GATTC_DISCONNECT_EVT && check_addr(param->disconnect.remote_bda)) ||
             (event == ESP_GATTC_CLOSE_EVT && state() == espbt::ClientState::IDLE)) {
    encrypted_ = false;
    encryption_requested_ = false;
    discovery_started_ = false;
    control_handle_ = 0;
    pending_ = -1;
    write_pending_ = false;
    set_auto_connect(false);
    cancel_timeout("idle_disconnect");
  }
  return true;
}
void HDBlind::gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  BLEClientBase::gap_event_handler(event, param);
  if (event == ESP_GAP_BLE_AUTH_CMPL_EVT && check_addr(param->ble_security.auth_cmpl.bd_addr)) {
    if (!param->ble_security.auth_cmpl.success) {
      abort_("Bond encryption failed; check captured key and phone identity");
      return;
    }
    encrypted_ = true;
    if (!discovery_started_) {
      discovery_started_ = true;
      if (esp_ble_gattc_search_service(gattc_if_, conn_id_, nullptr) != ESP_OK)
        abort_("Could not start encrypted discovery");
    }
  }
}
void HDBlind::ble_before_disabled_event_handler() {
  BLEClientBase::ble_before_disabled_event_handler();
  imported_ = encrypted_ = encryption_requested_ = discovery_started_ = write_pending_ = false;
  pending_ = -1;
  control_handle_ = 0;
  set_auto_connect(false);
}
}  // namespace esphome::hd_blinds
