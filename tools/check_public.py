#!/usr/bin/env python3
"""Check tracked files for forbidden artifacts, personal paths and common secrets."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
bad = []
for name in filter(None, paths):
    path = root / name
    if path.is_symlink() or path.stat().st_size > 2 * 1024**2:
        bad.append((name, 'symlink or oversized file')); continue
    if path.suffix.lower() in ('.img','.iso','.bin','.pem','.key','.psk','.nmconnection','.qcow2','.zip'):
        bad.append((name, 'private/build artifact extension'))
    content = path.read_bytes()
    patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{30,}',
                rb'/Users/[a-zA-Z][a-zA-Z0-9_-]+/', rb'192\.168\.\d+\.\d+',
                rb'(?m)^ssh-(?:rsa|ed25519) [A-Za-z0-9+/]{40,}']
    if any(re.search(pattern,content) for pattern in patterns):
        bad.append((name,'private content pattern'))
for name, reason in bad:
    print(name + ': ' + reason)
if bad: sys.exit(1)
print('Tracked-file public-content checks passed')
