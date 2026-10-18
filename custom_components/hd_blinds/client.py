"""BLE transport. Uses HA's selected adapter, including active ESPHome proxies."""
import asyncio
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

    def _disconnected(self, client):
        if self.changed:
            self.changed(None)

    def _notification(self, characteristic, value):
        self.status = p.Status.decode(bytes(value))
        if self.changed:
            self.changed(self.status)

    async def _connect(self):
        if self.client and self.client.is_connected:
            return
        device = self.get_device()
        if device is None:
            raise ConnectionError('Blind is not in range of an active Bluetooth adapter')
        self.client = await establish_connection(
            BleakClientWithServiceCache, device, 'HD Blind', self._disconnected,
            ble_device_callback=self.get_device)
        try:
            nonce = await self.client.read_gatt_char(p.AUTH)
            await self.client.write_gatt_char(p.AUTH, p.proof(self.key, nonce), response=True)
            status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            if not status.flags & 4:
                raise PermissionError('Blind authentication failed')
            self.settings = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            await self.client.start_notify(p.STATUS, self._notification)
            self.status = status
        except Exception:
            await self.client.disconnect()
            raise

    async def refresh(self):
        async with self.lock:
            await self._connect()
            self.status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            return self.status

    async def send(self, opcode, argument=0):
        async with self.lock:
            await self._connect()
            self.sequence = (self.sequence + 1) & 65535
            # Movement is sent once: never replay a possibly accepted command.
            await self.client.write_gatt_char(p.COMMAND,
                p.command(opcode, self.sequence, argument), response=True)
            status = p.Status.decode(await self.client.read_gatt_char(p.STATUS))
            self.status = status
            if status.sequence != self.sequence or status.result:
                raise RuntimeError(f'Blind command rejected: result {status.result}')
            if self.changed:
                self.changed(status)

    async def set_setting(self, name, value):
        async with self.lock:
            await self._connect()
            current = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            updated = replace(current, **{name: int(value)})
            await self.client.write_gatt_char(p.SETTINGS, updated.encode(), response=True)
            self.settings = p.Settings.decode(await self.client.read_gatt_char(p.SETTINGS))
            if self.changed:
                self.changed(self.status)

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
