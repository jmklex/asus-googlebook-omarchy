#!/usr/bin/env python3
"""Build a credential-free live image from the exact Omarchy 4.0.4 ISO."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, ISO_SHA256, XE_PARAMETERS, new_regular_output, require, run, save_json, sha256
from lapis.boot import build_set
from lapis.cpio import archive, find_member
from lapis.gpt import ENTRY, read_gpt, tables
from tools.fetch_sources import SOURCES


def payload(vendor):
    files = {}

    def add(name, data, mode=0o100644):
        pieces = name.split('/')
        for i in range(1, len(pieces)):
            files.setdefault('/'.join(pieces[:i]), (0o040755, b''))
        files[name] = (mode, data)

    # Deliberate allowlist. Never sweep a workspace or copy a live system.
    for folder in ('lapis', 'tools', 'assets', 'docs'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                require(path.suffix not in ('.pem', '.psk', '.img', '.bin'), 'Unexpected private/build file in sources')
                add('lapis-kit/' + str(path.relative_to(ROOT)), path.read_bytes(), 0o100755 if path.suffix in ('.py', '.sh') else 0o100644)
    for name in ('LICENSE', 'NOTICE.md', 'README.md'):
        add('lapis-kit/' + name, (ROOT / name).read_bytes())
    for name, (_, revision) in SOURCES.items():
        src = vendor / name
        got = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip()
        require(got == revision, f'Unexpected {name} revision')
        dirty = subprocess.check_output(['git', '-C', str(src), 'status', '--porcelain', '--untracked-files=no'], text=True)
        require(not dirty, f'Modified {name} source')
        tracked = subprocess.check_output(['git', '-C', str(src), 'ls-files', '-z']).decode().split('\0')
        for rel in filter(None, tracked):
            path = src / rel
            if path.suffix in ('.pem', '.key', '.p12', '.pfx'):
                continue  # Upstream test signing keys are not needed in the live kit.
            if ('test' in path.parts or 'tests' in path.parts or 'testdata' in path.parts) and path.name != 'Makefile.inc':
                continue
            if path.is_symlink():
                # These build tools do not need symlinked test fixtures.
                continue
            if path.is_file():
                add(f'lapis-kit/vendor/{name}/{rel}', path.read_bytes(), 0o100755 if os.access(path, os.X_OK) else 0o100644)
        add(f'lapis-kit/vendor/{name}/.source-revision', (revision + '\n').encode())
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--vendor', type=Path, default=ROOT / 'vendor')
    args = p.parse_args()
    iso = args.iso.resolve()
    require(iso.is_file(), 'Missing ISO')
    require(sha256(iso) == ISO_SHA256, 'Wrong ISO checksum; no unverified newer ISO fallback')
    image = new_regular_output(args.output).resolve()
    work = image.with_suffix('.build')
    require(not work.exists(), 'Build directory already exists')
    work.mkdir(mode=0o700)
    for name in ('vmlinuz-linux-t2', 'initramfs-linux-t2.img'):
        with (work / name).open('wb') as f:
            run(['bsdtar', '-xOf', iso, 'arch/boot/x86_64/' + name], stdout=f)
    with iso.open('rb') as f:
        gpt = read_gpt(f, iso.stat().st_size, hybrid_iso=True)
    iso_part = uuid.uuid4()
    cmdline = (f'archisobasedir=arch archisodevice=/dev/disk/by-partuuid/{iso_part} '
               'modprobe.blacklist=xe initramfs_async=0 console=tty0 loglevel=4 '
               'log_buf_len=4M printk.time=1 panic=30 fbcon=nodefer disablehooks=plymouth '
               'plymouth.enable=0 rd.plymouth=0 cow_spacesize=3G asus.live_desktop=1 ' +
               ' '.join('xe.' + k + '=' + v for k, v in XE_PARAMETERS.items()))
    initrd = (work / 'initramfs-linux-t2.img').read_bytes()
    config = find_member(initrd, 'config', lambda data: subprocess.check_output(['zstd', '-d', '-c'], input=data)).decode()
    config = config.replace(' plymouth', '').replace('="plymouth"', '=""').replace('LATEHOOKS="', 'LATEHOOKS="lapis ')
    files = payload(args.vendor.resolve())
    files['config'] = (0o100644, config.encode())
    files['hooks/lapis'] = (0o100755, (ROOT / 'assets/live/latehook.sh').read_bytes())
    combined = work / 'live-initramfs.img'
    combined.write_bytes(initrd + bytes((-len(initrd)) % 4) + archive(files))
    boot = work / 'boot'
    manifest = build_set(work / 'vmlinuz-linux-t2', combined, cmdline, boot, args.vendor.resolve())
    # A cloned/copied regular file, never a device. Source ISO is opened read-only.
    if platform.system() == 'Darwin':
        run(['/bin/cp', '-c', iso, image])
    else:
        require(shutil.disk_usage(image.parent).free > iso.stat().st_size + 1024**3, 'Need at least ISO size + 1 GiB free')
        shutil.copyfile(iso, image)
    entries = gpt.entries[:128*128]
    entries[16:32] = iso_part.bytes_le
    entries[128:256] = bytes(128)  # Remove the stock ISO's overlapping hybrid alias.
    h = list(gpt.header)
    h[11] = 128
    items = [(x['name'], boot / (x['name'] + '.img'), x['size']) for x in manifest['images']]
    misc = work / 'misc.img'
    misc.write_bytes(bytes(1048576))
    items.append(('misc', misc, 1048576))
    cursor = ((iso.stat().st_size + 1048575) // 1048576) * 1048576
    layout = []
    with image.open('r+b') as f:
        for index, (name, source, size) in enumerate(items, 3):
            typ = '88434509-d9d1-487d-b82c-15ef964cbd4b' if name == 'vbmeta_a' else '0fc63daf-8483-4772-8e79-3d69d8477de4'
            attrs = (15 << 48) | (1 << 56) if name == 'vbmeta_a' else 0
            entry = ENTRY.pack(uuid.UUID(typ).bytes_le, uuid.uuid4().bytes_le, cursor//512, (cursor+size)//512-1, attrs, name.encode('utf-16-le'))
            entries[index*128:(index+1)*128] = entry
            f.seek(cursor)
            with source.open('rb') as src:
                shutil.copyfileobj(src, f, 1024*1024)
            layout.append(dict(name=name, offset=cursor, size=size))
            cursor += size
        h[6], h[8] = cursor//512 + 32, cursor//512 - 1
        mbr = bytearray(gpt.primary[:512])
        mbr[446:510] = bytes(64)
        mbr[450] = 0xee
        struct.pack_into('<II', mbr, 454, 1, min(h[6], 0xffffffff))
        primary, secondary = tables(h, entries, mbr)
        f.truncate((h[6]+1)*512)
        f.seek(0)
        f.write(primary)
        f.seek(cursor)
        f.write(secondary)
        f.flush()
        os.fsync(f.fileno())
    with image.open('rb') as f:
        checked = read_gpt(f, image.stat().st_size)
    report = dict(image=image.name, sha256=sha256(image), size=image.stat().st_size,
                  iso_sha256=ISO_SHA256, cmdline=cmdline, android_partitions=layout,
                  included_credentials=False, internal_disk_writes=False,
                  status='Built and structurally checked; test this image on hardware before installing')
    save_json(image.with_suffix('.manifest.json'), report, 0o644)
    image.with_suffix('.sha256').write_text(report['sha256'] + '  ' + image.name + '\n')
    print('Created', image, '\nSHA256', report['sha256'])


if __name__ == '__main__':
    main()
