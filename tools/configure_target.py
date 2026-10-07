#!/usr/bin/env python3
"""Install ISO packages and configure the mounted Lapis encrypted root."""
import argparse
import datetime
import getpass
import os
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, KERNEL_PACKAGES, KERNEL_RELEASE, KERNEL_SHA256, output, read_json, require, run, save_json, sha256
from tools.native import STATE, TARGET, current, mounted, checked_backup

MASKED_HOOKS = ['60-mkinitcpio-remove.hook', '60-limine-mkinitcpio-remove-pre.hook',
                '80-limine-efi-deploy.hook', '90-mkinitcpio-install.hook',
                '90-limine-mkinitcpio-remove-post.hook', '99-omarchy-limine.hook', '10-limine-snapper-lock.hook']


def put(name, content, mode=0o644):
    path = TARGET / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), 'Refuse writing through target symlink: ' + name)
    path.write_text(content)
    path.chmod(mode)


def mask(name):
    path = TARGET / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        require(path.is_symlink() and os.readlink(path) == '/dev/null', 'Unexpected file at ' + name)
    else:
        path.symlink_to('/dev/null')


def chroot(*argv, **kw):
    return run(['arch-chroot', TARGET, *argv], **kw)


def packages(args):
    current(); mounted()
    require(sys.stdin.isatty(), 'Package setup needs a local terminal for the private account-password prompt')
    require(not (STATE / 'packages-started').exists(), 'Packages already attempted; inspect failure before manual resumption')
    require(re.fullmatch('[a-z][a-z0-9_-]{0,30}', args.user) and args.user not in ('root', 'asuslive'), 'Invalid username')
    require('\n' not in args.name and '\r' not in args.name and ':' not in args.name, 'Invalid full name')
    require((Path('/usr/share/zoneinfo') / args.timezone).is_file() and '..' not in args.timezone.split('/'), 'Invalid timezone')
    require(re.fullmatch('[a-zA-Z0-9_-]+', args.keymap), 'Invalid console keymap')
    cache = Path('/var/cache/omarchy/mirror/offline')
    for file, expected in KERNEL_PACKAGES.items():
        require(sha256(cache / file) == expected, 'Wrong ISO kernel package')
    source = Path('/usr/share/omarchy-iso/omarchy-base.packages')
    require(source.is_file(), 'Missing official ISO package manifest')
    requested = [line.split('#')[0].strip() for line in source.read_text().splitlines()]
    requested = [x for x in requested if x]
    require(all(re.fullmatch('[a-zA-Z0-9@+_.-]+', x) for x in requested), 'Invalid package manifest')
    requested = [x for x in requested if x not in ('linux', 'linux-headers', *KERNEL_PACKAGES)]
    # The pinned linux-t2 pair satisfies the linux dependency; never install a second kernel.
    requested = [x for x in requested if x not in ('linux-t2', 'linux-t2-headers')]
    account = dict(user=args.user, name=args.name, timezone=args.timezone, keymap=args.keymap)
    save_json(STATE / 'account.json', account)
    (STATE / 'packages-started').touch(mode=0o600)
    for name in MASKED_HOOKS:
        mask('/etc/asus-boot/pacman-hooks/' + name)
    conf = STATE / 'offline-pacman.conf'
    conf.write_text('[options]\nArchitecture = auto\nHookDir = /etc/asus-boot/pacman-hooks\nSigLevel = Required DatabaseOptional\nLocalFileSigLevel = Required\nCacheDir = /var/cache/omarchy/mirror/offline/\n[offline]\nServer = file:///var/cache/omarchy/mirror/offline/\n')
    early = ['base', 'base-devel', 'btrfs-progs', 'cryptsetup', 'mkinitcpio', 'linux-firmware', 'intel-ucode', 'sudo', 'python', 'git', 'omarchy-keyring', 'lua51', 'luarocks']
    run(['pacstrap', '-C', conf, '-M', '-c', TARGET, *early])
    local_conf = STATE / 'kernel-local.conf'
    local_conf.write_text(conf.read_text().replace('LocalFileSigLevel = Required', 'LocalFileSigLevel = Optional'))
    run(['pacstrap', '-U', '-C', local_conf, '-M', '-c', TARGET, *(cache / x for x in KERNEL_PACKAGES)])
    run(['pacstrap', '-C', conf, '-M', '-c', TARGET, 'omarchy-settings', 'omarchy-nvim'])
    chroot('useradd', '-m', '-s', '/bin/bash', '-G', 'wheel', '-c', args.name, args.user)
    password = getpass.getpass('New login/sudo password (may differ from disk password): ')
    require(len(password) >= 12 and '\n' not in password and '\0' not in password, 'Use at least 12 characters')
    require(password == getpass.getpass('Repeat login password: '), 'Passwords differ')
    chroot('chpasswd', input=(args.user + ':' + password + '\n').encode())
    del password
    chroot('passwd', '-l', 'root')
    for src in (cache, Path('/opt/packages')):
        dest = TARGET / str(src).lstrip('/')
        dest.mkdir(parents=True, exist_ok=True)
        run(['mount', '--bind', src, dest])
    put('/etc/pacman.conf', conf.read_text())
    chroot('pacman', '-Sy', '--needed', '--noconfirm', *requested, 'omarchy')
    require(sha256(TARGET / 'boot/vmlinuz-linux-t2') == KERNEL_SHA256, 'Installed kernel differs')
    save_json(STATE / 'packages.json', dict(status='ISO package installation complete'))


def configure(args):
    p, device, _ = current(); mounted(); backup = checked_backup(device)
    require((STATE / 'packages.json').is_file(), 'Install packages first')
    require(not (STATE / 'configure-started').exists(), 'Configuration already attempted; inspect before resuming')
    require(Path('/sys/bus/pci/devices/0000:00:1f.3/subsystem_device').read_text().strip() == '0x15e4', 'Audio subsystem differs')
    account = read_json(STATE / 'account.json')
    user = account['user']
    (STATE / 'configure-started').touch(mode=0o600)
    fs = read_json(STATE / 'format.json')['btrfs_uuid']
    put('/etc/fstab', ''.join(f'UUID={fs} {mount} btrfs noatime,compress=zstd:3,subvol={sub} 0 0\n' for mount,sub in [('/', '@'),('/home','@home'),('/var/log','@log'),('/var/cache/pacman/pkg','@pkg')]))
    put('/etc/hostname', 'omarchy\n')
    put('/etc/hosts', '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 omarchy.localdomain omarchy\n')
    put('/etc/locale.gen', 'en_US.UTF-8 UTF-8\n')
    put('/etc/locale.conf', 'LANG=en_US.UTF-8\n')
    put('/etc/vconsole.conf', 'KEYMAP=' + account['keymap'] + '\n')
    localtime = TARGET / 'etc/localtime'
    localtime.unlink(missing_ok=True)
    localtime.symlink_to('../usr/share/zoneinfo/' + account['timezone'])
    put('/etc/adjtime', '0.0 0 0.0\n0\nUTC\n')
    put('/etc/sudoers.d/10-wheel', '%wheel ALL=(ALL:ALL) ALL\n', 0o440)
    chroot('locale-gen'); chroot('systemd-machine-id-setup')
    log = TARGET / 'var/log/omarchy-install.log'
    log.touch(); log.chmod(0o666)
    env = ['OMARCHY_PATH=/usr/share/omarchy', 'OMARCHY_INSTALL=/usr/share/omarchy/install',
           'OMARCHY_INSTALL_USER=' + user, 'OMARCHY_USER_NAME=' + account['name'], 'OMARCHY_USER_EMAIL=',
           'OMARCHY_MIRROR=stable', 'OMARCHY_RUNTIME_PACKAGE=omarchy', 'OMARCHY_SETTINGS_PACKAGE=omarchy-settings',
           'OMARCHY_NVIM_PACKAGE=omarchy-nvim', 'OMARCHY_INSTALL_LOG_FILE=/var/log/omarchy-install.log',
           'OMARCHY_LOG_TO_STDOUT=1', 'OMARCHY_SETUP_CONTEXT=iso-chroot', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/bin',
           'OMARCHY_START_TIME=' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    chroot('env', '--unset=XDG_RUNTIME_DIR', *env, '/usr/bin/omarchy-apply-system', '--install-user', user, '--first-install')
    run(['arch-chroot', '-u', user, TARGET, 'env', '--unset=XDG_RUNTIME_DIR', *env,
         'HOME=/home/' + user, 'USER=' + user, 'LOGNAME=' + user, 'SHELL=/bin/bash', '/usr/bin/omarchy-provision-user', '--force', '--first-install'])
    log.chmod(0o644)
    put('/usr/local/libexec/asus-gpu-prepare', (ROOT / 'assets/installed/gpu-prepare.py').read_text(), 0o755)
    put('/etc/systemd/system/asus-gpu-prepare.service', (ROOT / 'assets/installed/gpu-prepare.service').read_text())
    put('/etc/systemd/system/sddm.service.d/20-asus-lapis.conf', '[Unit]\nRequires=asus-gpu-prepare.service\nAfter=asus-gpu-prepare.service\n[Service]\nEnvironment=AQ_NO_MODIFIERS=1 AQ_NO_ATOMIC=1\n')
    put('/etc/modprobe.d/asus-lapis-xe.conf', 'blacklist xe\noptions xe gsc_firmware_path= enable_panel_replay=0 enable_psr=0 enable_fbc=0 enable_dsb=0 enable_sagv=0 enable_dc=0\n')
    put('/etc/modprobe.d/asus-lapis-audio.conf', 'blacklist snd_sof_pci_intel_ptl\noptions snd_soc_sof_sdw quirk=0x288000\noptions snd_sof_intel_hda_generic dmic_num=0\n')
    put('/etc/wireplumber/wireplumber.conf.d/52-asus-lapis-unused-bt-offload.conf', 'monitor.alsa.rules = [ { matches = [ { api.alsa.pcm.id = "Bluetooth" } ] actions = { update-props = { node.disabled = true } } } ]\n')
    mask('/etc/systemd/system-generators/systemd-gpt-auto-generator')
    put('/home/' + user + '/.config/uwsm/env.d/20-asus-lapis', 'export AQ_NO_MODIFIERS=1\nexport AQ_NO_ATOMIC=1\n')
    monitor = 'hl.monitor({ output = "eDP-1", mode = "2880x1800@60", position = "0x0", scale = 2 })\n'
    put('/home/' + user + '/.config/hypr/monitors.lua', 'hl.env("GDK_SCALE", "2")\nhl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })\n' + monitor)
    put('/etc/sddm/hyprland-lapis.lua', (TARGET / 'usr/share/sddm/hyprland.lua').read_text() + '\n' + monitor)
    put('/etc/sddm.conf.d/99-asus-lapis.conf', '[Wayland]\nCompositorCommand=start-hyprland -- --config /etc/sddm/hyprland-lapis.lua\n[Users]\nRememberLastUser=true\nRememberLastSession=true\n')
    put('/etc/sddm.conf.d/autologin.conf', '[Autologin]\nUser=' + user + '\nSession=omarchy.desktop\n')
    put('/var/lib/sddm/state.conf', '[Last]\nSession=omarchy.desktop\nUser=' + user + '\n')
    chroot('chown', 'sddm:sddm', '/var/lib/sddm', '/var/lib/sddm/state.conf')
    chroot('chown', '-R', user + ':' + user, '/home/' + user)
    put('/etc/NetworkManager/conf.d/90-asus-lapis.conf', '[device]\nwifi.backend=wpa_supplicant\n')
    resolv = TARGET / 'etc/resolv.conf'; resolv.unlink(missing_ok=True); resolv.symlink_to('../run/systemd/resolve/stub-resolv.conf')
    chroot('visudo', '-c')
    chroot('systemctl', 'enable', 'asus-gpu-prepare.service', 'sddm.service', 'NetworkManager.service', 'systemd-resolved.service', 'systemd-timesyncd.service')
    chroot('systemctl', 'disable', 'iwd.service', 'systemd-networkd.service', 'limine-snapper-sync.service')
    chroot('systemctl', 'mask', 'sshd.service', 'getty@tty2.service', 'autovt@tty2.service', 'limine-snapper-sync.service', 'omarchy-provision-owner.service', 'efi.mount', 'efi.automount')
    chroot('systemctl', 'set-default', 'graphical.target')
    # Official provisioning creates the normal online pacman configuration. Refuse an offline-only result.
    conf = TARGET / 'etc/pacman.conf'
    require('[offline]' not in conf.read_text(), 'Official provisioning left an offline-only pacman config; inspect before boot')
    conf.write_text(conf.read_text().replace('[options]', '[options]\nHookDir = /etc/asus-boot/pacman-hooks\nIgnorePkg = linux-t2 linux-t2-headers\nNoExtract = usr/lib/snapper/plugins/10-limine-snapper-sync', 1))
    put('/usr/local/libexec/asus-boot-update-guard', '#!/bin/sh\necho "Lapis kernel update blocked: rebuild and validate Android boot images first. See the repository update guide." >&2\nexit 1\n', 0o755)
    put('/etc/pacman.d/hooks/00-asus-lapis-kernel-guard.hook', '[Trigger]\nOperation = Upgrade\nOperation = Install\nOperation = Remove\nType = Path\nTarget = usr/lib/modules/*/vmlinuz\n[Action]\nDescription = Protect Lapis kernel and Android boot pair\nWhen = PreTransaction\nExec = /usr/local/libexec/asus-boot-update-guard\nAbortOnFail\n')
    plugin = TARGET / 'usr/lib/snapper/plugins/10-limine-snapper-sync'
    if plugin.exists():
        shutil.move(plugin, TARGET / 'etc/asus-boot/10-limine-snapper-sync.disabled')
    mask('/etc/systemd/system/snapper-cleanup.service.d/limine-snapper-override.conf')
    for name in ('/etc/asus-boot/mkinitcpio.conf', '/etc/mkinitcpio.conf.d/zz-asus-lapis.conf'):
        put(name, (ROOT / 'assets/installed/mkinitcpio.conf').read_text())
    save_json(TARGET / 'etc/asus-boot/install.json', p)
    shutil.copy2(backup / 'luks-header.bin', TARGET / 'etc/asus-boot/luks-header.bin')
    chroot('/usr/bin/mkinitcpio', '-c', '/etc/asus-boot/mkinitcpio.conf', '-k', KERNEL_RELEASE, '-g', '/boot/initramfs-linux-t2.img')
    listing = output(['arch-chroot', TARGET, 'lsinitcpio', '/boot/initramfs-linux-t2.img'])
    require(all(x not in listing for x in ('avb-private', 'luks-header', '.nmconnection', 'authorized_keys')), 'Private file in initramfs')
    require((TARGET / 'boot/initramfs-linux-t2.img').stat().st_size < 29 * 1024**2, 'Initramfs exceeds partition budget')
    save_json(STATE / 'configured.json', dict(status='Configured; boot partitions not yet committed'))
    print('Configuration complete. Wi-Fi credentials are not copied: connect through the desktop after first boot.')


def main():
    os.umask(0o022)
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(required=True)
    q = subs.add_parser('packages'); q.add_argument('--user', required=True); q.add_argument('--name', required=True)
    q.add_argument('--timezone', required=True); q.add_argument('--keymap', default='us'); q.set_defaults(fn=packages)
    q = subs.add_parser('configure'); q.set_defaults(fn=configure)
    a = p.parse_args(); a.fn(a)


if __name__ == '__main__':
    main()
