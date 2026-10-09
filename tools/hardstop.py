"""Hard stop: set the event-6 mask in "charging forbidden" from 0x71 to 0x73 in a .ehex file.

This is the one-byte difference between 16.06.04 and 16.06.05 (SP80). With 0x73 a pack that is
"Intermittent recharge waiting" also opens its charge MOSFET.

    python3 -I hardstop.py <in.ehex> <offset hex> <out.ehex>

Known offsets (image address of the 0x71 byte): 16.06.04 658A, 16.06.11 6EA0, 16.06.12 6EA0,
16.06.13 706C. The script refuses to patch unless the expected instruction sequence is found:
ldr rX,[pc,#..] loading 0x20000035 (alarm event 6); movs r4,#0x71; ldrb rX,[rX]; tst rX,r4; bne.
"""
import struct
import sys

EVENT6 = 0x20000035  # RAM address of alarm event 6
HEADER_RECORDS = 16


class PatchError(Exception):
    pass


def records(text):
    """Yield (line_index, absolute_address, data, record_type) for every Intel HEX record after the header.

    The header must be exactly 16 pseudo records; every record after it must have a valid checksum.
    """
    base = 0
    seen = 0
    for i, line in enumerate(text.split("\n")):
        line = line.strip("\r")
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        addr, rtype, data = (raw[1] << 8) | raw[2], raw[3], raw[4:4 + raw[0]]
        seen += 1
        # The vendor header is exactly 16 pseudo records ":10 0000 00 <16 bytes> AA" (invalid checksum).
        if seen <= HEADER_RECORDS:
            if raw[0] != 0x10 or addr != 0 or rtype != 0 or raw[-1] != 0xAA or len(raw) != 21:
                raise PatchError(f"line {i} is not a vendor header record")
            continue
        if (sum(raw) & 0xFF) != 0:
            raise PatchError(f"bad checksum in line {i}")
        if rtype == 4:
            base = ((data[0] << 8) | data[1]) << 16
        elif rtype == 2:
            base = ((data[0] << 8) | data[1]) << 4
        yield i, base + addr, data, rtype


def decode(text):
    image = {}
    for _, a, data, t in records(text):
        if t == 0:
            for k, b in enumerate(data):
                image[a + k] = b
    return image


def read_bytes(image, start, length):
    try:
        return bytes(image[start + k] for k in range(length))
    except KeyError as e:
        raise PatchError(f"address 0x{e.args[0]:X} not in image") from None


def check_context(image, offset):
    """Require exactly: ldr rX,[pc,#imm] -> EVENT6; movs r4,#0x71; ldrb rX,[rX,#0]; tst rX,r4; bne."""
    ctx = read_bytes(image, offset - 2, 10)
    ldr, movs, ldrb, tst, bne = (struct.unpack_from("<H", ctx, k)[0] for k in range(0, 10, 2))
    rx = (ldr >> 8) & 7
    ok = (
        ldr & 0xF800 == 0x4800  # ldr rX,[pc,#imm8*4]
        and movs == 0x2471  # movs r4,#0x71
        and ldrb == 0x7800 | (rx << 3) | rx  # ldrb rX,[rX,#0]
        and tst == 0x4200 | (4 << 3) | rx  # tst rX,r4
        and bne & 0xFF00 == 0xD100  # bne
    )
    if not ok:
        raise PatchError(f"unexpected instruction sequence: {ctx.hex(' ')}")
    literal = ((offset - 2 + 4) & ~3) + (ldr & 0xFF) * 4
    target = struct.unpack("<I", read_bytes(image, literal, 4))[0]
    if target != EVENT6:
        raise PatchError(f"ldr loads 0x{target:08X}, expected alarm event 6 at 0x{EVENT6:08X}")
    return ctx


def patch(raw, offset, old, new):
    lines = raw.decode("ascii").split("\n")
    done = False
    for i, a, data, t in records(raw.decode("ascii")):
        if t == 0 and a <= offset < a + len(data):
            k = offset - a
            if data[k] != old:
                raise PatchError(f"expected 0x{old:02X} at 0x{offset:X}, found 0x{data[k]:02X}")
            cr = lines[i].endswith("\r")
            rec = bytearray(bytes.fromhex(lines[i].strip("\r")[1:]))
            rec[4 + k] = new
            rec[-1] = (-sum(rec[:-1])) & 0xFF
            lines[i] = ":" + rec.hex().upper() + ("\r" if cr else "")
            done = True
    if not done:
        raise PatchError(f"offset 0x{offset:X} not found")
    return "\n".join(lines).encode("ascii")


if __name__ == "__main__":
    src, offset, dst = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    raw = open(src, "rb").read()
    try:
        ctx = check_context(decode(raw.decode("ascii")), offset)
        out = patch(raw, offset, 0x71, 0x73)
    except PatchError as e:
        sys.exit(f"refusing to patch: {e}")
    open(dst, "wb").write(out)
    diff = [k for k in range(len(raw)) if raw[k] != out[k]]
    print(f"context {ctx.hex(' ')}; {len(diff)} characters changed (byte + line checksum); "
          f"image byte now 0x{read_bytes(decode(out.decode('ascii')), offset, 1)[0]:02X}")
