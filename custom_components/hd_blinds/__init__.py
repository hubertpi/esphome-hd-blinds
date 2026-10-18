"""HD Blinds replacement-firmware integration."""
from datetime import timedelta
from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import BlindClient
from .const import CONF_PAIRING_KEY, DOMAIN

PLATFORMS = [Platform.COVER, Platform.NUMBER, Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR, Platform.UPDATE]

class BlindCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        import logging
        super().__init__(hass, logging.getLogger(__name__), name=entry.title,
                         update_interval=timedelta(hours=6))
        self.entry = entry
        self.blind = BlindClient(
            lambda: bluetooth.async_ble_device_from_address(hass, entry.data['address'], True),
            bytes.fromhex(entry.data[CONF_PAIRING_KEY]), self.received)

    def received(self, status):
        if status is None:
            self.update_interval=timedelta(seconds=30)
            # Reconnect promptly; do not wait for the six-hour diagnostic poll.
            self.hass.async_create_task(self.async_request_refresh())
            self.async_set_update_error(UpdateFailed('Bluetooth disconnected'))
        else:
            self.async_set_updated_data(status)

    def sync_firmware_version(self):
        registry=dr.async_get(self.hass)
        device=registry.async_get_device(identifiers={(DOMAIN,self.entry.data['address'])})
        if device and self.blind.firmware_version and device.sw_version!=self.blind.firmware_version:
            registry.async_update_device(device.id,sw_version=self.blind.firmware_version)

    async def _async_update_data(self):
        try:
            if self.blind.updating:
                return self.blind.status
            status=await self.blind.refresh()
            self.update_interval=timedelta(hours=6)
            self.sync_firmware_version()
            return status
        except PermissionError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            self.update_interval=timedelta(seconds=30)
            raise UpdateFailed(str(err)) from err

async def async_setup_entry(hass, entry):
    coordinator = BlindCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.blind.disconnect()
        return True
    return False
