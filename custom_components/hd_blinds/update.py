"""Install staged GBL firmware over local BLE, including ESPHome proxies."""
import asyncio
import base64
import gzip
import hashlib
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature, UpdateDeviceClass
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError
from .entity import BlindEntity

MANIFEST='https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/main/firmware/releases/ota-latest.json'

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindUpdate(entry.runtime_data)])

class BlindUpdate(BlindEntity, UpdateEntity):
    _attr_device_class=UpdateDeviceClass.FIRMWARE
    _attr_supported_features=UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_latest_version='0.3.0'
    _attr_release_summary='Guided upper/lower calibration, HA cover positioning, saved encoder position, and tunable endpoint slowdown.'
    _attr_release_url='https://github.com/hubertpi/esphome-hd-blinds/blob/main/CUSTOM_FIRMWARE.md'
    def __init__(self, coordinator):
        super().__init__(coordinator, 'firmware', 'Firmware')
    @property
    def installed_version(self):
        return self.coordinator.blind.firmware_version
    @property
    def available(self):
        return super().available and bool(self.coordinator.data.flags & 256)
    async def async_install(self, version=None, backup=False, **kwargs):
        self._attr_in_progress=True
        self._attr_update_percentage=0
        self.async_write_ha_state()
        def progress(value):
            self._attr_update_percentage=value
            self.async_write_ha_state()
        try:
            session=async_get_clientsession(self.hass)
            async with session.get(MANIFEST) as response:
                response.raise_for_status()
                manifest=await response.json(content_type=None)
            if manifest['version']!=self.latest_version:
                raise ValueError('Update manifest version mismatch')
            async with session.get(manifest['url']) as response:
                response.raise_for_status()
                image=await response.read()
            if manifest.get("encoding")=="gzip-base64":
                image=gzip.decompress(base64.decodebytes(image))
            if len(image)!=manifest['bytes'] or hashlib.sha256(image).hexdigest()!=manifest['sha256']:
                raise ValueError('Firmware download checksum mismatch')
            await self.coordinator.blind.install_firmware(image, progress)
            await asyncio.sleep(5)
            for _ in range(60):
                try:
                    await self.coordinator.blind.refresh()
                    if self.coordinator.blind.firmware_version==manifest['version']:
                        self.coordinator.sync_firmware_version()
                        progress(100)
                        self.coordinator.async_set_updated_data(self.coordinator.blind.status)
                        return
                except Exception:
                    pass
                await asyncio.sleep(2)
            raise TimeoutError('Update sent, but the new version has not reconnected')
        except Exception as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            self._attr_in_progress=False
            self._attr_update_percentage=None
            self.async_write_ha_state()
