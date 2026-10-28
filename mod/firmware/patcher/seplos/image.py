"""Strict Seplos pseudo-header plus Intel HEX container, independent of versions."""
from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import struct
import re


class ImageError(ValueError):
    pass


def record(address, kind, data):
    raw = bytes([len(data)]) + address.to_bytes(2, 'big') + bytes([kind]) + data
    return ':' + (raw + bytes([-sum(raw) & 255])).hex().upper()


@dataclass(frozen=True)
class Image:
    header: tuple[str, ...]
    app: bytes
    tail: tuple[str, ...]

    @property
    def sp(self):
        return struct.unpack_from('<I', self.app)[0]

    @property
    def sha(self):
        return hashlib.sha256(self.app).hexdigest()

    def with_app(self, app):
        return replace(self, app=bytes(app))

    @classmethod
    def read(cls, path):
        return cls.parse(Path(path).read_text(encoding='ascii'))

    @classmethod
    def parse(cls, text):
        lines = text.splitlines()
        if len(lines) < 20:
            raise ImageError('truncated Seplos container')
        header = tuple(lines[:16])
        try:
            if not all(re.fullmatch(r':10000000[0-9A-F]{32}AA', s) for s in header):
                raise ImageError('invalid Seplos pseudo-header')
            data = b''.join(bytes.fromhex(s[9:-2]) for s in header)
            if not data.startswith(b'SWM181RCT6_64_M0EMU1101_10D_HW16RS485'):
                raise ImageError('unsupported hardware family')
            app, tail = bytearray(), []
            for line in lines[16:]:
                if not re.fullmatch(r':[0-9A-Fa-f]+',line) or len(line)%2 != 1:
                    raise ImageError('invalid Intel HEX prefix')
                raw = bytes.fromhex(line[1:])
                if len(raw) < 5 or len(raw) != raw[0] + 5 or sum(raw) & 255:
                    raise ImageError('Intel HEX checksum/length error')
                address, kind = int.from_bytes(raw[1:3], 'big'), raw[3]
                if kind == 0:
                    if tail or address != len(app) or not 1 <= raw[0] <= 16:
                        raise ImageError('overlapping/noncontiguous app records')
                    app.extend(raw[4:-1])
                elif kind in (1, 5):
                    tail.append(line.upper())
                else:
                    raise ImageError('unsupported Intel HEX record type')
            if tail != [':04000005000000C136', ':00000001FF']:
                raise ImageError('invalid entry/EOF records')
            if not 0x1000 <= len(app) < 0x10000 or len(app) & 3:
                raise ImageError('unsupported app extent/alignment')
            sp, reset = struct.unpack_from('<II', app)
            if not 0x20001000 <= sp <= 0x20004000 or sp & 7:
                raise ImageError('invalid initial stack pointer')
            if not reset & 1 or not 0xC0 <= (reset & ~1) < len(app):
                raise ImageError('invalid reset vector')
        except (ValueError, IndexError) as exc:
            if isinstance(exc, ImageError):
                raise
            raise ImageError(str(exc)) from exc
        return cls(header, bytes(app), tuple(tail))

    def render(self):
        if len(self.app) >= 0x10000:
            raise ImageError('16-bit app address range exceeded')
        return '\n'.join((*self.header, *(record(i, 0, self.app[i:i+16]) for i in range(0, len(self.app), 16)), *self.tail)) + '\n'
