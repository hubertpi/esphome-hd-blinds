#!/usr/bin/env python3
"""One-time SWD installation of OTA support; does not replace the bootloader."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='main')
    args=parser.parse_args()
    root=f'https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/{args.ref}/firmware/releases/'
    with urllib.request.urlopen(root+'hd-ota-bootstrap.json',timeout=30) as response:
        meta=json.load(response)
    with urllib.request.urlopen(root+'hd-ota-bootstrap.gz.b64',timeout=30) as response:
        image=gzip.decompress(base64.decodebytes(response.read()))
    if len(image)!=meta['bytes'] or hashlib.sha256(image).hexdigest()!=meta['sha256']:
        raise RuntimeError('Firmware checksum mismatch')
    if subprocess.run(['pgrep','-x','openocd'],stdout=subprocess.DEVNULL).returncode==0:
        raise RuntimeError('Another OpenOCD is running')
    with tempfile.TemporaryDirectory(prefix='hd-ota-') as directory:
        work=Path(directory)
        (work/'firmware.bin').write_bytes(image)
        commands=f'''init
        if {{[catch {{
          halt
          mww 0x4400A09C 0x8000
          mww 0xE000ED94 0
          dump_image {work/'boot-before.bin'} 0x0FE10000 0x4000
          flash probe 0
          flash write_image erase {work/'firmware.bin'} 0 bin
          verify_image {work/'firmware.bin'} 0 bin
          dump_image {work/'boot-after.bin'} 0x0FE10000 0x4000
          puts "OTA BOOTSTRAP VERIFIED"
          reset run
        }} problem]}} {{puts "FLASH ERROR: $problem"; shutdown error}} else {{shutdown}}
        '''
        cmd=['openocd','-c','gdb port disabled','-c','tcl port disabled',
             '-c','telnet port disabled','-f','interface/raspberrypi-native.cfg',
             '-c','transport select swd','-c','adapter gpio srst 24',
             '-f','target/efm32.cfg','-c','adapter speed 100',
             '-c','reset_config srst_only srst_open_drain','-c',commands]
        result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        print(result.stdout)
        if result.returncode or 'FLASH ERROR:' in result.stdout or 'OTA BOOTSTRAP VERIFIED' not in result.stdout:
            raise RuntimeError('Flash did not complete; keep SWD connected')
        if (work/'boot-before.bin').read_bytes()!=(work/'boot-after.bin').read_bytes():
            raise RuntimeError('Unexpected bootloader difference')
    print('OTA bootstrap 0.2.0 installed; bootloader unchanged. Battery feature awaits the wireless 0.2.1 update.')

if __name__=='__main__':main()
