#!/usr/bin/env python3
"""Recreate the verified ASUS live desktop using RAM and signed ISO packages."""
from pathlib import Path
import argparse
import json
import os
import pwd
import shutil
import subprocess
import time

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true', help='Validate prerequisites without changes')
args = parser.parse_args()


def run(argv, **kw):
    print('RUN', json.dumps(argv), flush=True)
    return subprocess.run(argv, check=True, **kw)


def output(argv):
    return subprocess.check_output(argv, text=True).strip()


require(os.geteuid() == 0, 'Live hardware/environment prerequisite failed')
require(output(['findmnt', '-no', 'FSTYPE', '/']) == 'overlay', 'Live hardware/environment prerequisite failed')
require(output(['findmnt', '-no', 'FSTYPE', '/run/archiso/cowspace']) == 'tmpfs', 'Live hardware/environment prerequisite failed')
require('archisobasedir=arch' in Path('/proc/cmdline').read_text().split(), 'Live hardware/environment prerequisite failed')
require(Path('/sys/class/dmi/id/product_name').read_text().strip() == 'Lapis', 'Live hardware/environment prerequisite failed')
require(Path('/sys/bus/pci/devices/0000:00:02.0/device').read_text().strip() == '0xb090', 'Live hardware/environment prerequisite failed')
require(output(['uname', '-r']) == '7.2.4-arch1-Watanare-T2-3-t2', 'Live hardware/environment prerequisite failed')
require(not any(('/dev/nvme' in line for line in Path('/proc/mounts').read_text().splitlines())), 'Live hardware/environment prerequisite failed')
assets = Path('/opt/asus-googlebook-omarchy/assets/live')
require((assets / 'hyprland.lua').is_file(), 'Live hardware/environment prerequisite failed')
require(Path('/var/cache/omarchy/mirror/offline/offline.db').is_file(), 'Live hardware/environment prerequisite failed')
params = {
    'gsc_firmware_path': '',
    'enable_panel_replay': '0',
    'enable_psr': '0',
    'enable_fbc': '0',
    'enable_dsb': '0',
    'enable_sagv': '0',
    'enable_dc': '0',
}
if Path('/sys/module/xe').exists():
    for name, value in params.items():
        actual = (Path('/sys/module/xe/parameters') / name).read_text().strip()
        require(actual == value or (value == '0' and actual == 'N'), (name, actual, value))
if args.check:
    print('Prerequisites and any loaded Xe parameters match the verified live baseline.')
    raise SystemExit(0)

run(['mount', '-o', 'remount,size=3G', '/run/archiso/cowspace'])
run(['systemctl', 'start', 'pacman-init.service'])
pacman_conf = Path('/run/asus-live-pacman.conf')
pacman_conf.write_text('''[options]
Architecture = auto
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Required
[offline]
Server = file:///var/cache/omarchy/mirror/offline/
''')
run(['pacman', '--config', str(pacman_conf), '-Sy', '--noconfirm'])
run(['pacman', '--config', str(pacman_conf), '-S', '--noconfirm', '--needed',
     'mesa', 'vulkan-intel', 'vulkan-icd-loader', 'hyprland', 'foot', 'ttf-liberation', 'grim'])

try:
    user = pwd.getpwnam('asuslive')
except KeyError:
    empty_skel = Path('/run/asus-empty-skel')
    empty_skel.mkdir(exist_ok=True)
    run(['useradd', '-m', '-k', str(empty_skel), '-s', '/bin/bash', '-G', 'video,render,input,wheel', 'asuslive'])
    user = pwd.getpwnam('asuslive')
require(user.pw_uid >= 1000 and user.pw_dir == '/home/asuslive', 'Live hardware/environment prerequisite failed')
sudoers = Path('/etc/sudoers.d/lapis-live')
sudoers.write_text('asuslive ALL=(ALL:ALL) NOPASSWD: ALL\n')
sudoers.chmod(0o440)
home = Path(user.pw_dir)
shutil.copyfile(assets / 'hyprland.lua', home / 'hyprland.lua')
(home / 'live-bashrc').write_text(
    "printf '\\nASUS Lapis - live graphics test\\nThis USB session runs in RAM.\\n\\n'\n"
    "PS1='live-test \\w $ '\n"
)
for name in ('hyprland.lua', 'live-bashrc'):
    shutil.chown(home / name, user=user.pw_uid, group=user.pw_gid)
run(['runuser', '-u', 'asuslive', '--', 'Hyprland', '--verify-config', '--config', str(home / 'hyprland.lua')])

if not Path('/sys/module/xe').exists():
    run(['modprobe', 'xe'] + [f'{k}={v}' for k, v in params.items()], timeout=40)
    # The first firmware-to-Xe display handoff failed in two physical boots.
    # Two physical sessions recovered after a normal unload and identical reload.
    # Do this once before any graphical client starts; never force an unload.
    time.sleep(2)
    drm_nodes = [str(p) for p in Path('/dev/dri').glob('*') if p.is_char_device()]
    require(drm_nodes, 'First Xe load did not create DRM devices')
    users = subprocess.run(['fuser'] + drm_nodes, capture_output=True, text=True)
    require(users.returncode == 1 and (not users.stdout.strip()), 'DRM devices are in use')
    for vt in Path('/sys/class/vtconsole').glob('vtcon*'):
        if 'frame buffer' in (vt / 'name').read_text() and (vt / 'bind').read_text().strip() == '1':
            (vt / 'bind').write_text('0\n')
    run(['modprobe', '-r', 'xe'], timeout=30)
    require(not Path('/sys/module/xe').exists(), 'Xe remained loaded')
    time.sleep(1)
    run(['modprobe', 'xe'] + [f'{k}={v}' for k, v in params.items()], timeout=40)
    Path('/run/asus-xe-reinitialized').write_text(Path('/proc/uptime').read_text())
    print('ASUS_XE_REINITIALIZED: one checked unload/reload before desktop startup', flush=True)
for name, value in params.items():
    actual = (Path('/sys/module/xe/parameters') / name).read_text().strip()
    require(actual == value or (value == '0' and actual == 'N'), (name, actual, value))

unit = Path('/run/systemd/system/asus-live-desktop.service')
unit.write_text(f'''[Unit]
Description=ASUS RAM-only live desktop test
[Service]
Type=simple
User=asuslive
PAMName=login
TTYPath=/dev/tty2
StandardInput=tty
StandardOutput=journal
StandardError=journal
WorkingDirectory=/home/asuslive
Environment=XDG_SESSION_TYPE=wayland XDG_SESSION_CLASS=user XDG_RUNTIME_DIR=/run/user/{user.pw_uid} AQ_NO_MODIFIERS=1 AQ_NO_ATOMIC=1
ExecStart=/usr/bin/dbus-run-session -- /usr/bin/Hyprland --config /home/asuslive/hyprland.lua
''')
run(['systemctl', 'mask', '--runtime', '--now', 'getty@tty2.service', 'autovt@tty2.service'])
run(['systemctl', 'daemon-reload'])
run(['chvt', '2'])
run(['systemctl', 'start', 'asus-live-desktop.service'])
print('ASUS_LIVE_DESKTOP_STARTED: 2880x1800 at 60 Hz; all installation writes were to the RAM overlay.', flush=True)
