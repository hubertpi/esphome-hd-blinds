"""Exercise transport authentication, reconnect and commands with a fake peripheral."""
import asyncio
from dataclasses import replace
import importlib
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest.mock import AsyncMock

root=Path(__file__).resolve().parents[1]/'custom_components/hd_blinds'
package=types.ModuleType('hd_blinds_test');package.__path__=[str(root)]
sys.modules['hd_blinds_test']=package
m=importlib.import_module('hd_blinds_test.client')
p=importlib.import_module('hd_blinds_test.protocol')

class Peripheral:
    def __init__(self):
        self.is_connected=True
        self.settings=p.Settings()
        self.sequence=0
        self.result=0
        self.writes=[]
        self.mtu_size=23
        self.ota=False
        self.ota_state=0
        self.ota_written=0
        self.ota_total=0
    async def read_gatt_char(self, uuid):
        if uuid==p.OTA_CONTROL:return struct.pack('<BBHIII',1,self.ota_state,0,self.ota_written,self.ota_total,0)
        if uuid==p.BATTERY:return bytes.fromhex('ffffffff')
        if uuid==p.AUTH:return bytes(16)
        if uuid==p.FIRMWARE:return b'0.1.0'
        if uuid==p.SETTINGS:return self.settings.encode()
        return struct.pack('<BBHHBBBBiIH',1,0,0x85|(256 if self.ota else 0),self.sequence,self.result,255,255,0,0,0,0)
    async def write_gatt_char(self, uuid, data, response):
        self.writes.append((uuid,data))
        if uuid==p.OTA_CONTROL:
            opcode=data[1]
            if opcode==1:self.ota_state=2;self.ota_total=struct.unpack_from('<I',data,4)[0]
            if opcode==2:self.ota_state=5
        if uuid==p.OTA_DATA:self.ota_written+=len(data)-4
        if uuid==p.COMMAND:self.sequence=struct.unpack('<BBHI',data)[2]
        elif uuid==p.SETTINGS:self.settings=p.Settings.decode(data)
    async def start_notify(self, uuid, callback):pass
    async def disconnect(self):self.is_connected=False

class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.peripheral=Peripheral()
        self.old=m.establish_connection
        m.establish_connection=AsyncMock(return_value=self.peripheral)
        self.blind=m.BlindClient(lambda:object(),bytes(32))
    async def asyncTearDown(self):m.establish_connection=self.old
    async def test_auth_before_command(self):
        await self.blind.send(p.Opcode.UP)
        self.assertEqual([u for u,v in self.peripheral.writes],[p.AUTH,p.COMMAND])
        self.assertEqual(self.peripheral.writes[0][1],p.proof(bytes(32),bytes(16)))
    async def test_settings_preserve_other_values(self):
        await self.blind.set_setting('down_pwm',57)
        self.assertEqual(self.blind.settings,replace(p.Settings(),down_pwm=57))
    async def test_rejected_command(self):
        self.peripheral.result=6
        with self.assertRaises(RuntimeError):await self.blind.send(p.Opcode.UP)
    async def test_unavailable(self):
        self.blind.get_device=lambda:None
        with self.assertRaises(ConnectionError):await self.blind.refresh()
    async def test_no_replay_after_uncertain_write(self):
        await self.blind.refresh()
        self.peripheral.write_gatt_char=AsyncMock(side_effect=ConnectionError('link lost'))
        with self.assertRaises(ConnectionError):await self.blind.send(p.Opcode.UP)
        self.assertEqual(self.peripheral.write_gatt_char.await_count,1)
    async def test_sequence_wrap(self):
        self.blind.sequence=65535
        await self.blind.send(p.Opcode.STOP)
        self.assertEqual(self.blind.status.sequence,0)

    async def test_ota_chunks_fit_mtu_and_have_offsets(self):
        self.peripheral.ota=True
        progress=[]
        await self.blind.install_firmware(bytes(36),progress.append)
        parts=[d for u,d in self.peripheral.writes if u==p.OTA_DATA]
        self.assertEqual([struct.unpack_from('<I',d)[0] for d in parts],[0,16,32])
        self.assertTrue(all(len(d)<=20 for d in parts))
        self.assertEqual(self.peripheral.ota_written,36)
        self.assertEqual(progress[-1],95)
        self.assertFalse(self.blind.updating)

    async def test_ota_requires_bootstrap(self):
        with self.assertRaises(RuntimeError):
            await self.blind.install_firmware(bytes(36),lambda x:None)
        self.assertFalse(any(u==p.OTA_DATA for u,d in self.peripheral.writes))

    async def test_bootstrap_refresh_does_not_require_battery_characteristic(self):
        self.peripheral.ota=True
        read=self.peripheral.read_gatt_char
        async def without_battery(uuid):
            if uuid==p.BATTERY:raise AssertionError('Battery diagnostic read before battery-valid flag')
            return await read(uuid)
        self.peripheral.read_gatt_char=without_battery
        status=await self.blind.refresh()
        self.assertTrue(status.flags & 256)
        self.assertIsNone(self.blind.battery_mv)

    async def test_stale_ota_services_cleared_before_reconnect(self):
        self.peripheral.ota=True
        services=types.SimpleNamespace(get_characteristic=lambda uuid:None)
        self.peripheral.services=services
        async def clear():
            services.get_characteristic=lambda uuid:object()
            return True
        self.peripheral.clear_cache=AsyncMock(side_effect=clear)
        async def connect(*args,**kwargs):
            self.peripheral.is_connected=True
            return self.peripheral
        m.establish_connection=AsyncMock(side_effect=connect)
        await self.blind.refresh()
        self.peripheral.clear_cache.assert_awaited_once()
        self.assertEqual(m.establish_connection.await_count,2)
