#!/usr/bin/env python3
"""Fetch pinned public tool sources. No binaries or disk images are downloaded."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, output, require, run

SOURCES = {
    'mkbootimg': ('https://android.googlesource.com/platform/system/tools/mkbootimg', 'd2bb0af5ba6d3198a3e99529c97eda1be0b5a093'),
    'avb': ('https://android.googlesource.com/platform/external/avb', 'c5066a96caa7bf4150c0a8cc8cc14ab81733fdc7'),
    'vboot': ('https://chromium.googlesource.com/chromiumos/platform/vboot_reference', '7cf41276406903650ee34d4f16af74196c85d346'),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', type=Path, default=ROOT / 'vendor')
    args = p.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for name, (url, revision) in SOURCES.items():
        dest = args.destination / name
        if not dest.exists():
            run(['git', 'init', str(dest)])
            run(['git', '-C', dest, 'remote', 'add', 'origin', url])
            run(['git', '-C', dest, 'fetch', '--depth=1', 'origin', revision])
            run(['git', '-C', dest, 'checkout', '--detach', 'FETCH_HEAD'])
        require(output(['git', '-C', dest, 'rev-parse', 'HEAD']) == revision, f'{name}: wrong revision')
        require(not output(['git', '-C', dest, 'status', '--porcelain', '--untracked-files=no']), f'{name}: modified source')
        print(f'{name}: verified {revision}')


if __name__ == '__main__':
    main()
