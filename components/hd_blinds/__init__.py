"""Experimental encrypted HDC blind control for ESPHome 2026.10.0b4."""
import re
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import button, esp32, esp32_ble, esp32_ble_client, esp32_ble_tracker
from esphome.const import CONF_ID, CONF_MAC_ADDRESS

DEPENDENCIES = ["esp32", "esp32_ble_tracker"]
AUTO_LOAD = ["esp32_ble_client", "button"]
ns = cg.esphome_ns.namespace("hd_blinds")
Hub = ns.class_("HDHub", cg.Component)
Blind = ns.class_("HDBlind", esp32_ble_client.BLEClientBase)
CommandButton = ns.class_("HDCommandButton", button.Button)

def hex_bytes(length):
    def validate(value):
        value = cv.string_strict(value).replace(":", "").replace(" ", "")
        if not re.fullmatch(r"[0-9a-fA-F]{%d}" % (length * 2), value):
            raise cv.Invalid(f"Expected exactly {length} bytes of hexadecimal")
        return [int(value[i:i + 2], 16) for i in range(0, len(value), 2)]
    return validate

BLIND_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(Blind),
    cv.Required(CONF_MAC_ADDRESS): cv.mac_address,
    cv.Required("ltk"): hex_bytes(16),
    cv.Optional("rand", default="0000000000000000"): hex_bytes(8),
    cv.Optional("ediv", default=0): cv.int_range(min=0, max=65535),
    cv.Optional("auth_mode", default=9): cv.one_of(1, 5, 9, 13, int=True),
    cv.Required("up"): button.button_schema(CommandButton),
    cv.Required("down"): button.button_schema(CommandButton),
    cv.Required("stop"): button.button_schema(CommandButton),
}).extend(cv.COMPONENT_SCHEMA).extend(esp32_ble_tracker.ESP_BLE_DEVICE_SCHEMA)
CONFIG_SCHEMA = cv.All(cv.Schema({
    cv.GenerateID(): cv.declare_id(Hub),
    cv.Required("phone_mac"): cv.mac_address,
    cv.Required("phone_name"): cv.All(cv.string_strict, cv.Length(min=1, max=29)),
    cv.Required("blinds"): cv.All(cv.ensure_list(BLIND_SCHEMA), cv.Length(min=1, max=3)),
}).extend(cv.COMPONENT_SCHEMA), esp32.only_on_variant(supported=[esp32.VARIANT_ESP32]))

async def to_code(config):
    esp32_ble.register_bt_logger(esp32_ble.BTLoggers.GATT, esp32_ble.BTLoggers.SMP)
    cg.add_define("USE_ESP32_BLE_UUID")
    hub = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(hub, config)
    cg.add(hub.set_phone_mac(config["phone_mac"].as_hex))
    cg.add(hub.set_phone_name(config["phone_name"]))
    for conf in config["blinds"]:
        var = cg.new_Pvariable(conf[CONF_ID])
        await cg.register_component(var, conf)
        await esp32_ble_tracker.register_client(var, conf)
        cg.add(var.set_hub(hub))
        cg.add(var.set_address(conf[CONF_MAC_ADDRESS].as_hex))
        cg.add(var.set_auto_connect(False))
        cg.add(var.set_bond(conf["ltk"], conf["rand"], conf["ediv"], conf["auth_mode"]))
        for key, command in (("up", 1), ("down", 0), ("stop", 4)):
            b = await button.new_button(conf[key])
            cg.add(b.set_blind(var))
            cg.add(b.set_command(command))
