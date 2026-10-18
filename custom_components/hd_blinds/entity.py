from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class BlindEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        address = coordinator.entry.data['address']
        self._attr_unique_id = f'{address}_{key}'
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)}, name=coordinator.entry.title,
            manufacturer='HD Blinds Community', model='BGM13P22 custom firmware',
            sw_version='0.1.0')
