#!/usr/bin/env python3
"""Install the BG13 development second stage and named firmware over Pi GPIO SWD.

Only the second-stage bootloader is replaced. The 2 KiB factory first stage,
user data, lock bits and device calibration are never erased by this script.
"""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

FACTORY_BOOT_SHA='94b85379f744cebceb22fe6b4f8bf5e9b3e15ce971233d036b496adaf6886f06'
ROOT='https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/{ref}/firmware/releases/'

def sha(data):return hashlib.sha256(data).hexdigest()

def download(ref,name):
    root=ROOT.format(ref=ref)
    with urllib.request.urlopen(root+name+'.json',timeout=30) as response:
        meta=json.load(response)
    with urllib.request.urlopen(root+name+'.bin.gz.b64',timeout=30) as response:
        data=gzip.decompress(base64.decodebytes(response.read()))
    if len(data)!=meta['bytes'] or sha(data)!=meta['sha256']:
        raise RuntimeError(f'Checksum mismatch: {name}')
    return data

def openocd(commands):
    args=['openocd','-c','gdb port disabled','-c','tcl port disabled',
          '-c','telnet port disabled','-f','interface/raspberrypi-native.cfg',
          '-c','transport select swd','-c','adapter gpio srst 24',
          '-f','target/efm32.cfg','-c','adapter speed 100',
          '-c','reset_config srst_only srst_open_drain',
          '-c','init; if {[catch {'+commands+'} problem]} {puts "INSTALL ERROR: $problem"; shutdown error} else {shutdown}']
    result=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    print(result.stdout,flush=True)
    if result.returncode or 'INSTALL ERROR:' in result.stdout:
        raise RuntimeError('OpenOCD did not finish successfully; do not reset after a write failure')
    return result.stdout

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='main')
    parser.add_argument('--backup',type=Path,default=Path('hd-bootloader.bin'))
    parser.add_argument('--install',action='store_true',help='Write verified bootloader and firmware')
    args=parser.parse_args()
    original=args.backup.read_bytes()
    if len(original)!=16384 or sha(original)!=FACTORY_BOOT_SHA:
        parser.error('Expected the verified factory hd-bootloader.bin backup')
    if subprocess.run(['pgrep','-x','openocd'],stdout=subprocess.DEVNULL).returncode==0:
        parser.error('Another OpenOCD is running; stop it first')
    images={name:download(args.ref,name) for name in
            ['hd-bootloader-stage2','hd-bootloader-writer','hd-blind-bench']}
    if len(images['hd-bootloader-stage2'])!=0x3800:
        parser.error('Second stage must occupy exactly seven pages')
    print('Factory backup and all three downloads verified.',flush=True)
    if not args.install:
        print('Download/check only. Run with --install to write the test motor.');return
    with tempfile.TemporaryDirectory(prefix='hd-blind-') as directory:
        work=Path(directory)
        for name,data in images.items():(work/(name+'.bin')).write_bytes(data)
        current=work/'current-bootloader.bin'
        # Remain halted between preflight and install: RAM will be overwritten.
        output=openocd(f'''halt
          mww 0x4400A09C 0x8000
          puts "BOOT WRITE PROTECTION: [read_memory 0x400E0090 32 1]"
          if {{([lindex [read_memory 0x400E0090 32 1] 0] & 2) != 0}} {{error "Bootloader write-protected; no flash was changed"}}
          dump_image {current} 0x0FE10000 0x4000
          puts "PREFLIGHT COMPLETE"
        ''')
        if 'PREFLIGHT COMPLETE' not in output:raise RuntimeError('Preflight incomplete')
        if current.read_bytes()!=original:
            raise RuntimeError('Current bootloader differs from backup; no flash was changed')
        output=openocd(f'''halt
          flash probe 0
          flash write_image erase {work/'hd-blind-bench.bin'} 0 bin
          verify_image {work/'hd-blind-bench.bin'} 0 bin
          load_image {work/'hd-bootloader-stage2.bin'} 0x20000000 bin
          load_image {work/'hd-bootloader-writer.bin'} 0x20008000 bin
          mww 0xE000E010 0
          mww 0xE000E180 0xFFFFFFFF 2
          mww 0xE000E280 0xFFFFFFFF 2
          reg msp 0x20010000
          reg control 0
          reg basepri 0
          reg faultmask 0
          reg primask 1
          reg xpsr 0x01000000
          resume 0x20008000
          wait_halt 15000
          puts "WRITER RESULT: [read_memory 0x20007000 32 1]"
          if {{[lindex [read_memory 0x20007000 32 1] 0] != 0x4844424c}} {{error "RAM writer did not verify all pages"}}
          verify_image {work/'hd-bootloader-stage2.bin'} 0x0FE10800 bin
          dump_image {work/'first-stage.bin'} 0x0FE10000 0x800
          puts "SECOND STAGE VERIFIED"
        ''')
        if 'SECOND STAGE VERIFIED' not in output:raise RuntimeError('Verification incomplete')
        if (work/'first-stage.bin').read_bytes()!=original[:0x800]:
            raise RuntimeError('First-stage mismatch; target left halted')
        print('First stage unchanged; second stage and named firmware verified.',flush=True)
        openocd('reset run; puts "RESET COMPLETE";')
        print('Installed. Scan for HD Blind plus the last four MAC digits.')

if __name__=='__main__':main()
