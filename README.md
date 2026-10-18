# esphome-hd-blinds

Experimental ESPHome external component for discontinued Home Decorators
Collection Bluetooth cellular-shade motors. Initial target: ESPHome
**2026.10.0b4**, classic ESP32, ESP-IDF **5.5.x**, Bluedroid.

## Status

The proprietary movement commands have been verified from a bonded Android
phone on one installed blind. The ESP implementation clones the phone's public
Bluetooth identity and imports its captured encryption key into Bluedroid RAM.
**Hardware acceptance of the ESP clone has not yet been verified.** A successful
firmware build is not a successful hardware test.

This does not modify the motor's firmware. PWM/speed control, actual position
feedback, percentage positioning, and calibration commands are not implemented.
`0x04` is an unverified Stop/Favorite command; when stationary it may move to
Favorite. Do not treat it as an emergency stop.

## Install on an existing device

1. Keep the existing ESP32, Wi-Fi, API, BLE tracker, and EasyStart configuration.
2. Remove the earlier `blind_hd0352` stock `ble_client:` entry and its three test
   buttons, to avoid having two clients connect to the same motor.
3. Merge [examples/hd0352.yaml](examples/hd0352.yaml) into the device YAML.
4. Put the captured phone identity and bond values into **local `secrets.yaml`**:

```yaml
hd_phone_mac: 'YOUR:PHONE:PUBLIC:BT:MAC'
hd_phone_name: 'Your phone Bluetooth name'
hd0352_ltk: '32 hexadecimal characters in HCI packet byte order'
hd0352_rand: '16 hexadecimal characters in HCI packet byte order'
hd0352_ediv: 0
hd0352_auth_mode: 9
```

For LE Secure Connections bonds, RAND and EDIV are normally zero. Do not assume
that for legacy bonds: extract the exact values from the capture. `auth_mode`
is the negotiated SMP bond mode (1=bond, 5=bond+MITM, 9=SC+bond, 13=SC+bond+MITM).
Current import supports 16-byte encryption keys and a public peripheral address.

5. Compile and install. Keep the cloned phone's Bluetooth **off** during the
   test: two active controllers must not share one Bluetooth identity.
6. Press Down on a partly open shade. The component queues the command,
   connects, enables bond encryption, discovers the command UUID, then writes.
   Look for `Encrypted and ready` followed by `Command acknowledged`.
   An acknowledgment only confirms the GATT write, not physical movement.
7. Test Up and Stop separately and verify the existing EasyStart still works.

**Shared adapter:** identity cloning changes the ESP's Bluetooth MAC/name for
all BLE connections. Its Wi-Fi MAC is not changed. Other peripherals bonded
to the original ESP identity may need attention; do not assume their existing
bonds remain usable. Keep a copy of your working device configuration.

For reproducible installations replace `@main` with the tested commit SHA and
remove `refresh: 0s`. During development the example intentionally reloads main.

## Connection behavior

- No movement or automatic blind connection on boot.
- Button presses initiate a connection through ESPHome's tracker scheduler.
- The latest button press replaces a still-queued command before transmission.
- A write already awaiting acknowledgment rejects new presses with a log message.
- Commands time out after 25 seconds and are not automatically retried.
- The encrypted link stays available for up to 20 seconds after a write so a
  subsequent Stop need not reconnect. The motor can close it earlier.
- Link loss discards queued commands; nothing executes unexpectedly on reconnect.
- UUID discovery must find the captured HDC control characteristic before writing.
- Bond keys are reimported into RAM after a BLE stack restart, not written into
  the ESP's persistent bond database. Firmware still contains the configured
  keys, as is usual for compiled ESPHome secrets.

## Why custom code is needed

The tested phone connection is encrypted. A stock ESPHome BLE client on the
unbonded ESP was disconnected during service discovery. This implementation
sets the phone's Bluetooth identity before BLE initialization, supplies the
captured LTK/RAND/EDIV to Bluedroid, and requests encryption before discovery.

ESP-IDF does not expose a public bond-import API. The implementation uses the
exported internal `BTA_DmAddBleDevice` and `BTA_DmAddBleKey` entry points, with
the ESP-IDF 5.5 key ABI explicitly represented. Other IDF major/minor versions
are rejected at compile time. This is an experimental, version-dependent
integration; inspect the ABI before porting to another IDF series.

Captured protocol:

| Item | Value |
|---|---|
| Service | `a2be20e1-cecf-4cfb-ac97-d656cb5b0e24` |
| Movement characteristic | `9d85a52d-4596-4076-b3ce-fd2fedf93c8b` |
| Down | `00` |
| Up | `01` |
| Stop/Favorite (unverified) | `04` |

Other captured setup writes are deliberately excluded: their meaning is not
established and they may alter limits or calibration.

## Validation

```sh
python -m pip install esphome==2026.10.0b4
esphome config tests/compile.yaml
esphome compile tests/compile.yaml
```

The compile configuration contains dummy addresses and keys only. Never commit
real bond keys, phone identifiers, captures, or your private device YAML.
