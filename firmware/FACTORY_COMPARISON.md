# Factory firmware comparison

This is a comparison from the privately retained REV.J factory firmware backup,
not a requirement to reproduce its controller. Original binaries, pairing data
and disassembly are deliberately not included. Evidence is from static analysis;
physical timing/braking measurements have not been made.

| Behavior | Factory implementation found | Custom 0.3.0 |
| --- | --- | --- |
| Encoder position | Signed directional increment/decrement in callback 0x187A8; current count at record offset +0x14 | Upper zero; downward counts positive; encoder IRQ also cuts drive at a target |
| Calibration | Upper capture resets current/top count to zero (0x1843C); lower capture stores nonnegative travel (0x184B8) | Guided upper/lower flow in HA with locally timed jogs |
| Positions | Explicit CurrentPOS, Bottom, Top, Individual, Group and Schedule fields identified by debug print routine 0x171C4 | Current/target counts, calibrated range, HA openness percentage |
| Motor start | PWM configuration helper 0x10088; movement entry points 0x10718/0x10744 request 50% initial drive; timer ISR 0x10A7C increases compare toward full drive | Independent up/down cruise speeds, startup ramp, independent near-target speeds |
| Target stop | Main loop compares signed current count with target and a six-count allowance (0x17B36/0x181CE) | Velocity-dependent slowdown window and learned per-direction coast allowance, bounded to 16 counts |
| Braking | Stop sequence calls 0x10770 first with 0, then 1: PWM braking path followed by static bridge state, before later disable | Drive disabled, coast counted for 300 ms; no factory brake timing copied |
| Flash | 34-byte PS record key 0x4002: 30 data bytes plus integrity field. Save routine 0x172B8, load at startup 0x17770, compare/save wrapper 0x172F0 | Separate versioned NVM3 record; dirty before movement, final count after settling |
| Save triggers traced | Calibration/favorite updates, and explicit SHADETSKPREPEM4 path 0x181A2 | Each movement start/settled stop; no per-pulse flash writes |
| Faults | Motor-current/stall and faulty-encoder handling identified in main loop and debug labels | Run timeout, encoder-progress watchdog, NVM-write fault; no motor-current sensing added in this release |

The target/braking path examined is a state machine with count comparisons and
PWM ramping. No proportional/integral/derivative feedback calculation was found
there; this does not prove that every unrelated firmware path lacks one. A save
before orderly deep sleep does not establish accurate recovery after sudden
power removal mid-motion. The original also contains backdrive handling, which
has not been fully traced and is not implemented in the custom controller.

The custom stop accuracy, near-target PWM under load, and 300 ms coast interval
still require bench validation. This comparison does not establish measured
accuracy for either firmware.
