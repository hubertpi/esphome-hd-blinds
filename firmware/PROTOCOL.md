# HD Blind BLE protocol v1

Service `b7e50001-6f8a-4d47-9ca5-3129a5c7a600`; characteristics replace 0001
with 0002 command, 0003 status, 0004 settings, 0005 authentication, 0006 enrollment.
All integer fields are little-endian. Python reference: custom_components/hd_blinds/protocol.py.

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
Battery/percentage use 255 when unknown. Firmware 0.2.1 adds battery sampling;
0.3.0 adds calibrated percentage positioning, described below.
Faults: 0 none, 2 timeout, 3 initialization, 4 flash write, 5 encoder stall. Charger meanings derive from original
firmware and still need physical confirmation.

Legacy settings v1 (8 bytes): version u8, up PWM u8, down PWM u8, startup PWM u8,
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

## Calibration and positioning (firmware 0.3.0)

The 20-byte status/8-byte command layouts remain unchanged. New status flags:
512 calibration capable; 1024 limits saved; 2048 calibration in progress;
4096 position referenced; 8192 upper limit captured for current calibration.
Status percentage is HA openness (100 open, 0 closed), 255 when unreferenced.
Encoder coordinates use upper=0 and increasing counts downward. Physical coast
counts remain visible; the firmware does not snap the encoder count to a target.

Command extensions: 10 begin calibration (invalidates old coordinates),
11 capture upper zero, 12 capture lower and atomically commit limits,
13 cancel calibration, 14 jog up, 15 jog down (argument 50–1000 milliseconds),
16 move to HA open percentage (argument 0–100). Endpoint capture requires the
motor stopped and coast settled. Lower travel must be 4–10,000,000 counts.
Jogs require calibration mode; ordinary movement is blocked during calibration.
After calibration, commands 1/2 with argument zero target upper/lower limits.
Position commands require a referenced count. Lost power during motion preserves
limits and the last saved count, but prevents automatic positioning until a new
calibration establishes the reference. Disconnect stops motion locally.

Settings v2 is 10 bytes `<BBBBHI`: version 2, up/down/startup PWM, ramp_ms u16,
max_run_ms u32 (100–120000). Firmware accepts legacy 8-byte v1 writes and migrates
stored v1 PWM/ramp values; the initial travel timeout becomes 120000 ms.

Calibration characteristic `b7e5000a-6f8a-4d47-9ca5-3129a5c7a600`, READ/WRITE,
24 bytes `<BBHiiHHHHBBxx`: version 1, stage (0 normal/1 upper/2 lower), flags,
travel, target, up/down coast allowance, slowdown counts, settle_ms, near-target
up/down PWM, two reserved bytes. Writes change only slowdown distance (4–2000)
and near-target up/down PWM (40–100); all coordinate/state fields are read-only.
Writes require authentication and idle/non-calibration state. PWM is capped at
the configured cruise speed. Defaults: up 60%, down 55%, slowdown 32 counts plus
200 ms velocity lookahead. Directional stopping allowance is learned from coast
and bounded to 16 counts. No automatic reversal or PID hunting is performed.

Bridge output is cut in the encoder IRQ at the requested target as a secondary
limit. Encoder power/count direction remain enabled for 300 ms after stopping to
capture coast. Motion without encoder progress for 2 seconds latches fault 5 and
invalidates the reference. Target run timeout latches fault 2; NVM write failure
is fault 4. GPIO single-channel encoder cannot detect unpowered/manual backdrive.

NVM3 objects: 0x48003 is a versioned six-word position record (version, calibrated,
travel, last settled position, referenced, packed up/down stopping allowance).
Before starting a move it is written with referenced=0; after settling it is
written with the current count and referenced=1 if the reference is trusted.
0x48004 stores four bytes of slowdown settings. There are no per-pulse flash
writes. Original pairing/settings and the OTA storage layout are retained.

### 0.3.2 startup and settling update

Startup PWM applies immediately, then linearly transitions to directional cruise
PWM during ramp_ms. For ramp_ms=0, cruise applies immediately. This fixes the
previous 50%-to-startup ramp and the position-mode cap that suppressed startup
torque. Endpoint slowdown is a separate later phase. Status flag 16384 denotes
the coast/settling interval; configuration flows may wait for it to clear before
capturing an endpoint. No wire frame lengths, NVM3 layouts or characteristic
UUIDs changed from 0.3.0.
