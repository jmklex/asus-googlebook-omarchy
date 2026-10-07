"""Minimal newc writer and reader, including concatenated early CPIO archives."""
from .common import require


def archive(files):
    data = bytearray()
    for ino, (name, (mode, body)) in enumerate(list(files.items()) + [('TRAILER!!!', (0, b''))], 1):
        require(not name.startswith('/') and '..' not in name.split('/'), 'Unsafe CPIO path')
        name = name.encode() + b'\0'
        vals = [ino, mode, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(name), 0]
        data += b'070701' + ''.join(f'{v:08x}' for v in vals).encode() + name
        data += bytes((-len(data)) % 4)
        data += body
        data += bytes((-len(data)) % 4)
    return bytes(data) + bytes((-len(data)) % 512)


def members(data):
    """Read one uncompressed archive and return its members and end offset."""
    offset = 0
    result = {}
    while True:
        require(data[offset:offset + 6] in (b'070701', b'070702'), 'Invalid newc header')
        fields = [int(data[offset + 6 + 8*i:offset + 14 + 8*i], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        require(0 < namesize < 4096, 'Invalid CPIO name')
        start = offset + 110
        require(data[start + namesize - 1:start + namesize] == b'\0', 'Unterminated CPIO name')
        name = data[start:start + namesize - 1].decode()
        offset = (start + namesize + 3) & ~3
        require(offset + size <= len(data), 'Truncated CPIO payload')
        if name == 'TRAILER!!!':
            return result, offset
        result[name] = (fields[1], data[offset:offset + size])
        offset = (offset + size + 3) & ~3


def find_member(initrd, name, decompress):
    offset = 0
    found = None
    while offset < len(initrd):
        while offset < len(initrd) and initrd[offset] == 0:
            offset += 1
        if offset == len(initrd):
            break
        if initrd[offset:offset + 6] in (b'070701', b'070702'):
            files, end = members(initrd[offset:])
            if name in files:
                found = files[name][1]
            offset += end
        else:
            # Omarchy 4.0.4: early uncompressed firmware archive followed by zstd.
            require(initrd[offset:offset+4] == b'\x28\xb5\x2f\xfd', 'Unsupported initramfs compression')
            files, _ = members(decompress(initrd[offset:]))
            if name in files:
                found = files[name][1]
            break
    require(found is not None, f'Missing initramfs member: {name}')
    return found
