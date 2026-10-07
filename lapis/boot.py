"""Build signed Android v4 boot sets, for files only."""
from pathlib import Path
import os
import sys

from .common import KERNEL_SHA256, new_regular_output, require, require_regular, run, save_json, sha256
from .cpio import archive


def make_key(path):
    path = Path(path)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        run(['openssl', 'genrsa', '-out', path, '2048'])
    require_regular(path)
    require(path.stat().st_mode & 0o077 == 0, 'AVB private key must be mode 600')


def build_set(kernel, initrd, cmdline, destination, vendor, *, sizes=None, installed=False):
    """Installed initrd goes in vendor_boot (32 MiB); live initrd in init_boot."""
    dest, vendor = Path(destination), Path(vendor)
    require(not dest.exists(), 'Boot output directory already exists')
    dest.mkdir(parents=True, mode=0o700)
    for path in (kernel, initrd):
        require_regular(path)
    require(sha256(kernel) == KERNEL_SHA256, 'Kernel differs from the hardware-tested version')
    require(len(cmdline.encode()) < 1536 and '\n' not in cmdline, 'Invalid kernel command line')
    mk, avb = vendor / 'mkbootimg/mkbootimg.py', vendor / 'avb/avbtool.py'
    require(mk.is_file() and avb.is_file(), 'Run tools/fetch_sources.py first')
    key = dest / 'avb-private.pem'
    make_key(key)
    run(['openssl', 'rsa', '-in', key, '-pubout', '-out', dest / 'avb-public.pem'])
    empty = dest / 'empty.cpio'
    empty.write_bytes(archive({}))
    ramdisk = Path(initrd).read_bytes()
    padded = dest / 'aligned-initramfs.img'
    padded.write_bytes(ramdisk + bytes((-len(ramdisk)) % 4))
    run([sys.executable, mk, '--header_version', '4', '--kernel', kernel, '--cmdline', cmdline, '-o', dest / 'boot_a.img'])
    run([sys.executable, mk, '--header_version', '4', '--ramdisk', empty if installed else padded, '-o', dest / 'init_boot_a.img'])
    run([sys.executable, mk, '--header_version', '4', '--pagesize', '4096', '--vendor_cmdline', cmdline,
         '--ramdisk_type', 'platform', '--ramdisk_name', 'linux' if installed else 'empty',
         '--vendor_ramdisk_fragment', padded if installed else empty, '--vendor_boot', dest / 'vendor_boot_a.img'])
    image_sizes = {}
    for name in ('boot', 'init_boot', 'vendor_boot'):
        image = dest / f'{name}_a.img'
        size = sizes[f'{name}_a'] if sizes else ((image.stat().st_size + 1048575) // 1048576 + 1) * 1048576
        run([sys.executable, avb, 'add_hash_footer', '--image', image, '--partition_name', name,
             '--partition_size', str(size), '--algorithm', 'SHA256_RSA2048', '--key', key])
        (dest / f'{name}.img').symlink_to(image.name)
        image_sizes[f'{name}_a'] = size
    argv = [sys.executable, avb, 'make_vbmeta_image', '--output', dest / 'vbmeta_a.img',
            '--algorithm', 'SHA256_RSA2048', '--key', key, '--padding_size', '4096']
    for name in ('boot', 'init_boot', 'vendor_boot'):
        argv += ['--include_descriptors_from_image', dest / f'{name}_a.img']
    run(argv)
    size = sizes['vbmeta_a'] if sizes else 1048576
    require((dest / 'vbmeta_a.img').stat().st_size <= size, 'vbmeta partition too small')
    with (dest / 'vbmeta_a.img').open('r+b') as f:
        f.truncate(size)
    image_sizes['vbmeta_a'] = size
    run([sys.executable, avb, 'verify_image', '--image', dest / 'vbmeta_a.img', '--key', dest / 'avb-public.pem'])
    result = dict(kernel_sha256=sha256(kernel), initramfs_sha256=sha256(initrd), cmdline=cmdline,
                  vendor_alignment_padding=(-len(ramdisk)) % 4 if installed else 0,
                  images=[dict(name=n, size=s, sha256=sha256(dest / f'{n}.img')) for n, s in image_sizes.items()])
    save_json(dest / 'manifest.json', result)
    return result
