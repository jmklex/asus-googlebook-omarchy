#!/usr/bin/env python3
"""Staged Lapis installation. Read docs/install.md before any apply command."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, KERNEL_RELEASE, KERNEL_SHA256, XE_PARAMETERS, output, read_json, require, run, save_json, sha256
from lapis.gpt import read_gpt
from lapis.boot import build_set

NAMES = ('boot_a', 'init_boot_a', 'vendor_boot_a', 'vbmeta_a')
STATE = Path('/run/lapis-install')
TARGET = Path('/mnt')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_profile(gpt):
    profile = read_json(ROOT / 'assets/lapis-512gb.json')
    require(gpt.disk_bytes == profile['disk_bytes'], 'Only the tested 512 GB layout is supported')
    actual = [{k: p[k] for k in ('index', 'name', 'start_lba', 'size', 'type_guid')} for p in gpt.partitions()]
    require(actual == profile['partitions'], 'Factory partition layout differs; stop and report sanitized geometry')
    parts = {p['name']: p for p in gpt.partitions()}
    a, b = (parts['vbmeta_' + s]['attributes'] for s in ('a', 'b'))
    require((a >> 48 & 15) > (b >> 48 & 15) and (a >> 56 & 1), 'Slot A must be the successful preferred slot')


def hardware(device, *, ac=False):
    require(os.geteuid() == 0 and sys.platform == 'linux', 'Run as root on the live Googlebook')
    require(Path('/sys/class/dmi/id/sys_vendor').read_text().strip() == 'Google', 'Wrong DMI vendor')
    require(Path('/sys/class/dmi/id/product_name').read_text().strip() == 'Lapis', 'Wrong board')
    require(Path('/sys/bus/pci/devices/0000:00:02.0/device').read_text().strip() == '0xb090', 'Wrong graphics device')
    require(Path('/sys/bus/pci/devices/0000:00:1f.3/subsystem_device').read_text().strip() == '0x15e4', 'Wrong audio subsystem')
    require(output(['uname', '-r']) == KERNEL_RELEASE, 'Wrong live kernel')
    require(output(['findmnt', '-no', 'FSTYPE', '/']) == 'overlay', 'Boot the live USB first')
    require('archisobasedir=arch' in Path('/proc/cmdline').read_text(), 'Not an Arch ISO live boot')
    require(re.fullmatch(r'/dev/nvme\d+n\d+', str(device)), 'Expected a whole internal NVMe disk')
    require(stat.S_ISBLK(device.stat().st_mode), 'Not a block device')
    node = Path('/sys/class/block') / device.name
    require((node / 'removable').read_text().strip() == '0', 'Disk must be internal')
    require(output(['blockdev', '--getss', device]) == '512', 'Only 512-byte logical sectors supported')
    if ac:
        supplies = Path('/sys/class/power_supply').glob('*/online')
        require(any(p.read_text().strip() == '1' for p in supplies), 'Connect AC power')
    size = int(output(['blockdev', '--getsize64', device]))
    with device.open('rb') as f:
        gpt = read_gpt(f, size)
    validate_profile(gpt)
    return gpt


def plan(args):
    require(not STATE.exists(), 'Existing install state: do not restart or reformat blindly')
    gpt = hardware(args.device)
    STATE.mkdir(mode=0o700)
    p = dict(device=str(args.device), disk_bytes=gpt.disk_bytes, disk_guid=gpt.guid,
             model=(Path('/sys/class/block') / args.device.name / 'device/model').read_text().strip(),
             gpt_sha256=digest(gpt.primary + gpt.secondary), partitions=gpt.partitions(), luks_uuid=str(uuid.uuid4()))
    save_json(STATE / 'plan.json', p)
    print(json.dumps(p, indent=2))
    print('Private plan saved. No disk changes. Next: backup to a separately mounted external drive.')


def current():
    p = read_json(STATE / 'plan.json')
    device = Path(p['device'])
    gpt = hardware(device, ac=True)
    require(gpt.guid == p['disk_guid'] and digest(gpt.primary + gpt.secondary) == p['gpt_sha256'], 'Disk/GPT changed since plan')
    require((Path('/sys/class/block') / device.name / 'device/model').read_text().strip() == p['model'], 'Disk identity changed')
    return p, device, gpt


def external(path, device):
    require(path.is_dir() and not path.is_symlink(), 'Backup parent must already exist on an external mounted filesystem')
    source = output(['findmnt', '-no', 'SOURCE', '--target', path]).split('[')[0]
    require(source.startswith('/dev/'), 'Backup must be on a mounted block filesystem, not RAM or a network share')
    ancestors = output(['lsblk', '-s', '-n', '-r', '-o', 'PATH', source]).splitlines()
    require(str(device) not in ancestors, 'Backup is on the disk being installed')
    if Path('/run/archiso/bootmnt').is_mount():
        require(os.stat(path).st_dev != os.stat('/run/archiso/bootmnt').st_dev, 'Do not use the live image filesystem for backups')
    require(os.stat(path).st_dev != os.stat('/').st_dev, 'Backup must not be in the live overlay')


def backup(args):
    p, device, gpt = current()
    dest = args.destination.resolve()
    external(dest.parent, device)
    require(not dest.exists(), 'Choose a new backup directory')
    required_bytes = sum(x['size'] for x in p['partitions'] if x['name'] not in ('userdata', 'super')) + 512 * 1024**2
    require(shutil.disk_usage(dest.parent).free > required_bytes, 'Insufficient external backup space')
    dest.mkdir(mode=0o700)
    records = []
    with device.open('rb') as f:
        for part in p['partitions']:
            if part['name'] in ('userdata', 'super'):
                continue
            f.seek(part['start_lba'] * 512)
            data = f.read(part['size'])
            require(len(data) == part['size'], 'Short disk read')
            path = dest / (part['name'] + '.img')
            path.write_bytes(data)
            path.chmod(0o600)
            records.append(dict(file=path.name, size=len(data), sha256=digest(data)))
    for name, data in [('gpt-primary.bin', gpt.primary), ('gpt-secondary.bin', gpt.secondary)]:
        (dest / name).write_bytes(data)
        (dest / name).chmod(0o600)
        records.append(dict(file=name, size=len(data), sha256=digest(data)))
    save_json(dest / 'plan.json', p)
    records.append(dict(file='plan.json', size=(dest / 'plan.json').stat().st_size, sha256=sha256(dest / 'plan.json')))
    save_json(dest / 'manifest.json', dict(records=records, disk_guid=gpt.guid))
    os.sync()
    verify_backup(dest)
    save_json(STATE / 'backup.json', dict(path=str(dest), manifest_sha256=sha256(dest / 'manifest.json')))
    print('Backup written and read back. It contains private device material; keep it offline. It does not contain your files or a complete factory OS.')


def verify_backup(dest):
    manifest = read_json(dest / 'manifest.json')
    for rec in manifest['records']:
        require(Path(rec['file']).name == rec['file'], 'Invalid backup filename')
        f = dest / rec['file']
        require(not f.is_symlink() and f.is_file() and f.stat().st_size == rec['size'] and sha256(f) == rec['sha256'], 'Backup verification failed: ' + rec['file'])
    print('All backup hashes verified')
    return manifest


def checked_backup(device):
    record = read_json(STATE / 'backup.json')
    dest = Path(record['path'])
    external(dest, device)
    require(sha256(dest / 'manifest.json') == record['manifest_sha256'], 'Backup manifest changed')
    verify_backup(dest)
    require(read_json(dest / 'plan.json') == read_json(STATE / 'plan.json'), 'Backup belongs to a different plan')
    return dest


def typed(phrase):
    require(sys.stdin.isatty(), 'Destructive stages require an interactive local terminal')
    require(input('Type exactly ' + phrase + ': ') == phrase, 'Cancelled')


def format_root(args):
    p, device, _ = current()
    dest = checked_backup(device)
    require(not (STATE / 'format-started').exists(), 'Format already attempted; use recovery instructions')
    part = next(x for x in p['partitions'] if x['name'] == 'userdata')
    block = Path('/dev/disk/by-partuuid') / part['partuuid']
    require(block.resolve() == Path(str(device) + 'p1'), 'Unexpected userdata device')
    require(not list((Path('/sys/class/block') / block.resolve().name / 'holders').iterdir()), 'Userdata has active holders')
    mounted = output(['lsblk', '-n', '-r', '-o', 'MOUNTPOINTS', device])
    require(not mounted, 'An internal partition is mounted')
    require(not Path('/dev/mapper/omarchy_root').exists(), 'Root mapper already exists')
    require(subprocess.run(['mountpoint', '-q', TARGET]).returncode != 0, '/mnt already mounted')
    print('Will erase ONLY userdata:', block, part['size'], 'bytes; create LUKS2 and Btrfs.')
    if not args.apply:
        return
    typed('ERASE USERDATA AND REPLACE GOOGLEBOOK OS')
    password = getpass.getpass('New disk password (never sent or saved): ')
    require(len(password) >= 12 and '\n' not in password and '\0' not in password, 'Use at least 12 characters')
    require(password == getpass.getpass('Repeat disk password: '), 'Passwords differ')
    (STATE / 'format-started').touch(mode=0o600)
    secret = password.encode()
    run(['cryptsetup', 'luksFormat', '--type', 'luks2', '--batch-mode', '--uuid', p['luks_uuid'],
         '--label', 'OMARCHY', '--cipher', 'aes-xts-plain64', '--key-size', '512', '--pbkdf', 'argon2id',
         '--pbkdf-memory', '1048576', '--iter-time', '2000', '--key-file', '-', block], input=secret)
    run(['cryptsetup', 'open', '--key-file', '-', block, 'omarchy_root'], input=secret)
    del secret, password
    run(['cryptsetup', 'luksHeaderBackup', block, '--header-backup-file', dest / 'luks-header.bin'])
    (dest / 'luks-header.bin').chmod(0o600)
    run(['mkfs.btrfs', '-f', '-L', 'Omarchy', '/dev/mapper/omarchy_root'])
    TARGET.mkdir(exist_ok=True)
    run(['mount', '/dev/mapper/omarchy_root', TARGET])
    for name in ('@', '@home', '@log', '@pkg'):
        run(['btrfs', 'subvolume', 'create', TARGET / name])
    run(['umount', TARGET])
    run(['mount', '-o', 'noatime,compress=zstd:3,subvol=@', '/dev/mapper/omarchy_root', TARGET])
    for subvol, relative in [('@home', 'home'), ('@log', 'var/log'), ('@pkg', 'var/cache/pacman/pkg')]:
        folder = TARGET / relative
        folder.mkdir(parents=True, exist_ok=True)
        run(['mount', '-o', 'noatime,compress=zstd:3,subvol=' + subvol, '/dev/mapper/omarchy_root', folder])
    save_json(STATE / 'format.json', dict(btrfs_uuid=output(['blkid', '-s', 'UUID', '-o', 'value', '/dev/mapper/omarchy_root'])))
    os.sync()
    print('Encrypted filesystem mounted. Backup LUKS header is on the external drive.')


def mounted():
    require((STATE / 'format.json').is_file(), 'Complete the format stage first')
    require(output(['findmnt', '-no', 'FSTYPE', '--mountpoint', TARGET]) == 'btrfs', 'Target not mounted')
    require(output(['findmnt', '-no', 'SOURCE', '--mountpoint', TARGET]).startswith('/dev/mapper/omarchy_root['), 'Wrong mounted target')
    require(output(['cryptsetup', 'luksUUID', str(read_json(STATE / 'plan.json')['device']) + 'p1']) == read_json(STATE / 'plan.json')['luks_uuid'], 'LUKS identity changed')


def build(args):
    p, device, gpt = current()
    checked_backup(device)
    mounted()
    require((STATE / 'configured.json').is_file(), 'Configure target first')
    cmdline = (f"cryptdevice=UUID={p['luks_uuid']}:omarchy_root root=/dev/mapper/omarchy_root rootfstype=btrfs rootflags=subvol=@ rw "
               'zswap.enabled=0 modprobe.blacklist=xe initramfs_async=0 console=tty0 loglevel=3 log_buf_len=4M '
               'printk.time=1 panic=30 fbcon=nodefer plymouth.enable=0 rd.plymouth=0 ' +
               ' '.join('xe.' + k + '=' + v for k, v in XE_PARAMETERS.items()))
    require((TARGET / 'boot/initramfs-linux-t2.img').stat().st_size < 29 * 1024**2, 'Initramfs too large')
    build_set(TARGET / 'boot/vmlinuz-linux-t2', TARGET / 'boot/initramfs-linux-t2.img', cmdline,
              STATE / 'candidate', ROOT / 'vendor', sizes={p['name']: p['size'] for p in gpt.partitions()}, installed=True)
    (TARGET / 'etc/kernel').mkdir(exist_ok=True)
    (TARGET / 'etc/kernel/cmdline').write_text(cmdline + '\n')
    shutil.copy2(STATE / 'candidate/avb-private.pem', TARGET / 'etc/asus-boot/avb-private.pem')
    print('Candidate files built; no boot partition writes. Next: validate.')


def candidate_regions(p, gpt, backup):
    manifest = read_json(STATE / 'candidate/manifest.json')
    require([x['name'] for x in manifest['images']] == list(NAMES), 'Unexpected boot set')
    parts = {x['name']: x for x in p['partitions']}
    regions = []
    for rec in manifest['images']:
        src = STATE / 'candidate' / (rec['name'] + '.img')
        part = parts[rec['name']]
        require(src.stat().st_size == part['size'] == rec['size'] and sha256(src) == rec['sha256'], 'Candidate changed')
        regions.append((part['start_lba'] * 512, src.read_bytes(), (backup / src.name).read_bytes()))
    primary, secondary = gpt.rename_vm_partitions()
    regions += [(p['disk_bytes'] - len(secondary), secondary, gpt.secondary), (0, primary, gpt.primary)]
    misc = (backup / 'misc.img').read_bytes()
    require(misc[:32].split(b'\0')[0] in (b'', b'boot-recovery'), 'Unexpected Android recovery command')
    regions.append((parts['misc']['start_lba'] * 512, bytes(32) + misc[32:512], misc[:512]))
    return regions


def validate(args):
    p, device, gpt = current()
    backup = checked_backup(device)
    regions = candidate_regions(p, gpt, backup)
    image = STATE / 'loader-test.sparse.img'
    require(not image.exists(), 'Existing loader fixture; remove only this file before retrying')
    with image.open('xb') as f:
        f.truncate(p['disk_bytes'])
        for offset, new, _ in regions:
            f.seek(offset)
            f.write(new)
    loader = args.loader.resolve()
    require(loader.is_file(), 'Build the loader harness first')
    result = subprocess.run([str(loader), '-b', '1', str(image)], cwd=STATE, capture_output=True, text=True)
    (STATE / 'loader-validation.log').write_text(result.stdout + result.stderr)
    require(result.returncode == 0 and 'vb2api_load_kernel() returned 0' in result.stdout, 'Loader failed; inspect private log')
    save_json(STATE / 'validated.json', dict(manifest_sha256=sha256(STATE / 'candidate/manifest.json'),
                                           regions=[dict(offset=o, sha256=digest(n)) for o,n,_ in regions]))
    image.unlink()
    print('ChromiumOS Android loader accepted the candidate. This is not a physical boot test.')


def write_all(fd, offset, data):
    view = memoryview(data)
    while view:
        n = os.pwrite(fd, view, offset)
        require(n > 0, 'Short disk write')
        view, offset = view[n:], offset + n
    os.fsync(fd)


def commit(args):
    p, device, gpt = current()
    mounted()
    backup = checked_backup(device)
    require(not (STATE / 'commit-started').exists(), 'Commit already attempted; inspect result and recover manually')
    proof = read_json(STATE / 'validated.json')
    require(proof['manifest_sha256'] == sha256(STATE / 'candidate/manifest.json'), 'Candidate changed after validation')
    regions = candidate_regions(p, gpt, backup)
    require(proof['regions'] == [dict(offset=o, sha256=digest(n)) for o,n,_ in regions], 'Validated regions differ')
    with device.open('rb') as f:
        for offset, _, old in regions:
            f.seek(offset)
            require(f.read(len(old)) == old, 'Original boot region changed since backup')
    print('Will write four slot-A images, two GPT label changes and the 32-byte misc command. Slot B payloads remain unchanged.')
    if not args.apply:
        print('Dry run passed; no writes')
        return
    typed('WRITE VALIDATED SLOT A')
    (STATE / 'commit-started').touch(mode=0o600)
    fd = os.open(device, os.O_RDWR | os.O_SYNC)
    attempted = []
    try:
        for offset, new, old in regions:
            attempted.append((offset, old))
            write_all(fd, offset, new)
            require(os.pread(fd, len(new), offset) == new, 'Disk read-back failed')
        save_json(STATE / 'committed.json', dict(status='All boot regions passed read-back', disk_guid=p['disk_guid']))
    except BaseException:
        status = []
        for offset, old in reversed(attempted):
            try:
                write_all(fd, offset, old)
                require(os.pread(fd, len(old), offset) == old, 'Rollback read-back failed')
                status.append(dict(offset=offset, restored=True))
            except BaseException as error:
                status.append(dict(offset=offset, restored=False, error=str(error)))
        save_json(STATE / 'rollback.json', status)
        print('Commit failed. See /run/lapis-install/rollback.json. Do not reboot.')
        raise
    finally:
        os.close(fd)
    saved = TARGET / 'var/lib/asus-boot/installation'
    shutil.copytree(STATE, saved, ignore=shutil.ignore_patterns('*.sparse.img'), dirs_exist_ok=False)
    shutil.copytree(STATE, backup / 'installed-state', ignore=shutil.ignore_patterns('*.sparse.img'), dirs_exist_ok=False)
    os.sync()
    print('Boot committed and state archived. Follow the shutdown and first-boot checklist.')


def main():
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    q = subs.add_parser('plan'); q.add_argument('--device', required=True, type=Path); q.set_defaults(fn=plan)
    q = subs.add_parser('backup'); q.add_argument('--destination', required=True, type=Path); q.set_defaults(fn=backup)
    q = subs.add_parser('verify-backup'); q.add_argument('destination', type=Path); q.set_defaults(fn=lambda a: verify_backup(a.destination))
    for name, fn in [('format', format_root), ('commit', commit)]:
        q = subs.add_parser(name); q.add_argument('--apply', action='store_true'); q.set_defaults(fn=fn)
    q = subs.add_parser('build'); q.set_defaults(fn=build)
    q = subs.add_parser('validate'); q.add_argument('--loader', type=Path, default=ROOT / 'build/load_android_test'); q.set_defaults(fn=validate)
    args = parser.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
