"""Send one read-only Seplos ASCII request and print the raw answer.

Usage: python3 -I seplos_query.py <port> <baud> <adr-hex> <cid2-hex> [info-hex]
Only intended for read commands (0x42, 0x44, 0x47, 0x51, ...).
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import os
import select
import sys
import termios
import time

READ_ONLY = {0x42, 0x44, 0x47, 0x4B, 0x4D, 0x51, 0xA2, 0xA4}


def frame(adr, cid2, info=""):
    info = info.upper()
    n = len(info)
    lchk = (~(((n >> 8) & 0xF) + ((n >> 4) & 0xF) + (n & 0xF)) + 1) & 0xF
    body = "20%02X46%02X%X%03X%s" % (adr, cid2, lchk, n, info)
    chk = (~sum(body.encode()) + 1) & 0xFFFF
    return ("~%s%04X\r" % (body, chk)).encode()


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port');parser.add_argument('baud',type=int,choices=(9600,19200));parser.add_argument('adr_hex');parser.add_argument('cid2_hex');parser.add_argument('info_hex',nargs='?',default='')
    args=parser.parse_args()
    port, baud = args.port, args.baud
    adr, cid2 = int(args.adr_hex,16), int(args.cid2_hex,16)
    info = args.info_hex
    if cid2 not in READ_ONLY:
        sys.exit("refusing non-read command 0x%02X" % cid2)
    speeds = {9600: termios.B9600, 19200: termios.B19200}
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attr = termios.tcgetattr(fd)
        attr[0] = 0                                   # iflag
        attr[1] = 0                                   # oflag
        attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attr[3] = 0                                   # lflag (raw)
        attr[4] = attr[5] = speeds[baud]
        termios.tcsetattr(fd, termios.TCSANOW, attr)
        termios.tcflush(fd, termios.TCIOFLUSH)
        req = frame(adr, cid2, info)
        os.write(fd, req)
        print("TX", req.decode().strip())
        buf = b""
        end = time.time() + 1.5
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                buf += os.read(fd, 1024)
                if buf.endswith(b"\r"):
                    break
        print("RX", buf.decode("ascii", "replace").strip() if buf else "(no reply)")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
