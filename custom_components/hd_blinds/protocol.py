"""Versioned wire protocol shared with the BGM13P22 firmware."""
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import hmac
import struct

SERVICE = 'b7e50001-6f8a-4d47-9ca5-3129a5c7a600'
COMMAND = SERVICE.replace('0001-', '0002-')
STATUS = SERVICE.replace('0001-', '0003-')
SETTINGS = SERVICE.replace('0001-', '0004-')
AUTH = SERVICE.replace('0001-', '0005-')
ENROLL = SERVICE.replace('0001-', '0006-')

class Opcode(IntEnum):
    PING = 0
    UP = 1
    DOWN = 2
    STOP = 3
    ZERO = 4
    PAIR = 5
    CLEAR_FAULT = 9

@dataclass(frozen=True)
class Status:
    state: int
    flags: int
    sequence: int
    result: int
    battery: int
    percent: int
    fault: int
    position: int
    pulses: int
    uptime: int

    @classmethod
    def decode(cls, data: bytes):
        if len(data) != 20 or data[0] != 1:
            raise ValueError('Unsupported blind status frame')
        return cls(*struct.unpack('<BBHHBBBBiIH', data)[1:])

@dataclass(frozen=True)
class Settings:
    up_pwm: int = 65
    down_pwm: int = 60
    startup_pwm: int = 75
    ramp_ms: int = 250
    max_run_ms: int = 10000

    def encode(self):
        if not (0 <= self.up_pwm <= 100 and 0 <= self.down_pwm <= 100
                and 50 <= self.startup_pwm <= 100 and 0 <= self.ramp_ms <= 2000
                and 100 <= self.max_run_ms <= 10000):
            raise ValueError('Settings outside firmware limits')
        return struct.pack('<BBBBHH', 1, self.up_pwm, self.down_pwm,
                           self.startup_pwm, self.ramp_ms, self.max_run_ms)

    @classmethod
    def decode(cls, data):
        if len(data) != 8 or data[0] != 1:
            raise ValueError('Unsupported blind settings frame')
        value = cls(*struct.unpack('<BBBBHH', data)[1:])
        value.encode()
        return value

def command(opcode, sequence, argument=0):
    return struct.pack('<BBHI', 1, Opcode(opcode), sequence, argument)

def proof(key, nonce):
    if len(key) != 32 or len(nonce) != 16:
        raise ValueError('Invalid pairing key or challenge')
    return hmac.new(key, nonce, hashlib.sha256).digest()[:16]


def device_name(address):
    """Stable default name shared with firmware advertising."""
    compact = address.replace(':', '').replace('-', '').upper()
    if len(compact) != 12 or any(c not in '0123456789ABCDEF' for c in compact):
        raise ValueError('Invalid Bluetooth address')
    return f'HD Blind {compact[-4:]}'

OTA_CONTROL = SERVICE.replace('0001-', '0007-')
OTA_DATA = SERVICE.replace('0001-', '0008-')
BATTERY = SERVICE.replace('0001-', '0009-')
FIRMWARE = '00002a26-0000-1000-8000-00805f9b34fb'

def ota_command(opcode, length=0):
    if opcode not in (1, 2, 3) or length < 0 or length > 225280 or length % 4:
        raise ValueError('Invalid OTA request')
    return struct.pack('<BBHIII', 1, opcode, 0, length, 0, 0)

def ota_status(data):
    if len(data) != 16 or data[0] != 1:
        raise ValueError('Unsupported OTA status')
    _, state, error, written, total, loader = struct.unpack('<BBHIII', data)
    if state == 6:
        raise RuntimeError(f'Firmware update failed: bootloader code 0x{error:04x}')
    return state, written, total
