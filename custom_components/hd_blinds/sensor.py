from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from .entity import BlindEntity

SENSORS = [('position', 'Raw position'), ('pulses', 'Encoder pulses'),
           ('state', 'Motor state'), ('fault', 'Motor fault'),
           ('battery', 'Battery'), ('battery_mv', 'Battery voltage'), ('battery_raw', 'Battery ADC')]
async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindSensor(entry.runtime_data, *s) for s in SENSORS])

class BlindSensor(BlindEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        if key == 'battery':
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = '%'
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == 'battery_mv':
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = 'V'
            self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        if self.key == 'battery':
            value = self.coordinator.data.battery
            return value if self.coordinator.data.flags & 64 and value <= 100 else None
        if self.key == 'battery_mv':
            value = self.coordinator.blind.battery_mv
            return None if value is None else value / 1000
        if self.key == 'battery_raw':
            return self.coordinator.blind.battery_raw
        value = getattr(self.coordinator.data, self.key)
        if self.key == 'state':
            return {0: 'idle', 1: 'opening', 2: 'closing', 3: 'fault', 4: 'updating'}.get(value, 'unknown')
        if self.key == 'fault':
            return {0: 'none', 1: 'stall', 2: 'run_timeout', 3: 'initialization'}.get(value, f'fault_{value}')
        return value
