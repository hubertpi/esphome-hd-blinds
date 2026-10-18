# HD custom firmware and Home Assistant integration — bench preview

The existing ESPHome component remains for blinds running factory firmware.
The new integration in `custom_components/hd_blinds` talks directly to the new
BG13 firmware over Home Assistant Bluetooth, including active ESPHome proxies.
No phone address spoofing or imported factory bond is needed for custom firmware.

## Included

- Cover: Open, Close, Stop.
- Numbers: Up PWM, Down PWM, Startup PWM, Startup ramp, Maximum run time.
- Diagnostics: signed raw position, encoder pulse count, motor state, fault.
- Binary sensors: Pairing mode, Charging, Charger connected.
- Buttons: Zero position counter, Clear motor fault, Open pairing mode.
- Physical button: hold 3 seconds for 90-second enrollment.
- Blue pairing LED and red charging LED, reconstructed from factory routines.
- Persistent motor settings and per-connection HMAC authentication.
- Local stop on BLE disconnect and a maximum 10-second movement timeout.

The first build is for the loose test motor. Up/down labels and LED/charging
mapping need confirmation on hardware. No end limits or calibrated percentage
are claimed. Reaching the run timeout stops the motor and latches a fault;
use Clear motor fault before another movement. Zero counter is only available
while stopped. Counters reset on boot. The startup ramp begins at 50%, rises
to Startup PWM, then changes to the selected direction's running PWM.

## Install Home Assistant integration

Add `hubertpi/esphome-hd-blinds` to HACS custom repositories as **Integration**,
install HD Blinds, then restart Home Assistant. Alternatively copy
`custom_components/hd_blinds` into `/config/custom_components/hd_blinds`.

After custom firmware is running, hold its physical pairing button for 3 seconds
and add the discovered HD Blind in Settings → Devices & services. The first
boot also opens enrollment. Pairing requires proximity to an active Bluetooth
proxy. Keep the enrollment window closed outside provisioning; the enrollment
key is transferred over BLE while that physical window is open.

## Firmware status and recovery

`firmware/releases/hd-blind-bench.bin.gz.b64` contains the compiled main-flash
image (base64 of gzip). The companion JSON gives its size, SHA-256 and address.
It includes the SDK AppLoader at address zero and the application at 0xD800.
It is not the factory application image and is not flashed at factory address
0x9000. **OTA entry is disabled in this build.** A matched bootloader/recovery
check and OTA transport are still required before OTA can be declared working.

A host build is not a hardware test. Before the first replacement flash, retain
the original 512 KiB backup and save the device's separate bootloader and user
areas. Do not mass erase the device or its factory information pages. Main flash
alone does not back up the separate bootloader area. Do not install on the
mounted blinds until the spare passes movement, charging and recovery tests.

See `firmware/readme.md` for build instructions and pin mappings, and
`firmware/PROTOCOL.md` for the wire format.
