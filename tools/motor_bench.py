#!/usr/bin/env python3
"""RAM-only speed experiment for the identified HD0393 BGM13P bench motor.

Uses the original 00.02.31 firmware's motor prepare/start/stop functions.
Ramps from the stock 50% initial duty to full drive, then holds --duty
for 20 million CPU cycles (about 0.5-1 second), stops and resets.
No erase/program commands. Requires the matching original flash backup.
This bypasses application position/stall checks: use an unloaded bench motor.
OpenOCD is required; no Python packages are needed.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

CODE_END = 0x7F000
CODE_SHA256 = "8ec4db398157ac7f8b1277c663dd492e1295cac99e4597a5f486ca3677d0cd70"
PARAMETER_OFFSET = 212
TEMPLATE = bytes.fromhex(
    "72b62b48016841f0807101602948016841f0010101600120274ca047274c2568"
    "274e2068401bb042fbd3264ca047264c264d2e68264f002080468346d4f86c90"
    "d4f81ca01af1010a2868801bb84229d2bbf1000ff8d1e068c007f5d501206061"
    "18f10108b8f1280feed30020804619f10109c4f86c90c4f87c90d145e4d31548"
    "642807d0baf1010101fb00f06421b0fbf1f000e05046e066e067814601208346"
    "2e68d1e700200c4ca04700befee700bffced00e0001000e0f5050100041000e0"
    "801a06001907010000800140041000e0002d310175005a5af5050100"
)

def payload(duty):
    if not 0 <= duty <= 100:
        raise ValueError("Duty must be 0..100")
    data = bytearray(TEMPLATE)
    if struct.unpack_from("<I", data, PARAMETER_OFFSET)[0] != 0x5A5A0075:
        raise ValueError("Payload parameter marker damaged")
    struct.pack_into("<I", data, PARAMETER_OFFSET, duty)
    return bytes(data)


def session(reference, image):
    # Paths are generated under TemporaryDirectory, not user-interpolated Tcl.
    return f"""
init
set failed 0
if {{[catch {{
    halt
    verify_image {{{reference}}} 0 bin
    load_image {{{image}}} 0x2000f000 bin
    reg msp 0x20010000
    reg psp 0x20010000
    reg control 0
    reg primask 1
    reg xpsr 0x01000000
    resume 0x2000f000
    wait_halt 5000
    set result [get_reg {{r9 r11}}]
    puts "Final compare and hold-phase flag: $result"
    if {{[dict get $result r11] != 1}} {{error "Startup ramp did not finish"}}
    puts "BENCH PASS: pulse finished and stop routine returned"
}} problem]}} {{
    puts "BENCH ERROR: $problem"
    set failed 1
}}
if {{[catch {{reset run}} problem]}} {{
    puts "RESET ERROR: $problem"
    set failed 1
}}
if {{$failed}} {{shutdown error}} else {{shutdown}}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duty", type=int, required=True,
                        help="PWM duty after the startup ramp, 0..100")
    parser.add_argument("--reference", type=Path,
                        default=Path.cwd() / "hd-blind-original.bin")
    args = parser.parse_args()
    if not 0 <= args.duty <= 100:
        parser.error("--duty must be 0..100")
    try:
        original = args.reference.read_bytes()
    except OSError as exc:
        parser.error(str(exc))
    if len(original) != 0x80000 or hashlib.sha256(original[:CODE_END]).hexdigest() != CODE_SHA256:
        parser.error("Backup is not the identified 00.02.31 firmware; no test performed")
    executable = shutil.which("openocd")
    if not executable:
        parser.error("Install OpenOCD first")
    existing = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True)
    if existing.returncode == 0:
        parser.error("Another OpenOCD is running; stop it before testing")
    print(f"RAM-only test: factory startup ramp, then {args.duty}% PWM, stop and reset.", flush=True)
    with tempfile.TemporaryDirectory(prefix="hd-bench-") as temp:
        directory = Path(temp)
        reference = directory / "reference.bin"
        image = directory / "pulse.bin"
        script = directory / "test.cfg"
        reference.write_bytes(original[:CODE_END])
        image.write_bytes(payload(args.duty))
        script.write_text(session(reference, image))
        command = [executable,
                   "-c", "gdb port disabled",
                   "-c", "tcl port disabled",
                   "-c", "telnet port disabled",
                   "-f", "interface/raspberrypi-native.cfg",
                   "-c", "transport select swd",
                   "-c", "adapter gpio srst 24",
                   "-f", "target/efm32.cfg",
                   "-c", "adapter speed 100",
                   "-c", "reset_config srst_only srst_open_drain",
                   "-f", str(script)]
        return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
