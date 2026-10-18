"""Provision a blind during its physical pairing window."""
import probatio
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow
from .const import CONF_PAIRING_KEY, DOMAIN
from . import protocol as p
from .calibration_flow import BlindCalibrationFlow
from homeassistant.core import callback

class HDBlindsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BlindCalibrationFlow()

    def __init__(self):
        self.address = None

    async def async_step_bluetooth(self, discovery_info):
        self.address = discovery_info.address
        await self.async_set_unique_id(self.address)
        self._abort_if_unique_id_configured()
        self.context['title_placeholders'] = {'name': f'HD Blind {self.address}'}
        return await self.async_step_pair()

    async def async_step_user(self, user_input=None):
        if user_input:
            self.address = user_input['address']
            await self.async_set_unique_id(self.address)
            self._abort_if_unique_id_configured()
            return await self.async_step_pair()
        choices = {s.address: f'{s.name} ({s.address})'
                   for s in bluetooth.async_discovered_service_info(self.hass, connectable=True)
                   if p.SERVICE in [u.lower() for u in s.service_uuids]}
        if not choices:
            return self.async_abort(reason='no_devices_found')
        return self.async_show_form(step_id='user', data_schema=probatio.Schema({
            probatio.Required('address'): probatio.In(choices)}))

    async def async_step_pair(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = None
            try:
                device = bluetooth.async_ble_device_from_address(self.hass, self.address, True)
                if device is None:
                    raise ConnectionError('Device not available')
                client = await establish_connection(BleakClientWithServiceCache, device, 'HD Blind setup')
                key = bytes(await client.read_gatt_char(p.ENROLL))
                nonce = bytes(await client.read_gatt_char(p.AUTH))
                await client.write_gatt_char(p.AUTH, p.proof(key, nonce), response=True)
                status = p.Status.decode(await client.read_gatt_char(p.STATUS))
                if not status.flags & 4:
                    raise PermissionError('Authentication failed')
                return self.async_create_entry(title=p.device_name(self.address),
                    data={'address': self.address, CONF_PAIRING_KEY: key.hex()})
            except Exception:
                errors['base'] = 'cannot_pair'
            finally:
                if client:
                    await client.disconnect()
        return self.async_show_form(step_id='pair', data_schema=probatio.Schema({}), errors=errors)
