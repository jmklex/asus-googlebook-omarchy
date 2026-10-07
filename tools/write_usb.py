#!/usr/bin/env python3
"""Write a validated image to an explicitly chosen external USB. Dry run by default."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import require, require_regular, sha256
from lapis.gpt import read_gpt, tables


def inspect(device):
    if platform.system() == 'Darwin':
        require(re.fullmatch(r'/dev/disk\d+', str(device)), 'Use a whole /dev/diskN device')
        info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(device)]))
        require(info.get('Whole') is True and info.get('Internal') is False, 'Refuse internal disks and partitions')
        require(info.get('BusProtocol') == 'USB' and info.get('Writable') is True, 'Require a writable USB disk')
        require(info.get('DeviceBlockSize') == 512, 'Require 512-byte logical sectors')
        return dict(device=str(device), bytes=info['TotalSize'], model=info.get('MediaName', ''),
                    identity=info.get('DeviceTreePath', ''), raw='/dev/r' + device.name)
    require(platform.system() == 'Linux', 'Supported writers: macOS and Linux')
    require(re.fullmatch(r'/dev/sd[a-z]+', str(device)), 'Use a whole USB /dev/sdX disk')
    info = json.loads(subprocess.check_output(['lsblk', '--json', '--bytes', '--nodeps', '-o', 'PATH,TYPE,TRAN,RO,SIZE,LOG-SEC,MODEL,SERIAL', str(device)]))['blockdevices']
    require(len(info) == 1, 'Ambiguous disk')
    d = info[0]
    require(d['type'] == 'disk' and d['tran'] == 'usb' and not d['ro'], 'Require a writable whole USB disk')
    require(d['log-sec'] == 512, 'Require 512-byte logical sectors')
    root = subprocess.check_output(['findmnt', '-no', 'SOURCE', '/'], text=True).strip().split('[')[0]
    if root.startswith('/dev/'):
        parents = subprocess.check_output(['lsblk', '-s', '-n', '-r', '-o', 'PATH', root], text=True).splitlines()
        require(str(device) not in parents, 'Refuse the running system disk')
    return dict(device=str(device), bytes=d['size'], model=d.get('model'), identity=d.get('serial'), raw=str(device))


def resized_tables(gpt, disk_bytes):
    require(disk_bytes >= gpt.disk_bytes and disk_bytes % 512 == 0, 'USB too small or not sector aligned')
    header = list(gpt.header)
    header[6] = disk_bytes // 512 - 1
    header[8] = header[6] - 33
    mbr = bytearray(gpt.primary[:512])
    import struct
    struct.pack_into('<I', mbr, 458, min(header[6], 0xffffffff))
    return tables(header, gpt.entries, mbr)


def unmount(device):
    if platform.system() == 'Darwin':
        subprocess.run(['diskutil', 'unmountDisk', str(device)], check=True)
    else:
        rows = subprocess.check_output(['lsblk', '-n', '-r', '-o', 'PATH,MOUNTPOINT', str(device)], text=True).splitlines()
        for row in reversed(rows):
            fields = row.split(maxsplit=1)
            if len(fields) == 2:
                require(fields[1] != '[SWAP]', 'Deactivate USB swap explicitly before writing')
                subprocess.run(['umount', fields[0]], check=True)


def write_full(f, data):
    view = memoryview(data)
    while view:
        n = f.write(view)
        require(n is not None and n > 0, 'Short USB write')
        view = view[n:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--device', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    require_regular(args.image)
    require(args.image.stat().st_size > 1024**3, 'Image unexpectedly small')
    manifest = json.loads(args.image.with_suffix('.manifest.json').read_text())
    require(manifest['size'] == args.image.stat().st_size and manifest['sha256'] == sha256(args.image), 'Image hash differs from builder manifest')
    with args.image.open('rb') as f:
        gpt = read_gpt(f, args.image.stat().st_size)
    info = inspect(args.device)
    image_fs = subprocess.check_output(['df', '-P', str(args.image)], text=True).splitlines()[-1].split()[0]
    require(not re.fullmatch(re.escape(str(args.device)) + r'(?:s\d+|\d+)?', image_fs), 'Image file is on the USB about to be erased')
    primary, secondary = resized_tables(gpt, info['bytes'])
    print(json.dumps({k:v for k,v in info.items() if k != 'identity'}, indent=2))
    print('Image SHA256:', manifest['sha256'])
    if not args.apply:
        print('Dry run passed. No writes. Apply erases this entire USB.')
        return
    require(os.geteuid() == 0 and sys.stdin.isatty(), 'Run apply as root in an interactive terminal')
    require(input('Type ERASE ' + str(args.device) + ': ') == 'ERASE ' + str(args.device), 'Cancelled')
    require(inspect(args.device) == info, 'USB identity changed')
    unmount(args.device)
    require(inspect(args.device) == info, 'USB identity changed after unmount')
    with open(info['raw'], 'r+b', buffering=0) as dest, args.image.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024**2), b''):
            write_full(dest, block)
        os.fsync(dest.fileno())
        dest.seek(0)
        h, remaining = hashlib.sha256(), manifest['size']
        while remaining:
            block = dest.read(min(remaining, 4 * 1024**2))
            require(block, 'Short USB read-back')
            h.update(block); remaining -= len(block)
        require(h.hexdigest() == manifest['sha256'], 'USB image read-back failed')
        dest.seek(info['bytes'] - len(secondary)); write_full(dest, secondary)
        dest.seek(0); write_full(dest, primary)
        os.fsync(dest.fileno())
        checked = read_gpt(dest, info['bytes'])
        require(checked.primary == primary and checked.secondary == secondary, 'Resized USB GPT read-back failed')
    print('Image and capacity-adjusted GPT verified. Eject the USB before unplugging.')


if __name__ == '__main__':
    main()
