"""Wire compatibility tests without importing Home Assistant."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
path=Path(__file__).resolve().parents[1]/'custom_components/hd_blinds/protocol.py'
spec=importlib.util.spec_from_file_location('hd_protocol',path)
p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)

class ProtocolTests(unittest.TestCase):
    def test_status_signed_position(self):
        frame=struct.pack('<BBHHBBBBiIH',1,2,0x87,65535,0,255,255,0,-1024,4096,42)
        status=p.Status.decode(frame)
        self.assertEqual(status.position,-1024)
        self.assertEqual(status.pulses,4096)
        self.assertEqual(status.sequence,65535)

    def test_settings_limits_roundtrip(self):
        self.assertEqual(p.Settings.decode(p.Settings().encode()),p.Settings())
        for change in [dict(up_pwm=101),dict(startup_pwm=49),dict(max_run_ms=10001),dict(ramp_ms=2001)]:
            with self.assertRaises(ValueError):p.Settings(**change).encode()

    def test_command_layout(self):
        self.assertEqual(p.command(p.Opcode.DOWN,0x1234,1000),bytes.fromhex('01023412e8030000'))

    def test_hmac_known_vector(self):
        import hashlib,hmac
        self.assertEqual(p.proof(bytes(32),bytes(16)),hmac.new(bytes(32),bytes(16),hashlib.sha256).digest()[:16])
        with self.assertRaises(ValueError):p.proof(b'',bytes(16))

    def test_malformed_frames(self):
        for frame in [b'',bytes(19),bytes(20),bytes([2])+bytes(19)]:
            with self.assertRaises(ValueError):p.Status.decode(frame)

    def test_mac_name(self):
        self.assertEqual(p.device_name('08:6B:D7:6D:0D:3C'), 'HD Blind 0D3C')
        self.assertEqual(p.device_name('08:6b:d7:65:7d:52'), 'HD Blind 7D52')
