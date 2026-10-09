"""Hard stop: set the event-6 mask in "charging forbidden" from 0x71 to 0x73 in a .ehex file.

This is the one-byte difference between 16.06.04 and 16.06.05 (SP80). With 0x73 a pack that is
"Intermittent recharge waiting" also opens its charge MOSFET.

    python3 -I hardstop.py <in.ehex> <offset hex> <out.ehex>

Known offsets (image address of the 0x71 byte): 16.06.04 658A, 16.06.11 6EA0, 16.06.12 6EA0,
16.06.13 706C. The script refuses to patch unless the expected instruction sequence is found:
ldr rX,[pc,#..]; movs r4,#0x71; ldrb rX,[rX]; tst rX,r4; bne.
"""
import sys


def records(text):
    """Yield (line_index, absolute_address, data, record_type) for every Intel HEX record after the header."""
    base = 0
    in_header = True
    for i, line in enumerate(text.split("\n")):
        line = line.strip("\r")
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        addr, rtype, data = (raw[1] << 8) | raw[2], raw[3], raw[4:4 + raw[0]]
        valid = (sum(raw) & 0xFF) == 0
        # The vendor header is a block of 16 leading pseudo records with dummy checksum "AA".
        if in_header and not valid:
            continue
        in_header = False
        assert valid, f"bad checksum in line {i}"
        if rtype == 4:
            base = ((data[0] << 8) | data[1]) << 16
        elif rtype == 2:
            base = ((data[0] << 8) | data[1]) << 4
        yield i, base + addr, data, rtype


def read_bytes(text, start, length):
    image = {}
    for _, a, data, t in records(text):
        if t == 0:
            for k, b in enumerate(data):
                image[a + k] = b
    return bytes(image[start + k] for k in range(length))


def check_context(ctx):
    """ctx starts 2 bytes before the 0x71: ldr(lit) / movs r4,#0x71 / ldrb / tst / bne."""
    ok = (ctx[1] & 0xF8) == 0x48 and ctx[2:4] == b"\x71\x24" and ctx[5] == 0x78 and ctx[7] == 0x42 and ctx[9] == 0xD1
    assert ok, f"unexpected instruction sequence: {ctx.hex(' ')}"


def patch(raw, offset, old, new):
    lines = raw.decode("ascii").split("\n")
    done = False
    for i, a, data, t in records(raw.decode("ascii")):
        if t == 0 and a <= offset < a + len(data):
            k = offset - a
            assert data[k] == old, f"expected 0x{old:02X} at 0x{offset:X}, found 0x{data[k]:02X}"
            cr = lines[i].endswith("\r")
            rec = bytearray(bytes.fromhex(lines[i].strip("\r")[1:]))
            rec[4 + k] = new
            rec[-1] = (-sum(rec[:-1])) & 0xFF
            lines[i] = ":" + rec.hex().upper() + ("\r" if cr else "")
            done = True
    assert done, f"offset 0x{offset:X} not found"
    return "\n".join(lines).encode("ascii")


if __name__ == "__main__":
    src, offset, dst = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    raw = open(src, "rb").read()
    ctx = read_bytes(raw.decode("ascii"), offset - 2, 10)
    check_context(ctx)
    out = patch(raw, offset, 0x71, 0x73)
    open(dst, "wb").write(out)
    diff = [k for k in range(len(raw)) if raw[k] != out[k]]
    print(f"context {ctx.hex(' ')}; {len(diff)} characters changed (byte + line checksum); "
          f"image byte now 0x{read_bytes(out.decode('ascii'), offset, 1)[0]:02X}")
