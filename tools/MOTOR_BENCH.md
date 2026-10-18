# HD0393 RAM-only motor bench test

This tool targets the analyzed BGM13P22 / EFR32BG13P spare motor running factory
firmware 00.02.31. It is separate from the ESPHome BLE integration. The complete
flash backup stays private; its code-region SHA-256 guards the fixed function addresses.

## Hardware

Raspberry Pi 3 Model B, OpenOCD 0.12 development snapshot, short wires:

| Pi physical pin | Board pad identified by continuity |
| --- | --- |
| 23 / GPIO11 | Module pin 21 / PF0 / SWCLK |
| 24 / GPIO8 | Module pin 22 / PF1 / SWDIO |
| 18 / GPIO24 | R, module pin 30 / RESETn |
| 20 / GND | GND2 |

The board uses its battery. Do not connect Pi power rails to it. Measured board
logic supply: 3.308 V. The six-pad programming area has no confirmed ground pad.
Earlier proposed backside test-point numbers 17 and 6 were retracted.

## Run

From the directory containing the matching `hd-blind-original.bin` backup:

```sh
sudo python3 motor_bench.py --duty 75
```

`--reference /path/to/hd-blind-original.bin` can select a different backup path.
Stop existing OpenOCD processes before running. OpenOCD servers are disabled.

The script verifies the chip code against the original below 0x7f000, loads a
220-byte Thumb-2 program at 0x2000f000, takes over the core with interrupts
masked, and gives it stack space at the top of RAM. It calls the original motor
prepare/start functions, reproduces the original timer-overflow ramp from
compare 60 to 121 (TOP is 120 on the tested unit), then changes to the requested
PWM duty. The hold is 20 million CPU cycles, approximately 0.5-1 second depending
on the core clock. It then calls the original stop routine, breaks, and resets
the board to reload the factory application. No flash erase/program commands
are used. Volatile application state is discarded on reset.

A `BENCH PASS` message means the payload reached its stop and hold phase; the
operator must still observe actual movement. The factory startup ramp has moved
the motor on hardware. Reduced-duty holding is experimental. This test bypasses
normal position/current/stall handling and is intended only for the unloaded spare.
PWM duty does not imply the same percentage of mechanical speed.

## Reverse-engineering evidence

- Correct module identification is BGM13P22, **not BGM113**.
- Application vector table is at 0x9000; TIMER0 ISR is at 0x10a7c.
- 0x105f4: motor preparation/disable routine, argument 1 enables, 0 stops/disables.
- 0x10718: proven direction-start wrapper; 0x10744 is the other direction path.
- 0x10088: shared PWM setup routine.
- TIMER0 is at 0x40018000. Initial TOP=120, CC0/CC1 buffer=60.
- Factory ISR increments the compare value by 1 every 40 overflows, up to 121.
- Merely holding the initial PWM setting did not move this bench motor; reproducing
  the ramp did. The exact low-duty starting threshold is not yet established.
- Recalibration changed 46 bytes at 0x7f3d0..0x7f423; bytes below 0x7f000 stayed identical.
- Suspected motor driver marking is DRV8850; not yet positively confirmed.

`motor_bench_payload.s` is reviewable source for the embedded payload. The duty
literal 0x5a5a0075 at byte offset 212 is patched by the Python tool. Keystone can
assemble it at 0x2000f000 (Thumb-2); Keystone is not needed on the Pi.

Payload flow is tested under Unicorn with the original flash routines stubbed.
The tests cover ramp progression, requested hold duty, stopping, and a missing
overflow flag. They do not validate the motor hardware or stock function internals.
