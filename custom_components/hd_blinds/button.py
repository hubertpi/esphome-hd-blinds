from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .entity import BlindEntity
from .protocol import Opcode

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindButton(entry.runtime_data, key, name, opcode) for key, name, opcode in
        [('zero', 'Zero position counter', Opcode.ZERO),
         ('pair', 'Open pairing mode', Opcode.PAIR),
         ('clear_fault', 'Clear motor fault', Opcode.CLEAR_FAULT)]])

class BlindButton(BlindEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    def __init__(self, coordinator, key, name, opcode):
        super().__init__(coordinator, key, name)
        self.opcode = opcode
    async def async_press(self):
        await self.coordinator.blind.send(self.opcode)
