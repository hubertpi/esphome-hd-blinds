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

## Staged OTA and battery extensions (wire version remains 1)

Characteristic 0007 is OTA control/status (READ/WRITE, 16 bytes), 0008 is OTA
data (WRITE, maximum 244 bytes), and 0009 is battery diagnostics (READ, 4 bytes).
Status flag bit8 advertises staged OTA; bit6 means the battery byte is valid.
Motor state 4 means updating. Firmware version comes from Device Information
characteristic 2A26.

OTA control is `<BBHIII`: version 1, operation (1 begin, 2 finish, 3 abort),
reserved u16, total GBL bytes u32, two reserved u32 fields. Data is offset u32
followed by 4-byte-aligned chunks. Total must fit the 225280-byte slot. Both
write characteristics require an authenticated connection. Motor commands and
settings writes are blocked while updating.

OTA status is `<BBHIII`: version, state, error code, bytes written, total bytes,
bootloader version. States are 0 idle, 1 erasing, 2 ready, 3 receiving, 4 verifying,
5 reboot pending, 6 error. Erasure/verification happen incrementally. Only a
fully received GBL that passes bootloader verification is scheduled to install.
A 120-second inactivity timeout or disconnect aborts an unfinished transfer.

Battery diagnostics is `<HH`: millivolts, ADC raw value. 65535 means unknown.
0.2.0 returns unknown; 0.2.1 samples the factory divider while idle, using PF6
for divider power, APORT1XCH20, 2.5 V reference, and 147/47 scaling. Eight 12-bit
samples are averaged once per minute. Values outside 2.5–4.35 V are rejected.
Percentage is explicitly a single-cell Li-ion voltage estimate, not measured
remaining charge capacity. The voltage mapping still needs a meter check.
