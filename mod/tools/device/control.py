"""Send one 0x45 control frame (lab board only) and print the raw answer.

Usage: python3 -I ctl45.py <port> <adr-hex> <type-hex> <param-hex>
INFO = 00 <type> <param>; 19200 baud (pack bus).
"""
import os
import select
import sys
import termios
import time


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
    parser.add_argument('port');parser.add_argument('adr_hex');parser.add_argument('type_hex');parser.add_argument('param_hex')
    args=parser.parse_args()
    port, adr, typ, par = args.port, int(args.adr_hex,16), int(args.type_hex,16), int(args.param_hex,16)
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attr = termios.tcgetattr(fd)
        attr[0] = attr[1] = attr[3] = 0
        attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attr[4] = attr[5] = termios.B19200
        termios.tcsetattr(fd, termios.TCSANOW, attr)
        termios.tcflush(fd, termios.TCIOFLUSH)
        req = frame(adr, 0x45, "00%02X%02X" % (typ, par))
        os.write(fd, req)
        print(time.strftime("%H:%M:%S"), "TX", req.decode().strip())
        buf, end = b"", time.time() + 1.5
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                buf += os.read(fd, 1024)
                if buf.endswith(b"\r"):
                    break
        print(time.strftime("%H:%M:%S"), "RX", buf.decode("ascii", "replace").strip() if buf else "(no reply)")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
