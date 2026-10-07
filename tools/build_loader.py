#!/usr/bin/env python3
"""Build the read-only ChromiumOS Android loader harness on Linux or macOS."""
import argparse
import os
from pathlib import Path
import platform
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, require, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, default=ROOT / 'vendor')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/load_android_test')
    args = parser.parse_args()
    vendor = args.vendor.resolve()
    vboot = vendor / 'vboot'
    require((vboot / 'Makefile').is_file(), 'Fetch pinned sources first')
    dest = args.output.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    compat = dest.parent / 'compat'
    compat.mkdir(exist_ok=True)
    if platform.system() == 'Darwin':
        pairs = [('htobe', 'OSSwapHostToBigInt'), ('htole', 'OSSwapHostToLittleInt'),
                 ('be', 'OSSwapBigToHostInt'), ('le', 'OSSwapLittleToHostInt')]
        text = '#pragma once\n#include <libkern/OSByteOrder.h>\n'
        for prefix, fn in pairs:
            for bits in (16, 32, 64):
                name = prefix + str(bits) + ('toh' if prefix in ('be', 'le') else '')
                text += f'#define {name} {fn}{bits}\n'
        (compat / 'endian.h').write_text(text)
    cc = os.environ.get('CC', 'cc')
    run(['make', '-C', vboot, '-j2', 'FIRMWARE_ARCH=mock', 'USE_AVB=1',
         'LIBAVB_SRCDIR=' + str(vendor / 'avb') + '/', 'CC=' + cc,
         'TEST_FLAGS=-O2 -I' + str(compat), 'fwlib'])
    includes = ['firmware/2lib/include', 'firmware/include', 'firmware/lib/include',
                'firmware/lib/cgptlib/include', 'host/lib/include', 'host/lib21/include', 'host/include']
    run([cc, '-O2', '-DUSE_AVB=1', '-I' + str(compat),
         *('-I' + str(vboot / p) for p in includes), ROOT / 'tools/loader_harness.c',
         vboot / 'build/vboot_fw.a', '-o', dest])
    print('Built', dest)


if __name__ == '__main__':
    main()
