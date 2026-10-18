"""Install staged GBL firmware over local BLE, including ESPHome proxies."""
import asyncio
import base64
import gzip
import hashlib
import logging
import re
from datetime import timedelta
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature, UpdateDeviceClass
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError
from .entity import BlindEntity

_LOGGER=logging.getLogger(__name__)

MANIFEST='https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/main/firmware/releases/ota-latest.json'

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindUpdate(entry.runtime_data)])

class BlindUpdate(BlindEntity, UpdateEntity):
    _attr_device_class=UpdateDeviceClass.FIRMWARE
    _attr_supported_features=UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_latest_version=None
    _attr_release_summary=None
    _attr_release_url='https://github.com/hubertpi/esphome-hd-blinds/blob/main/CUSTOM_FIRMWARE.md'
    def __init__(self, coordinator):
        super().__init__(coordinator, 'firmware', 'Firmware')
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(
            self.hass,self._async_check_release,timedelta(hours=6)))
        task=self.hass.async_create_task(self._async_check_release())
        self.async_on_remove(task.cancel)

    async def _fetch_manifest(self):
        session=async_get_clientsession(self.hass)
        async with asyncio.timeout(20):
            async with session.get(MANIFEST) as response:
                response.raise_for_status()
                manifest=await response.json(content_type=None)
        if (not isinstance(manifest.get('version'),str) or
                not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',manifest['version']) or
                not isinstance(manifest.get('bytes'),int) or
                not 32<=manifest['bytes']<=225280 or manifest['bytes']%4 or
                not re.fullmatch(r'[0-9a-fA-F]{64}',str(manifest.get('sha256',''))) or
                not str(manifest.get('url','')).startswith('https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/')):
            raise ValueError('Invalid firmware release manifest')
        self._attr_latest_version=manifest['version']
        self._attr_release_summary=manifest.get('summary','Firmware update for HD Blinds.')
        return manifest

    async def _async_check_release(self, now=None):
        try:
            await self._fetch_manifest()
        except Exception:
            # Keep the last successful release info; a GitHub outage must not
            # make local blind control unavailable.
            _LOGGER.debug('Unable to check HD Blind firmware release',exc_info=True)
        self.async_write_ha_state()

    async def async_update(self):
        # homeassistant.update_entity can explicitly check without waiting 6 h.
        await self._async_check_release()

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
            manifest=await self._fetch_manifest()
            if version is not None and version!=manifest['version']:
                raise ValueError('Requested firmware version is no longer the published release')
            session=async_get_clientsession(self.hass)
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
