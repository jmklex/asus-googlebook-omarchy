import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

from lapis.common import new_regular_output, require, sha256
from lapis.cpio import archive, find_member, members
from lapis.gpt import ENTRY, tables, read_gpt
from tools import native
from tools.write_usb import resized_tables, write_full


def disk_fixture(parts=None, size=4 * 1024**2):
    if parts is None:
        parts = [('boot_a', 128, 255), ('pvmfw_a', 256, 383), ('pvmfw_b', 384, 511)]
    entries = bytearray(128 * 128)
    for i, (name, start, end) in enumerate(parts):
        entries[i*128:(i+1)*128] = ENTRY.pack(uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le,
            uuid.uuid4().bytes_le, start, end, 0, name.encode('utf-16-le'))
    header = [b'EFI PART', 0x10000, 92, 0, 0, 1, size//512-1, 34, size//512-34, uuid.uuid4().bytes_le, 2, 128, 128, 0]
    mbr = bytes(510) + b'\x55\xaa'
    primary, secondary = tables(header, entries, mbr)
    data = bytearray(size)
    data[:len(primary)] = primary
    data[-len(secondary):] = secondary
    return data


class SafetyTests(unittest.TestCase):
    def test_guards_are_runtime_checks(self):
        with self.assertRaises(RuntimeError):
            require(False, 'still enabled with python -O')

    def test_gpt_crc_detects_corruption(self):
        for offset in (512 + 40, 1024 + 60, -512 + 40):
            data = disk_fixture(); data[offset] ^= 1
            with self.assertRaises(RuntimeError):
                read_gpt(io.BytesIO(data), len(data))

    def test_gpt_rejects_overlap_and_duplicate_labels(self):
        for parts in [[('a',128,256),('b',256,300)], [('a',128,200),('a',201,250)], [('a',1,20)]]:
            data = disk_fixture(parts)
            with self.assertRaises(RuntimeError):
                read_gpt(io.BytesIO(data), len(data))

    def test_gpt_renames_only_two_labels(self):
        data = disk_fixture(); gpt = read_gpt(io.BytesIO(data), len(data))
        primary, secondary = gpt.rename_vm_partitions()
        data[:len(primary)] = primary; data[-len(secondary):] = secondary
        changed = read_gpt(io.BytesIO(data), len(data))
        self.assertEqual(gpt.primary[:512], changed.primary[:512])
        for old, new in zip(gpt.partitions(), changed.partitions()):
            expected = dict(old)
            if old['name'].startswith('pvmfw_'):
                expected['name'] = 'factory_' + old['name']
            self.assertEqual(expected, new)
        with self.assertRaises(RuntimeError):
            changed.rename_vm_partitions()

    def test_resize_keeps_partition_geometry(self):
        data = disk_fixture(); gpt = read_gpt(io.BytesIO(data), len(data))
        larger = len(data) * 2
        primary, secondary = resized_tables(gpt, larger)
        resized = bytearray(larger)
        resized[:len(primary)] = primary; resized[-len(secondary):] = secondary
        result = read_gpt(io.BytesIO(resized), larger)
        self.assertEqual(gpt.partitions(), result.partitions())
        with self.assertRaises(RuntimeError):
            resized_tables(gpt, len(data) - 512)

    def test_output_refuses_devices_existing_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image'; path.write_bytes(b'keep')
            with self.assertRaises(RuntimeError): new_regular_output(path)
            path.unlink(); path.symlink_to(Path(tmp) / 'missing')
            with self.assertRaises(RuntimeError): new_regular_output(path)
            with self.assertRaises(RuntimeError): new_regular_output('/dev/never-create-lapis')

    def test_cpio_override_and_path_rejection(self):
        first = archive({'config': (0o100644, b'old')})
        second = archive({'config': (0o100644, b'new')})
        self.assertEqual(find_member(first + second, 'config', lambda x:x), b'new')
        with self.assertRaises(RuntimeError): archive({'../secret': (0o100644, b'bad')})
        with self.assertRaises(RuntimeError): members(first[:120])

    def test_profile_rejects_unrecognized_disk(self):
        data = disk_fixture()
        with self.assertRaises(RuntimeError): native.validate_profile(read_gpt(io.BytesIO(data), len(data)))

    def test_short_writes_are_completed(self):
        class ShortWriter(io.BytesIO):
            def write(self, data): return super().write(data[:3])
        out = ShortWriter(); write_full(out, b'abcdefghij')
        self.assertEqual(out.getvalue(), b'abcdefghij')

    def test_partial_failed_commit_restores_all_attempted_regions(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); state = folder / 'state'; state.mkdir(); (state/'candidate').mkdir()
            manifest = state/'candidate/manifest.json'; manifest.write_text('{}')
            device = folder/'disk'; original = bytes(range(256)) * 8; device.write_bytes(original)
            regions = [(0,b'A'*512,original[:512]), (512,b'B'*512,original[512:1024])]
            (state/'validated.json').write_text(json.dumps(dict(manifest_sha256=sha256(manifest), regions=[dict(offset=o,sha256=native.digest(n)) for o,n,_ in regions])))
            write = native.write_all
            count = 0
            def fail_second(fd, offset, data):
                nonlocal count
                count += 1
                if count == 2:
                    os.pwrite(fd, data[:100], offset)
                    raise OSError('injected partial write failure')
                return write(fd, offset, data)
            with mock.patch.object(native,'STATE',state), mock.patch.object(native,'current',return_value=({},device,None)), \
                 mock.patch.object(native,'mounted'), mock.patch.object(native,'checked_backup',return_value=folder), \
                 mock.patch.object(native,'candidate_regions',return_value=regions), mock.patch.object(native,'typed'), \
                 mock.patch.object(native,'write_all',side_effect=fail_second):
                with self.assertRaises(OSError): native.commit(argparse.Namespace(apply=True))
            self.assertEqual(device.read_bytes(),original)
            results=json.loads((state/'rollback.json').read_text())
            self.assertEqual(len(results),2)
            self.assertTrue(all(x['restored'] for x in results))


if __name__ == '__main__':
    unittest.main()
