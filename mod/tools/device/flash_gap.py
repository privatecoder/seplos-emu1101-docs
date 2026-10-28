"""Flash a validated Seplos BMS 2.0/10E/V16 (EMU1101) image over isolated UART0.

Same stream/blocks/frames as FirmwareUpdate.exe (analysis/protocols/bootloader-update-protocol.md);
only the fixed 350 ms pause is replaced by <gap-ms>. Aborts on anything but the expected ACK.

Usage: python3 -I flash_gap.py PORT IMAGE GAP_MS NEW_LOG [--address N]

Address is decimal 0..21; default 0 preserves the original CLI. Query, reset
and application verification target that address. Bootloader traffic itself
is unaddressed: connect exactly one pack. NEW_LOG must not already exist.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PATCHER_ROOT
import os
import select
import sys
import termios
import time
import importlib.util

_sys.path.insert(0, str(PATCHER_ROOT))
from seplos.image import Image

_spec = importlib.util.spec_from_file_location("flash_boot_entry", _Path(__file__).with_name("boot_entry.py"))
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def ascii_frame(ver, adr, cid2, info=""):
    n = len(info)
    lchk = (~(((n >> 8) & 0xF) + ((n >> 4) & 0xF) + (n & 0xF)) + 1) & 0xF
    body = "%02X%02X46%02X%X%03X%s" % (ver, adr, cid2, lchk, n, info)
    return ("~%s%04X\r" % (body, (-sum(body.encode())) & 0xFFFF)).encode()


def boot_frame(cmd, adr=0, data=b""):
    body = cmd + len(data).to_bytes(2, "big") + adr.to_bytes(2, "big") + data
    return b"::::" + body + ((-sum(body)) & 0xFFFF).to_bytes(2, "big") + b"\r" * 4


def stream_of(path):
    """Validate the full EHEX before reproducing the OEM record-data stream."""
    image = Image.read(path)
    header = b"".join(bytes.fromhex(line[9:-2]) for line in image.header)
    tail = b"".join(bytes.fromhex(line[9:-2]) for line in image.tail)
    return header + image.app + tail


class Port:
    def __init__(self, path, log):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            a = termios.tcgetattr(self.fd)
            a[0] = a[1] = a[3] = 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = termios.B19200
            termios.tcsetattr(self.fd, termios.TCSANOW, a)
        except BaseException:
            os.close(self.fd)
            raise
        self.log = log

    def close(self):
        os.close(self.fd)

    def stamp(self, tag, data):
        self.log.write("%d %s %s\n" % (time.time() * 1000, tag, data.hex().upper()))

    def send(self, data, discard_pending=True):
        if discard_pending:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        self.stamp("TX", data)
        os.write(self.fd, data)
        termios.tcdrain(self.fd)

    def read_until(self, done, timeout):
        buf, end = b"", time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.005)
            if r:
                buf += os.read(self.fd, 1024)
                if done(buf):
                    break
        if buf:
            self.stamp("RX", buf)
        return buf


def application_info(port, address, timeout):
    """Read a complete, checksummed 0x51 reply from the selected pack."""
    port.send(ascii_frame(0x20, address, 0x51))
    raw = port.read_until(lambda data: data.endswith(b"\r"), timeout)
    result, info = entry.ascii.parse_response(raw, address)
    if result or len(info) < 12:
        raise ValueError("Invalid 0x51 response or incomplete version information")
    return info


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port')
    parser.add_argument('image')
    parser.add_argument('gap_ms', type=int)
    parser.add_argument('log')
    parser.add_argument('--address', type=int, default=0, metavar='N',
                        help='Decimal pack address 0..21 (default: 0 for compatibility)')
    args = parser.parse_args()
    try:
        entry.ascii.valid_address(args.address)
        if args.gap_ms < 0:
            raise ValueError('gap_ms must be nonnegative')
    except ValueError as error:
        parser.error(str(error))
    gap = args.gap_ms / 1000
    stream = stream_of(args.image)
    blocks = [stream[i:i + 256].ljust(256, b"\0") for i in range(0, len(stream), 256)]
    plan = [(b"WFE", 0, b"")] + [(b"WFD", 16 * i, block) for i, block in enumerate(blocks)] + [(b"WFG", 0, b"")]
    frames = [boot_frame(command, address, data) for command, address, data in plan]
    with open(args.log, 'x') as log:
        port = Port(args.port, log)
        try:
            application_info(port, args.address, .6)
            started = time.monotonic()
            entry.enter(port, args.address)
            time.sleep(gap)
            log.write("STATE gap=%d ms, sending W F E\n" % args.gap_ms)
            for number, (frame, (command, _, _)) in enumerate(zip(frames, plan)):
                port.send(frame)
                reply = port.read_until(lambda raw: raw.endswith(b"\r" * 4), 10)
                try:
                    entry.validate_write_ack(reply)
                except ValueError:
                    log.write("STATE ABORT at %s %d: %r\n" % (command, number, reply))
                    raise
                log.flush()
                if command != b"WFG":
                    time.sleep(gap)
            elapsed = time.monotonic() - started
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    info = application_info(port, args.address, .3)
                except ValueError:
                    time.sleep(.1)
                    continue
                log.write("STATE done; app back\n")
                print("OK: %d blocks, elapsed %.1f s (reset to W F G), version %s, application after %.1f s" % (
                    len(blocks), elapsed, info[10:12].hex(), time.monotonic() - started))
                return
            raise SystemExit("Application did not return")
        finally:
            port.close()


if __name__ == "__main__":
    main()
