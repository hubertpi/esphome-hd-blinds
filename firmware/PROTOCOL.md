# HD Blind BLE protocol v1

Service `b7e50001-6f8a-4d47-9ca5-3129a5c7a600`; characteristics replace 0001
with 0002 command, 0003 status, 0004 settings, 0005 authentication, 0006 enrollment.
All integer fields are little-endian. Python reference: integration/protocol.py.

Command (8 bytes): version u8, opcode u8, sequence u16, argument u32.
Opcodes: 0 ping, 1 up, 2 down, 3 stop, 4 zero counters, 5 pairing window,
9 clear fault. Movement argument is milliseconds; zero uses configured timeout.
All commands require authentication. A status read acknowledges sequence/result.
Result: 0 success, 1 unauthenticated, 2 malformed, 3 range, 4 busy,
5 unsupported, 6 latched fault. Movement is never automatically replayed.

Status (20 bytes): version u8, state u8, flags u16, sequence u16, result u8,
battery u8, percentage u8, fault u8, signed position i32, pulses u32, uptime u16.
State: 0 idle, 1 opening, 2 closing, 3 fault.
Flags: bit0 key provisioned, bit1 pairing window, bit2 current connection
authenticated, bit3 charging active, bit4 wall power present, bit7 encoder present.
Battery and percentage are 255 (unknown). No percentage calibration is present.
Faults: 0 none, 2 timeout, 3 initialization. Charger meanings derive from original
firmware and still need physical confirmation.

Settings (8 bytes): version u8, up PWM u8, down PWM u8, startup PWM u8,
ramp milliseconds u16, max runtime milliseconds u16. Settings writes require
authentication and a stopped motor, and are persisted only on a valid write.
Limits: direction PWM 0–100%, startup 50–100%, ramp 0–2000 ms, runtime 100–10000 ms.

Authentication: read the fresh 16-byte connection challenge; write the first
16 bytes of HMAC-SHA256(key, challenge). The key is 32 random bytes persisted
in NVM3. Read it from enrollment only during the 90-second physical pairing
window. A 3-second button hold opens that window. This avoids OS bonding
requirements on ESPHome proxy connections. Enrollment is unencrypted; it must
occur in a trusted environment. This protocol does not implement encrypted
application payloads or signed OTA images yet.
