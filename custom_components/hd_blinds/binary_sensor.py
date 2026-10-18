from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from .entity import BlindEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FlagSensor(entry.runtime_data, key, name, mask) for key, name, mask in
        [('pairing', 'Pairing mode', 2), ('charging', 'Charging', 8), ('charger', 'Charger connected', 16), ('calibrated', 'Travel calibrated', 1024),
         ('position_valid', 'Position referenced', 4096), ('calibrating', 'Calibration active', 2048)]])

class FlagSensor(BlindEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, key, name, mask):
        super().__init__(coordinator, key, name)
        self.mask = mask
    @property
    def is_on(self):
        return bool(self.coordinator.data.flags & self.mask)
