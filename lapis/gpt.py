"""Read, validate and minimally edit 512-byte-sector GPT tables.

The public installer deliberately accepts only the factory 128-entry layout.
No disk is opened for writing by this module.
"""
from dataclasses import dataclass
import struct
import uuid
import zlib

from .common import require

SECTOR = 512
HEADER = struct.Struct('<8s4I4Q16sQ3I')
ENTRY = struct.Struct('<16s16sQQQ72s')


@dataclass
class GPT:
    header: list
    entries: bytearray
    primary: bytes
    secondary: bytes
    disk_bytes: int

    @property
    def guid(self):
        return str(uuid.UUID(bytes_le=self.header[9]))

    def partitions(self):
        result = []
        for i in range(self.header[11]):
            raw = self.entries[i * 128:(i + 1) * 128]
            typ, guid, start, end, attrs, name = ENTRY.unpack(raw)
            if typ == bytes(16):
                continue
            result.append(dict(index=i + 1, name=name.decode('utf-16-le').rstrip('\0'),
                               type_guid=str(uuid.UUID(bytes_le=typ)),
                               partuuid=str(uuid.UUID(bytes_le=guid)),
                               start_lba=start, end_lba=end, size=(end - start + 1) * 512,
                               attributes=attrs))
        return result

    def rename_vm_partitions(self):
        entries = bytearray(self.entries)
        found = set()
        for part in self.partitions():
            if part['name'] in ('pvmfw_a', 'pvmfw_b'):
                found.add(part['name'])
                offset = (part['index'] - 1) * 128 + 56
                entries[offset:offset + 72] = ('factory_' + part['name']).encode('utf-16-le').ljust(72, b'\0')
        require(found == {'pvmfw_a', 'pvmfw_b'}, 'Factory pvmfw labels missing; do not rerun an installation')
        return tables(self.header, entries, self.primary[:512])


def encode_header(values):
    values = list(values)
    values[3] = 0
    values[3] = zlib.crc32(HEADER.pack(*values)) & 0xffffffff
    return HEADER.pack(*values).ljust(512, b'\0')


def tables(header, entries, mbr):
    """Return primary and backup regions for a canonical 128-entry GPT."""
    h = list(header)
    require(h[10:13] == [2, 128, 128] and len(entries) == 16384, 'Unsupported GPT geometry')
    h[13] = zlib.crc32(entries) & 0xffffffff
    backup = list(h)
    backup[5], backup[6], backup[10] = h[6], 1, h[6] - 32
    return mbr + encode_header(h) + entries, bytes(entries) + encode_header(backup)


def decode_header(raw):
    require(len(raw) == 512, 'Truncated GPT header')
    h = list(HEADER.unpack_from(raw))
    require(h[0] == b'EFI PART' and h[1] == 0x10000 and h[2] == 92 and h[4] == 0, 'Unsupported GPT header')
    copy = bytearray(raw[:h[2]])
    struct.pack_into('<I', copy, 16, 0)
    require(zlib.crc32(copy) & 0xffffffff == h[3], 'GPT header CRC mismatch')
    return h


def read_gpt(stream, disk_bytes, *, hybrid_iso=False):
    require(disk_bytes >= 34 * 512 * 2 and disk_bytes % 512 == 0, 'Invalid disk size')
    stream.seek(0)
    mbr = stream.read(512)
    require(mbr[510:512] == b'\x55\xaa', 'Invalid protective MBR')
    h = decode_header(stream.read(512))
    require(h[5] == 1 and h[6] == disk_bytes // 512 - 1, 'GPT size/backup location mismatch')
    require(h[10] == 2 and h[12] == 128, 'Unsupported GPT entry format')
    require(h[11] == (248 if hybrid_iso else 128), 'Unexpected GPT entry count')
    stream.seek(h[10] * 512)
    entries = bytearray(stream.read(h[11] * 128))
    require(len(entries) == h[11] * 128 and zlib.crc32(entries) & 0xffffffff == h[13], 'GPT entry CRC mismatch')
    stream.seek(h[6] * 512)
    backup_h = decode_header(stream.read(512))
    require(backup_h[5] == h[6] and backup_h[6] == 1, 'GPT backup header mismatch')
    require(backup_h[7:10] == h[7:10] and backup_h[11:] == h[11:], 'GPT tables disagree')
    count_sectors = (len(entries) + 511) // 512
    require(h[7] >= 2 + count_sectors and h[7] <= h[8] < h[6] - count_sectors, 'GPT usable bounds overlap metadata')
    require(backup_h[10] == h[6] - count_sectors, 'Unexpected backup entry location')
    stream.seek(backup_h[10] * 512)
    backup_entries = stream.read(len(entries))
    require(backup_entries == entries, 'Primary and backup entries differ')
    stream.seek(0)
    primary = stream.read((2 + count_sectors) * 512)
    stream.seek(backup_h[10] * 512)
    secondary = stream.read((count_sectors + 1) * 512)
    result = GPT(h, entries, primary, secondary, disk_bytes)
    parts = result.partitions()
    require(len({p['partuuid'] for p in parts}) == len(parts), 'Duplicate partition GUID')
    require(len({p['name'] for p in parts}) == len(parts), 'Duplicate partition label')
    for p in parts:
        require(h[7] <= p['start_lba'] <= p['end_lba'] <= h[8], 'Partition outside usable bounds')
    ordered = sorted((p for p in parts if not (hybrid_iso and p['index'] == 2)), key=lambda p: p['start_lba'])
    require(all(a['end_lba'] < b['start_lba'] for a, b in zip(ordered, ordered[1:])), 'Overlapping partitions')
    return result
