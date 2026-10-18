# HD custom firmware and Home Assistant integration — bench preview

The existing ESPHome component remains for blinds running factory firmware.
The new integration in `custom_components/hd_blinds` talks directly to the new
BG13 firmware over Home Assistant Bluetooth, including active ESPHome proxies.
No phone address spoofing or imported factory bond is needed for custom firmware.

## Current features (0.3.3)

- HA cover Open/Close/Stop and percentage targets after upper/lower calibration.
- Separate direction speeds, immediate Startup PWM followed by a ramp to cruise,
  near-end slowing settings, and a configurable maximum run time up to 120 seconds.
- Signed encoder position and pulse diagnostics; durable settled-position storage.
- Battery voltage and approximate single-cell Li-ion percentage; charging sensors.
- Physical pairing button, blue pairing/red charging LEDs, MAC-suffix name.
- Authenticated BLE control and staged custom OTA through active ESPHome proxies.
- Event-driven idle power savings with six-hour battery/idle telemetry and live
  position during movement. Detailed charging behavior and loaded motion still
  need physical validation on the test motor.

## Install Home Assistant integration

Add `hubertpi/esphome-hd-blinds` to HACS custom repositories as **Integration**,
install HD Blinds, then restart Home Assistant. Alternatively copy
`custom_components/hd_blinds` into `/config/custom_components/hd_blinds`.

After custom firmware is running, hold its physical pairing button for 3 seconds
and add the discovered HD Blind in Settings → Devices & services. The first
boot also opens enrollment. Pairing requires proximity to an active Bluetooth
proxy. Keep the enrollment window closed outside provisioning; the enrollment
key is transferred over BLE while that physical window is open.

## Historical first-build artifact and recovery

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

## Bench validation and normal boot

The spare passed HA enrollment, up/down, independent speeds, Stop, signed encoder
counting and the physical pairing button/blue LED. The factory bootloader enforces
ECDSA signatures and cannot start the unsigned custom image after reset. A direct
SWD application start demonstrated that the application itself runs.

`tools/install_bootloader.py --install` checks the saved factory bootloader backup,
download hashes, and bootloader write protection before writing. It writes the
named application and a matched SDK second stage, preserving the factory first
stage, user data and lock bits. The second stage is CRC protected and accepts
unsigned development firmware. The SRAM writer uses Silicon Labs emlib MSC code
and verifies each page; emulator tests exercise page boundaries and protected
refusal. Physical normal-boot validation is still pending. OTA remains disabled.

## OTA bootstrap and first wireless update

1. Redownload the HD Blinds integration in HACS and restart Home Assistant.
2. On the Pi run `tools/install_ota_bootstrap.py` with sudo to install **0.2.0**
   over SWD. This changes only the application/AppLoader main-flash image; it
   verifies that the bootloader is unchanged. Battery remains unknown in 0.2.0.
3. In the device page open the **Firmware** update entity and install **0.2.1**.
   The transfer uses HA's active BLE adapter/proxy. Keep the Pi connected for
   recovery during this first OTA test, but the OTA transfer does not use SWD.
4. After reconnect, confirm installed version 0.2.1 and inspect Battery, Battery
   voltage, and Battery ADC. Battery percentage is an estimate based on a
   single-cell Li-ion resting-voltage curve, not a coulomb counter. Validate the
   voltage against a meter before relying on percentage.

The updater downloads a hashed GBL, authenticates the BLE connection, erases only
the needed staging pages in 0x40000–0x77000, and transfers ordered chunks. The
bootloader verifies the complete image before scheduling installation. A failed
transfer or failed verification does not schedule installation. NVM3 enrollment
keys and settings above 0x77000 are retained. No automatic movement is replayed
after reconnect. The first OTA still needs physical validation.

The 0.2.1 application-only GBL is about 175 KiB and fits the 220 KiB staging
slot. A future minimal intermediate image is possible if growth consumes that
margin; it is not needed for this update.

### 0.3.0: guided calibration and cover position

Update the HA integration before installing firmware 0.3.0 via the Firmware
entity. Under Settings → Devices & services → HD Blinds, open Configure for the
blind. Start calibration, use the Up pulse/Down pulse buttons to find the upper
position, and select Set upper limit (zero). Then jog to the lower position and
select Set lower limit and finish. The screen reports encoder counts and offers
50–1000 ms pulses; motor timing is enforced on the blind, not by HA connectivity.
Starting calibration clears the previous coordinate reference. Cancelling or
closing the screen never leaves a jog running indefinitely.

The existing shade gains HA's position slider after calibration: 100% fully open,
0% fully closed; 10% open maps to 90% of the saved downward encoder range.
Up/Down then target the calibrated endpoints, while Stop remains available.
Slowdown distance and Near-target Up/Down PWM entities permit tuning on the test
motor. The first target move measures coast; subsequent moves use a bounded
per-direction stopping allowance. This is an initial bench controller, and end
accuracy under load still needs physical validation. It never silently resets
counts to hide overshoot. A 2-second encoder-stall watchdog and adjustable
maximum run time (up to 120 seconds) remain active.

Limits and the final encoder count are saved in wear-levelled NVM3 after the
motor's 300 ms coast interval. A pre-movement dirty marker ensures interrupted
movement cannot restore a falsely trusted count. Power loss while idle restores
the position. Power loss during motion retains the limits/last saved count but
requires recalibration before target moves. The single-channel encoder cannot
measure movement when its electronics are unpowered. New diagnostics expose
reference validity, calibration state, travel, target and directional allowance.

The device registry firmware version now refreshes automatically after OTA.

### 0.3.1: clear target completion before the next move

Fixes a target-reached latch that could immediately stop the movement following
an endpoint stop. The driver clears the latch when coast finishes; the command
handler also clears it before starting a move. Negative coast counts such as
-2 at the upper endpoint are retained and do not prevent downward travel.
Calibration, position records, PWM settings and pairing are unchanged. A native
board-driver regression exercises upper target → coast to -2 → downward travel.

### 0.3.2: startup semantics and independent firmware discovery

Startup PWM is applied immediately when a move is accepted. During Startup ramp
milliseconds it interpolates from Startup PWM to the selected Up/Down PWM. With
75% startup, 60% Down and a 250 ms ramp this means 75% immediately, then a ramp
to 60% over 250 ms. A zero ramp uses the direction's running PWM immediately.
Endpoint slowdown runs after this startup phase; the encoder target cutoff and
fault watchdog remain active throughout. Calibration/position/PWM data persist.

The HA integration checks the GitHub firmware manifest at startup and every six
hours, retains the last successful result during network errors, and downloads
and checksum-checks firmware only when Install is requested. A new firmware-only
release no longer requires a HACS integration redownload. Calling
homeassistant.update_entity on the Firmware entity checks immediately. Future
integration releases use numeric major.minor.patch GitHub release tags.

Calibration pages no longer reread settings/battery several times per pulse.
They wait only for the timed jog/coast and perform a lightweight status read;
the normal HA form-action spinner remains. Errors now explain an uncertain
position reference instead of only returning numeric command result 3. After an
encoder-stall fault, clearing the fault still does not manufacture a reference;
recalibration is required if the Position referenced diagnostic is Off.


### 0.3.3: battery savings and integration icon

Install HACS integration **0.3.3**, restart Home Assistant, then use the Firmware
update entity to install **0.3.3** over BLE. The HACS update is needed this time
because the old integration polls the motor every 30 seconds. Future firmware-only
releases continue to use the existing GitHub manifest/update entity.

The integration includes its own blind icon for light and dark themes.

Idle battery sampling/status is six-hourly; state changes still push immediately.
Movement retains 10 ms control and approximately four position updates/second.
Stop is processed directly on command arrival. The connection is retained, using
requested 100–200 ms idle / 30–50 ms active intervals with no peripheral latency.
Advertising slows after a minute when disconnected. Pairing and charger inputs
wake by interrupt; LED timing and battery ADC use scheduled wakeups. The encoder
is powered and interrupt-enabled only during movement/coast. See PROTOCOL.md.

No current measurement is available. Track resting battery voltage over several
days with charging disconnected and note motor use. Cell capacity and voltage
trend can give a rough discharge estimate, but the nonlinear curve and motor
energy mean this is not a precise idle-current measurement. Saved configuration
and calibration survive this application-only OTA update.
