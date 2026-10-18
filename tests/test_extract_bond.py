import importlib.util
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('extract', Path(__file__).parents[1] / 'tools/extract_bond.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TARGET = '02:00:00:00:00:04'

def record(packet, flags=0, timestamp=1):
    return struct.pack('>IIIIQ', len(packet), len(packet), flags, 0, timestamp) + packet

def capture(*packets):
    return b'btsnoop\0' + struct.pack('>II', 1, 1002) + b''.join(packets)

def connect(mac, handle=1):
    return record(bytes([4, 62, 31, 10, 0]) + struct.pack('<H', handle) + b'\0\0' + bytes.fromhex(mac.replace(':', ''))[::-1] + bytes(19), 1)

def key(handle=1):
    return record(b'\x01\x19\x20\x1c' + struct.pack('<H', handle) + bytes(8) + b'\x34\x12' + bytes(range(16)))

def encrypted(handle=1, status=0):
    return record(b'\x04\x59\x05' + bytes([status]) + struct.pack('<H', handle) + b'\x01\x10', 1)

class ParserTests(unittest.TestCase):
    def test_success_preserves_hci_key_order(self):
        result, _ = module.parse_snoop(capture(connect(TARGET), key(), encrypted()), TARGET)
        self.assertEqual(result['ltk'], '000102030405060708090a0b0c0d0e0f')
        self.assertEqual(result['ediv'], 0x1234)
    def test_failed_encryption_not_returned(self):
        result, _ = module.parse_snoop(capture(connect(TARGET), key(), encrypted(status=6)), TARGET)
        self.assertIsNone(result)
    def test_handle_reuse_cannot_select_another_devices_key(self):
        result, _ = module.parse_snoop(capture(connect(TARGET), connect('02:00:00:00:00:06'), key(), encrypted()), TARGET)
        self.assertIsNone(result)
    def test_truncated_record_rejected(self):
        with self.assertRaises(ValueError):
            module.parse_snoop(capture(connect(TARGET))[:-2], TARGET)

if __name__ == '__main__':
    unittest.main()
