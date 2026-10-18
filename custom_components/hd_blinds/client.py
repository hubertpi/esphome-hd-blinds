"""BLE transport. Uses HA's selected adapter, including active ESPHome proxies."""
import asyncio
import time
from dataclasses import replace
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from . import protocol as p

class BlindClient:
    def __init__(self, get_device, key, changed=None):
        self.get_device = get_device
        self.key = key
        self.changed = changed
        self.client = None
        self.status = None
        self.settings = p.Settings()
        self.lock = asyncio.Lock()
        self.sequence = 0
        self.updating = False
        self.firmware_version = None
        self.battery_mv = None
        self.battery_raw = None
        self.calibration = None
        self._diagnostics_at = None
        self._diagnostics_task = None
        self._closing = False

    def _disconnected(self, client):
        if self.changed and not self._closing:
            self.changed(None)

    def _notification(self, characteristic, value):
        self.status = p.Status.decode(bytes(value))
        if self.changed:
            self.changed(self.status)
        # Read voltage alongside the sparse battery/status push, not every move.
        # A single managed task avoids parallel refreshes while notifications arrive.
        if (self.status.flags & 64 and not self.updating
                and (self.battery_mv is None or self._diagnostics_at is None or time.monotonic()-self._diagnostics_at>=5*3600)
                and (self._diagnostics_task is None or self._diagnostics_task.done())):
            self._diagnostics_task=asyncio.create_task(self._refresh_diagnostics())

    async def _refresh_diagnostics(self):
        try:
            status=await self.refresh()
            if self.changed:self.changed(status)
        except Exception:
            # The coordinator handles availability/reconnect; never replay commands.
            pass

    async def _connect(self, cache_retry=True):
        if self.client and self.client.is_connected:
            return
        self._closing = False
        device = self.get_device()
        if device is None:
            raise ConnectionError('Blind is not in range of an active Bluetooth adapter')
        self.client = await establish_connection(
            BleakClientWithServiceCache, device, 'HD Blind', self._disconnected,
            ble_device_callback=self.get_device, use_services_cache=False)
        try:
            nonce = await self.client.read_gatt_char(p.AUTH)
            await self.client.write_gatt_char(p.AUTH, p.proof(self.key, nonce), response=True)
            status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            if not status.flags & 4:
                raise PermissionError('Blind authentication failed')
            # OTA-capable firmware must expose these UUIDs. ESPHome/BlueZ may
            # retain an older service table even with use_services_cache=False.
            if status.flags & 256 and hasattr(self.client, 'services'):
                required = [p.OTA_CONTROL, p.OTA_DATA, p.BATTERY]
                if status.flags & p.CAL_CAPABLE:
                    required.append(p.CALIBRATION)
                missing = [uuid for uuid in required
                           if self.client.services.get_characteristic(uuid) is None]
                if missing:
                    if not cache_retry:
                        raise ConnectionError('Bluetooth service cache is still missing OTA characteristics')
                    await self.client.clear_cache()
                    await self.client.disconnect()
                    self.client = None
                    await self._connect(cache_retry=False)
                    return
            self.firmware_version = bytes(await self.client.read_gatt_char(p.FIRMWARE)).decode('utf-8').rstrip('\0')
            self.settings = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            await self.client.start_notify(p.STATUS, self._notification)
            self.status = status
        except Exception:
            if self.client is not None:
                await self.client.disconnect()
            raise

    async def refresh_status(self):
        """Read only the live count/state for responsive calibration screens."""
        async with self.lock:
            await self._connect()
            self.status=p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            if self.changed:self.changed(self.status)
            return self.status

    async def refresh(self):
        async with self.lock:
            await self._connect()
            self.status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            if self.status.flags & 64:
                data = bytes(await self.client.read_gatt_char(p.BATTERY))
                import struct
                mv, raw = struct.unpack("<HH", data)
                self.battery_mv = None if mv == 65535 else mv
                self.battery_raw = None if raw == 65535 else raw
            if self.status.flags & p.CAL_CAPABLE:
                self.calibration = p.Calibration.decode(await self.client.read_gatt_char(p.CALIBRATION))
            self._diagnostics_at=time.monotonic()
            return self.status

    async def send(self, opcode, argument=0):
        if self.updating:
            raise RuntimeError('A firmware update is in progress')
        async with self.lock:
            await self._connect()
            self.sequence = (self.sequence + 1) & 65535
            # Movement is sent once: never replay a possibly accepted command.
            await self.client.write_gatt_char(p.COMMAND,
                p.command(opcode, self.sequence, argument), response=True)
            status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            self.status = status
            if status.sequence != self.sequence:
                raise RuntimeError('Blind acknowledgement sequence did not match; command was not replayed')
            if status.result:
                if status.result==3 and status.flags & p.CALIBRATED and not status.flags & p.POSITION_VALID:
                    raise RuntimeError('Position reference is uncertain. Recalibrate before moving to a position or endpoint.')
                if status.result==6:
                    raise RuntimeError('Motor fault is latched. Check Motor fault and clear it before moving.')
                if status.result==4:
                    raise RuntimeError('Blind is busy moving, finishing its stop, calibrating, or updating.')
                raise RuntimeError(f'Blind command rejected: result {status.result}')
            if self.changed:
                self.changed(status)

    async def set_setting(self, name, value):
        if self.updating:
            raise RuntimeError('A firmware update is in progress')
        async with self.lock:
            await self._connect()
            if name in ('slow_up_pwm','slow_down_pwm','slow_counts'):
                current=p.Calibration.decode(await self.client.read_gatt_char(p.CALIBRATION))
                updated=replace(current,**{name:int(value)})
                await self.client.write_gatt_char(p.CALIBRATION,updated.encode(),response=True)
                self.calibration=p.Calibration.decode(await self.client.read_gatt_char(p.CALIBRATION))
                if self.changed:self.changed(self.status)
                return
            current = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            updated = replace(current, **{name: int(value)})
            await self.client.write_gatt_char(p.SETTINGS, updated.encode(legacy=not self.status.flags & p.CAL_CAPABLE), response=True)
            self.settings = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            if self.changed:
                self.changed(self.status)

    async def disconnect(self):
        self._closing = True
        if self._diagnostics_task and not self._diagnostics_task.done():
            self._diagnostics_task.cancel()
            await asyncio.gather(self._diagnostics_task,return_exceptions=True)
        if self.client and self.client.is_connected:
            await self.client.disconnect()

    async def install_firmware(self, image, progress):
        """Transfer one verified GBL without retrying ambiguous writes."""
        if not image or len(image) > 225280 or len(image) % 4:
            raise ValueError('Invalid update size')
        if self.updating:
            raise RuntimeError('An update is already running')
        self.updating = True
        try:
            async with self.lock:
                await self._connect()
                if not self.status.flags & 256:
                    raise RuntimeError('Install the OTA bootstrap firmware over SWD first')
                await self.client.write_gatt_char(p.OTA_CONTROL, p.ota_command(1, len(image)), response=True)
                for _ in range(120):
                    state, _, _ = p.ota_status(await self.client.read_gatt_char(p.OTA_CONTROL))
                    if state == 2:
                        break
                    await asyncio.sleep(1)
                else:
                    raise TimeoutError('Timed out preparing update storage')
                import struct
                chunk = min(240, max(4, ((self.client.mtu_size - 7) // 4) * 4))
                for offset in range(0, len(image), chunk):
                    part = image[offset:offset + chunk]
                    await self.client.write_gatt_char(p.OTA_DATA, struct.pack('<I', offset) + part, response=True)
                    progress((offset + len(part)) * 90 / len(image))
                await self.client.write_gatt_char(p.OTA_CONTROL, p.ota_command(2), response=True)
                for _ in range(120):
                    state, _, _ = p.ota_status(await self.client.read_gatt_char(p.OTA_CONTROL))
                    if state == 5:
                        progress(95)
                        return
                    await asyncio.sleep(0.25)
                raise TimeoutError('Timed out verifying update')
        finally:
            self.updating = False
