# HD Blind experimental firmware

Target: BGM13P22F512GA / EFR32BG13P, REV.J motor PCB.
Gecko SDK 4.4.6, commit 59d2160fe448b13730a91c0f019a8b4c53c43eb2.

Firmware 0.3.3 provides guided upper/lower calibration through the HA Configure
flow, persistent encoder position, and a cover percentage target after
calibration. Movement has a configurable hard timeout up to 120 seconds and a
2-second no-encoder-progress watchdog. Endpoint slowdown/coast control still
requires physical bench validation before use on an installed blind.
See PROTOCOL.md for power-loss semantics and calibration commands.

Pairing: hold PC8 button for 3 seconds to open a 90-second enrollment window.
The first boot also opens enrollment. Home Assistant stores a generated key
and authenticates each BLE connection with HMAC-SHA256. Active ESPHome BLE
proxies can carry the GATT connection without importing the original phone bond.
Enrollment transfers the key over BLE during the physical pairing window;
only open that window when provisioning in a trusted environment.

Factory code maps PC8 to the pairing button, PD14 to blue, PD13 to red,
PC7 low to charging active, and PB13 low to wall power present. These mappings
are implemented and await physical bench confirmation. Hardware charge-control
pins are left at their reset input configuration. Charge control and its
indicators must be verified before using this build on an installed blind.

The SDK AppLoader is linked. Its legacy OTA entry stays disabled. The authenticated
custom staged OTA interface is enabled in 0.2.0 and later.
Do not flash a standalone application over the factory loader without checking
its address/layout and retaining the original flash backup.

Generate with Silicon Labs SLC CLI (trusted SDK selected):

```
slc generate firmware/hd_blind.slcp -np -d build/hd_blind -o makefile
make -C build/hd_blind -f hd_blind.Makefile ARM_GCC_DIR=/path/to/gcc-arm
```

The SDK and compiler are external dependencies, not vendored in this repository.


Power behavior: event-driven idle sleep, boot/six-hour battery measurements,
sparse idle notifications, 4 Hz moving position, direct Stop handling. GPIO wakes
retain physical pairing/charging indications. See PROTOCOL.md for intervals and
CUSTOM_FIRMWARE.md for integration update instructions. Savings are unmeasured.
