from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverEntityFeature
from .entity import BlindEntity
from .protocol import Opcode, CALIBRATED, POSITION_VALID, CALIBRATING

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BlindCover(entry.runtime_data)])

class BlindCover(BlindEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    def __init__(self, coordinator):
        super().__init__(coordinator, 'cover', None)
    @property
    def supported_features(self):
        features=CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if self.current_cover_position is not None:features |= CoverEntityFeature.SET_POSITION
        return features
    @property
    def current_cover_position(self):
        status=self.coordinator.data
        required=CALIBRATED | POSITION_VALID
        if status.flags & required == required and not status.flags & CALIBRATING and status.percent<=100:
            return status.percent
        return None
    @property
    def is_closed(self):
        return None if self.current_cover_position is None else self.current_cover_position==0
    async def async_set_cover_position(self, **kwargs):
        await self.coordinator.blind.send(Opcode.SET_POSITION,int(kwargs['position']))
    @property
    def is_opening(self):
        return self.coordinator.data.state == 1
    @property
    def is_closing(self):
        return self.coordinator.data.state == 2
    async def async_open_cover(self, **kwargs):
        await self.coordinator.blind.send(Opcode.UP)
    async def async_close_cover(self, **kwargs):
        await self.coordinator.blind.send(Opcode.DOWN)
    async def async_stop_cover(self, **kwargs):
        await self.coordinator.blind.send(Opcode.STOP)
