"""HD Blinds replacement-firmware integration."""
from datetime import timedelta
from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import BlindClient
from .const import CONF_PAIRING_KEY, DOMAIN

PLATFORMS = [Platform.COVER, Platform.NUMBER, Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]

class BlindCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        import logging
        super().__init__(hass, logging.getLogger(__name__), name=entry.title,
                         update_interval=timedelta(seconds=30))
        self.entry = entry
        self.blind = BlindClient(
            lambda: bluetooth.async_ble_device_from_address(hass, entry.data['address'], True),
            bytes.fromhex(entry.data[CONF_PAIRING_KEY]), self.received)

    def received(self, status):
        if status is None:
            self.async_set_update_error(UpdateFailed('Bluetooth disconnected'))
        else:
            self.async_set_updated_data(status)

    async def _async_update_data(self):
        try:
            return await self.blind.refresh()
        except PermissionError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
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
