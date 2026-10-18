from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from .entity import BlindEntity

SETTINGS = [
    ('slow_up_pwm', 'Near-target Up PWM', 40, 100, 1, '%'),
    ('slow_down_pwm', 'Near-target Down PWM', 40, 100, 1, '%'),
    ('slow_counts', 'Slowdown distance', 4, 2000, 1, 'counts'),
    ('up_pwm', 'Up PWM', 0, 100, 1, '%'),
    ('down_pwm', 'Down PWM', 0, 100, 1, '%'),
    ('startup_pwm', 'Startup PWM', 50, 100, 1, '%'),
    ('ramp_ms', 'Startup ramp', 0, 2000, 10, 'ms'),
    ('max_run_ms', 'Maximum run time', 100, 120000, 100, 'ms'),
]
async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindNumber(entry.runtime_data, *s) for s in SETTINGS])

class BlindNumber(BlindEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    def __init__(self, coordinator, key, name, minimum, maximum, step, unit):
        super().__init__(coordinator, key, name)
        self.key = key
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
    @property
    def available(self):
        if self.key in ('slow_up_pwm','slow_down_pwm','slow_counts'):
            return super().available and self.coordinator.blind.calibration is not None
        return super().available
    @property
    def native_value(self):
        if self.key in ('slow_up_pwm','slow_down_pwm','slow_counts'):
            return getattr(self.coordinator.blind.calibration,self.key,None)
        return getattr(self.coordinator.blind.settings, self.key)
    async def async_set_native_value(self, value):
        await self.coordinator.blind.set_setting(self.key, value)
        self.async_write_ha_state()
