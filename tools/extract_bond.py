#!/usr/bin/env python3
"""Extract one user's own HDC bond from an Android bugreport, to a local YAML file.

Never upload the output or the bugreport to a public repository. HCI byte order
is preserved for LTK/RAND; EDIV is decoded as a little-endian integer.
"""
import argparse
import re
import struct
import zipfile
from pathlib import Path


def address(raw):
    return ':'.join(f'{x:02X}' for x in raw[::-1])


def parse_snoop(data, target):
    if data[:8] != b'btsnoop\0' or len(data) < 16:
        raise ValueError('Not a btsnoop file')
    version, kind = struct.unpack_from('>II', data, 8)
    if version != 1 or kind != 1002:
        raise ValueError('Expected btsnoop v1 HCI UART packets')
    active, pending, modes = {}, {}, {}
    result, phone = None, None
    offset = 16
    while offset + 24 <= len(data):
        _, size, flags, _, timestamp = struct.unpack_from('>IIIIQ', data, offset)
        offset += 24
        packet = data[offset:offset + size]
        offset += size
        if len(packet) != size:
            raise ValueError('Truncated btsnoop record')
        # LE Connection Complete / LE Enhanced Connection Complete
        if len(packet) >= 15 and packet[0:2] == b'\x04\x3e' and packet[3] in (1, 10) and packet[4] == 0:
            handle = struct.unpack_from('<H', packet, 5)[0]
            active[handle] = address(packet[9:15])
            pending.pop(handle, None)
        # LE Start Encryption command: LTK is passed from host to controller.
        if len(packet) == 32 and packet[:3] == b'\x01\x19\x20':
            handle = struct.unpack_from('<H', packet, 4)[0]
            if active.get(handle) == target:
                pending[handle] = {
                    'ltk': packet[16:32].hex(), 'rand': packet[6:14].hex(),
                    'ediv': struct.unpack_from('<H', packet, 14)[0],
                    'timestamp': timestamp,
                }
        # Only return keys followed by a successful Encryption Change event.
        if len(packet) >= 7 and packet[0] == 4 and packet[1] in (8, 0x59):
            handle = struct.unpack_from('<H', packet, 4)[0]
            if packet[3] == 0 and packet[6] != 0 and handle in pending:
                candidate = dict(pending[handle])
                candidate['auth_mode'] = modes.get(target)
                if result is None or candidate['timestamp'] > result['timestamp']:
                    result = candidate
        # SMP pairing metadata and the phone's public identity address.
        if len(packet) >= 10 and packet[0] == 2:
            handle = struct.unpack_from('<H', packet, 1)[0] & 0xFFF
            if active.get(handle) == target and struct.unpack_from('<H', packet, 7)[0] == 6:
                smp = packet[9:]
                if len(smp) >= 7 and smp[0] == 2:
                    modes[target] = smp[3] & 0x0D
                if len(smp) == 8 and smp[0] == 9 and not flags & 1:
                    if smp[1] != 0:
                        raise ValueError('Phone identity is random; this component requires a public identity')
                    phone = address(smp[2:8])
        if len(packet) >= 7 and packet[:2] == b'\x04\x05':
            handle = struct.unpack_from('<H', packet, 4)[0]
            active.pop(handle, None)
            pending.pop(handle, None)
    return result, phone


def extract(report, target):
    records, phone, phone_name = [], None, None
    with zipfile.ZipFile(report) as z:
        for name in z.namelist():
            if name.endswith('btsnoop_hci.log') or name.endswith('btsnoop_hci.log.last'):
                result, identity = parse_snoop(z.read(name), target)
                if result:
                    records.append(result)
                if identity:
                    phone = identity
        if 'dumpstate.txt' in z.namelist():
            text = z.read('dumpstate.txt').decode('utf-8', errors='replace')
            match = re.search(r'AdapterProperties\s*\n\s+Name: ([^\n]+)', text)
            if match:
                phone_name = match.group(1).strip()
    if not records:
        raise ValueError('No successfully encrypted connection for this blind was found')
    return max(records, key=lambda x: x['timestamp']), phone, phone_name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bugreport', type=Path)
    p.add_argument('--blind', required=True)
    p.add_argument('--prefix', default='hd0352')
    p.add_argument('--phone-mac', help='Public identity MAC if the capture omitted identity exchange')
    p.add_argument('--phone-name', help='Bluetooth name if absent from the report')
    p.add_argument('--auth-mode', type=int, choices=[1, 5, 9, 13])
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', args.prefix):
        p.error('Invalid YAML secret prefix')
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', args.blind):
        p.error('Invalid blind MAC')
    key, phone, name = extract(args.bugreport, args.blind.upper())
    phone, name = args.phone_mac or phone, args.phone_name or name
    mode = args.auth_mode or key['auth_mode']
    if not phone or not name or mode is None:
        p.error('Missing phone identity/name or negotiated mode; supply the corresponding option')
    import json  # JSON double-quoted strings are also valid YAML strings.
    text = '# PRIVATE: append locally to ESPHome secrets.yaml; never commit this file.\n'
    text += f'hd_phone_mac: {json.dumps(phone)}\nhd_phone_name: {json.dumps(name)}\n'
    for suffix in ('ltk', 'rand', 'ediv'):
        text += f'{args.prefix}_{suffix}: {json.dumps(key[suffix])}\n'
    text += f'{args.prefix}_auth_mode: {mode}\n'
    # Do not overwrite an existing secrets file or change its other contents.
    with args.out.open('x', encoding='utf-8') as f:
        f.write(text)
    args.out.chmod(0o600)
    print(f'Wrote private bond settings to {args.out}; key values were not printed.')


if __name__ == '__main__':
    main()
