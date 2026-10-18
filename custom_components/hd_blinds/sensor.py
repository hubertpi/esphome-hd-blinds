from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from .entity import BlindEntity

SENSORS = [('position', 'Raw position'), ('pulses', 'Encoder pulses'),
           ('state', 'Motor state'), ('fault', 'Motor fault')]
async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindSensor(entry.runtime_data, *s) for s in SENSORS])

class BlindSensor(BlindEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
    @property
    def native_value(self):
        value = getattr(self.coordinator.data, self.key)
        if self.key == 'state':
            return {0: 'idle', 1: 'opening', 2: 'closing', 3: 'fault'}.get(value, 'unknown')
        if self.key == 'fault':
            return {0: 'none', 1: 'stall', 2: 'run_timeout', 3: 'initialization'}.get(value, f'fault_{value}')
        return value
