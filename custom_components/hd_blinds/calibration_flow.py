"""Interactive upper-then-lower endpoint calibration in the device options."""
import asyncio
import logging
import probatio
from homeassistant.config_entries import OptionsFlow
from homeassistant.helpers import selector
from . import protocol as p

_LOGGER=logging.getLogger(__name__)

class BlindCalibrationFlow(OptionsFlow):
    def __init__(self):
        self._stage='upper'
        self._pulse=250
        self._error=''

    @property
    def coordinator(self):
        return self.config_entry.runtime_data

    async def _refresh(self):
        status=await self.coordinator.blind.refresh()
        self.coordinator.async_set_updated_data(status)

    async def _send(self, opcode, arg=0):
        await self.coordinator.blind.send(opcode,arg)
        await self._refresh()

    async def async_step_init(self,user_input=None):
        if not self.coordinator.data.flags & p.CAL_CAPABLE:
            return self.async_abort(reason='firmware_required')
        if user_input is not None:
            try:
                await self._send(p.Opcode.CALIBRATE_BEGIN)
                self._stage='upper'
                return await self.async_step_upper()
            except Exception as err:
                _LOGGER.debug('Could not begin calibration',exc_info=True)
                return self.async_show_form(step_id='init',data_schema=probatio.Schema({}),
                    errors={'base':'command_failed'},description_placeholders={'error':str(err)})
        return self.async_show_form(step_id='init',data_schema=probatio.Schema({}),
            description_placeholders={'error':''})

    async def _menu(self):
        await self._refresh()
        return self.async_show_menu(step_id=self._stage,
            menu_options=['pulse_up','pulse_down','pulse_length',
                          'set_upper' if self._stage=='upper' else 'set_lower','stop','cancel'],
            description_placeholders={'position':str(self.coordinator.data.position),
                                      'pulse':str(self._pulse),'error':self._error})

    async def async_step_upper(self,user_input=None):
        self._stage='upper'
        return await self._menu()

    async def async_step_lower(self,user_input=None):
        self._stage='lower'
        return await self._menu()

    async def _pulse_motor(self,opcode):
        try:
            await self._send(opcode,self._pulse)
            # Firmware bounds the jog; wait for coast and durable-position save.
            await asyncio.sleep(self._pulse/1000+0.5)
            self._error=''
        except Exception as err:
            self._error=str(err)
        return await self._menu()

    async def async_step_pulse_up(self,user_input=None):
        return await self._pulse_motor(p.Opcode.JOG_UP)

    async def async_step_pulse_down(self,user_input=None):
        return await self._pulse_motor(p.Opcode.JOG_DOWN)

    async def async_step_pulse_length(self,user_input=None):
        if user_input is not None:
            self._pulse=int(user_input['milliseconds'])
            return await self._menu()
        return self.async_show_form(step_id='pulse_length',data_schema=probatio.Schema({
            probatio.Required('milliseconds',default=self._pulse):selector.NumberSelector(
                selector.NumberSelectorConfig(min=50,max=1000,step=50,mode=selector.NumberSelectorMode.BOX,
                                              unit_of_measurement='ms'))}))

    async def async_step_set_upper(self,user_input=None):
        try:
            await self._send(p.Opcode.CALIBRATE_UPPER)
            self._stage='lower';self._error=''
        except Exception as err:self._error=str(err)
        return await self._menu()

    async def async_step_set_lower(self,user_input=None):
        try:
            await self._send(p.Opcode.CALIBRATE_LOWER)
            return self.async_create_entry(title='',data={})
        except Exception as err:
            self._error=str(err)
            return await self._menu()

    async def async_step_stop(self,user_input=None):
        try:
            await self._send(p.Opcode.STOP)
            await asyncio.sleep(0.5)
            self._error=''
        except Exception as err:self._error=str(err)
        return await self._menu()

    async def async_step_cancel(self,user_input=None):
        try:
            await self._send(p.Opcode.CALIBRATE_CANCEL)
        except Exception:
            _LOGGER.debug('Could not cancel firmware calibration',exc_info=True)
            return self.async_abort(reason='cancel_failed')
        return self.async_abort(reason='calibration_cancelled')
