#!/usr/bin/env python3
"""The physically validated Lapis GPU startup sequence, before display-manager."""
from pathlib import Path
import json,os,subprocess,time
def require(ok, message):
 if not ok:raise RuntimeError(message)
require(os.geteuid() == 0, 'GPU prerequisite failed')
require(Path('/sys/class/dmi/id/product_name').read_text().strip() == 'Lapis', 'GPU prerequisite failed')
require(Path('/sys/bus/pci/devices/0000:00:02.0/device').read_text().strip() == '0xb090', 'GPU prerequisite failed')
require(subprocess.check_output(['uname', '-r'], text=True).strip() == '7.2.4-arch1-Watanare-T2-3-t2', 'GPU prerequisite failed')
require(not Path('/sys/module/xe').exists(), 'Xe loaded before the checked display sequence')
require(not Path('/sys/bus/pci/devices/0000:00:1f.3/driver').exists(), 'Audio must bind after graphics preparation')
params={'gsc_firmware_path':'','enable_panel_replay':'0','enable_psr':'0','enable_fbc':'0','enable_dsb':'0','enable_sagv':'0','enable_dc':'0'}
load=['modprobe','xe']+[k+'='+v for k,v in params.items()]
def run(args,timeout=40):
 print('RUN',json.dumps(args),flush=True);subprocess.run(args,check=True,timeout=timeout)
run(load);time.sleep(2)
nodes=[str(x) for x in Path('/dev/dri').glob('*') if x.is_char_device()]
require(nodes, 'GPU prerequisite failed')
r=subprocess.run(['fuser']+nodes,capture_output=True,text=True)
require(r.returncode == 1 and (not r.stdout.strip()), 'A graphical client started before GPU preparation')
for vt in Path('/sys/class/vtconsole').glob('vtcon*'):
 if 'frame buffer' in (vt/'name').read_text() and (vt/'bind').read_text().strip()=='1':(vt/'bind').write_text('0\n')
# Releasing the console can retire its final module reference asynchronously.
# The SOF audio driver also holds an Xe reference, so its probe is ordered after
# this service through a soft blacklist and ExecStartPost in the unit.
for attempt in range(40):
 refs=int(Path('/sys/module/xe/refcnt').read_text())
 if refs==0:break
 if attempt in (0,20,39):print('Waiting for Xe references:',refs,'holders:',[x.name for x in Path('/sys/module/xe/holders').iterdir()],flush=True)
 time.sleep(0.25)
require(refs == 0, 'Xe still referenced; refusing any forced unload')
run(['modprobe','-r','xe'],30)
require(not Path('/sys/module/xe').exists(), 'GPU prerequisite failed')
time.sleep(1);run(load)
for name,want in params.items():
 actual=(Path('/sys/module/xe/parameters')/name).read_text().strip()
 require(actual == want or (want == '0' and actual == 'N'), (name, actual))
Path('/run/asus-xe-reinitialized').write_text(Path('/proc/uptime').read_text())
print('ASUS_GPU_READY: checked driver reinitialization complete',flush=True)
