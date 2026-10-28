"""Send a maintenance command to patched UART1, or print the frame offline.

Examples (nothing is sent without --serial or --tcp):
  python3 -I maintenance_client.py status
  python3 -I maintenance_client.py info
  python3 -I maintenance_client.py status --serial /dev/ttyUSB0
  python3 -I maintenance_client.py start --serial /dev/ttyUSB0
  python3 -I maintenance_client.py stop --tcp 192.0.2.1:8899

Current profiles: MAINT1.5.3/1.6.3; recognizes MNT02/03/04 and five-byte raw status; older status replies
are rejected. On UART1, INFO03 supports addressed packs0..21; status/start/stop remain master-only.
1.5.2/1.6.2 add addressed diagnostics (64/04, ten bytes, no writes) on UART0 and UART1.
On UART0 (1.5.1/1.6.1 and later), addressed status/stop/info use19200; start is unsupported. This tool never
sends 0x45 or bootloader frames and never flashes firmware.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT

import argparse
import json
import os
import select
import socket
import termios
import time


INFO = {"status": "02", "info": "03", "diagnostics": "04", "start": "01C35A", "stop": "00C35A"}


def valid_address(address):
    if type(address) is not int or not 0 <= address <= 21:
        raise ValueError("pack address must be an integer in 0..21")
    return address


def frame(code, info, address=0):
    valid_address(address)
    n = len(info)
    check = (-sum(((n >> 8) & 15, (n >> 4) & 15, n & 15))) & 15
    body = "20%02X46%02X%X%03X%s" % (address, code, check, n, info)
    checksum = (-sum(body.encode("ascii"))) & 0xFFFF
    return ("~%s%04X\r" % (body, checksum)).encode("ascii")


def normalize_uart(value):
    """Return canonical selectors; preserve existing API and CLI callers."""
    aliases = {"UART0": "UART0", "UART1": "UART1", "R": "UART0", "C": "UART1"}
    if value not in aliases:
        raise ValueError("UART must be UART0 or UART1")
    return aliases[value]


def request(action, address=0, uart="UART1"):
    valid_address(address)
    uart = normalize_uart(uart)
    if uart == "UART0" and action == "start":
        raise ValueError("Maintenance start is only available over UART1")
    if uart == "UART1" and address and action not in ("info", "diagnostics"):
        raise ValueError("Only info/diagnostics are available for nonzero pack addresses")
    return frame(0x64, INFO[action], address)


def parse_response(raw, address=0):
    valid_address(address)
    if not raw.startswith(b"~") or not raw.endswith(b"\r") or len(raw) < 18:
        raise ValueError("not a complete Seplos ASCII response")
    body = raw[1:-5].decode("ascii")
    checksum = int(raw[-5:-1], 16)
    if body[:6] != "20%02X46" % address or (sum(body.encode("ascii")) + checksum) & 0xFFFF:
        raise ValueError("unexpected header or checksum")
    length = int(body[9:12], 16)
    check = int(body[8], 16)
    if check != (-sum(((length >> 8) & 15, (length >> 4) & 15, length & 15))) & 15:
        raise ValueError("bad LENGTH nibble")
    if length != len(body[12:]) or length & 1:
        raise ValueError("bad INFO length")
    return int(body[6:8], 16), bytes.fromhex(body[12:])


def parse_info(info):
    """Decode immutable MNT02/17, MNT03/18 or MNT04/19-byte info."""
    if (len(info), info[:4]) not in ((17,b"MNT\x02"),(18,b"MNT\x03"),(19,b"MNT\x04")):
        raise ValueError("unknown maintenance info format or length")
    version_end = 10 if info[3] == 4 else 9
    result = {
        "base_version": ("%d.%02d.?" % (info[4],info[5])) if info[6]==255 else "%d.%02d.%02d" % (info[4],info[5],info[6]),
        "patch_version": ".".join(str(x) for x in info[7:version_end]),
        "build_id": info[version_end:version_end+8].hex(),
    }
    if info[3] >= 3:
        flags=info[-1]
        result.update(info_format=info[3],image_flags=flags,hard_stop=bool(flags&1),positive_flags=bool(flags&8))
        if info[3] == 4:
            result["uart0_marker"] = bool(flags&16)
            result["extended_diagnostics"] = bool(flags&32)
            result["checkpoint_before_reset"] = bool(flags&64)
            result["configurable_hard_stop"] = bool(flags&128)
            if flags&128:
                result["hard_stop_default"] = bool(flags&1)
                result["hard_stop"] = None  # Current state requires47/Group0.
    return result


def hard_stop_state(group0, image_flags, info_format=4):
    """Decode an actual Group0 read; bit0 is a default only with MNT04 bit7."""
    if type(group0) is not int or not 0<=group0<=255 or type(image_flags) is not int or not 0<=image_flags<=255:
        raise ValueError("Group0 and image flags must be bytes")
    if type(info_format) is not int or info_format not in (2,3,4):
        raise ValueError("unknown maintenance info format")
    default=bool(image_flags&1)
    if info_format!=4 or not image_flags&128:
        return dict(configurable=False,initialized=None,enabled=default,default_enabled=default,source="image")
    initialized=not bool(group0&128)
    return dict(configurable=True,initialized=initialized,
                enabled=bool(group0&64) if initialized else default,
                default_enabled=default,source="parameter" if initialized else "image-default")


def hard_stop_group0(group0, enabled):
    """Explicitly set bits7/6 to00/01, retaining all six existing lower bits."""
    if type(group0) is not int or not 0<=group0<=255 or type(enabled) is not bool:
        raise ValueError("expected a Group0 byte and a boolean selection")
    return (group0&0x3f)|(0x40 if enabled else 0)


def parse_diagnostics(info):
    """64/04 format1; classify raw records without causing OEM mirror repair."""
    if len(info) != 10 or info[0] != 1:
        raise ValueError("unknown diagnostic format or length")
    if any(info[i] > 2 for i in (1,2,3,4,5,6)) or any(info[i] not in (0,1,255) for i in (7,8)) or info[9]&~7:
        raise ValueError("unknown diagnostic status code or flags")
    classes=("erased", "valid", "invalid")
    comparisons=("not-comparable", "identical", "different")
    lock=lambda value: None if value==255 else bool(value)
    return dict(format=1,
        parameters=dict(primary=classes[info[1]],backup=classes[info[2]],comparison=comparisons[info[3]],primary_lock=lock(info[7]),backup_lock=lock(info[8])),
        soc=dict(primary=classes[info[4]],backup=classes[info[5]],comparison=comparisons[info[6]]),
        runtime_lock=bool(info[9]&1) if info[9]&4 else None,
        runtime_consistent=bool(info[9]&2) if info[9]&4 else None,
        runtime_magic_valid=bool(info[9]&4))


def parse_status(info):
    """Decode raw marker and effective slave count; unknown is never 'on'."""
    if len(info) != 5:
        raise ValueError("Expected five status bytes, got %r" % info)
    marker = int.from_bytes(info[:4], "little")
    marker_state = "off" if marker == 0xFFFFFFFF else (
        "on" if marker == 0 else "unexplained")
    return {
        "marker": marker,
        "marker_state": marker_state,
        "effective_slaves": info[4],
        "flag": 0 if marker_state == "off" else (1 if marker_state == "on" else None),
    }


def read_reply(read_chunk, sent, timeout=3):
    buffer = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = read_chunk(max(0, deadline - time.monotonic()))
        if not chunk:
            continue
        buffer += chunk
        while b"\r" in buffer:
            packet, buffer = buffer.split(b"\r", 1)
            packet += b"\r"
            if packet == sent:   # USB-RS485 adapter or gateway may echo TX
                continue
            try:
                return packet, parse_response(packet, address=int(sent[3:5], 16))
            except ValueError:
                continue
    raise TimeoutError("No valid 0x64 response within %.1f s" % timeout)


def exchange_serial(port, sent, timeout=3, baud=9600):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        if baud not in (9600,19200):
            raise ValueError("baud must be 9600 or 19200")
        attrs[4] = attrs[5] = termios.B19200 if baud==19200 else termios.B9600
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
        os.write(fd, sent)
        termios.tcdrain(fd)

        def receive(wait):
            ready, _, _ = select.select([fd], [], [], min(wait, 0.1))
            return os.read(fd, 4096) if ready else b""

        return read_reply(receive, sent, timeout)
    finally:
        os.close(fd)


def valid_tcp_endpoint(value):
    host, separator, port_text = value.rpartition(":")
    if not separator or not host or not port_text:
        raise argparse.ArgumentTypeError("expected HOST:PORT (for example, localhost:8899)")
    try:
        port = int(port_text, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("PORT must be a number from 1 to 65535") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("PORT must be a number from 1 to 65535")
    return value


def exchange_tcp(address, sent, timeout=3):
    host, port = address.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=timeout) as conn:
        conn.sendall(sent)

        def receive(wait):
            conn.settimeout(min(wait, 0.1))
            try:
                return conn.recv(4096)
            except socket.timeout:
                return b""

        return read_reply(receive, sent, timeout)


def wait_for_state(action, query_status, expected_slaves=None, timeout=3.0,
                   interval=0.5, now=time.monotonic, sleep=time.sleep):
    """Return a fresh status after the one-second DIP hook has taken effect."""
    deadline = now() + timeout
    started = now()
    last = None
    last_error = None
    while now() < deadline:
        sleep(min(interval, deadline - now()))
        remaining = deadline - now()
        if remaining <= 0:
            break
        try:
            last = query_status(min(interval, remaining))
        except OSError as error:
            last_error = error
            continue
        flag, slaves = last
        if action == "start" and (flag, slaves) == (1, 0):
            return last
        if action == "stop" and flag == 0:
            if expected_slaves is None and slaves > 0:
                return last
            if expected_slaves == slaves and (slaves > 0 or now() - started >= 1.1):
                return last
    if last is None:
        detail = "No valid status response received"
    elif action == "stop" and last[0] == 0:
        expected = expected_slaves if expected_slaves is not None else ">0"
        detail = ("Marker cleared (flag=0), but slave count %d; expected %s. "
                  "Check DIP settings" % (last[1], expected))
    elif action == "start" and last[0] == 1:
        detail = ("Marker set (flag=1), but effective slave count %d instead of 0. "
                  "Check DIP settings and automatic slave detection" % last[1])
    else:
        detail = "Maintenance state not reached (last status: %r)" % (last,)
    if last_error is not None:
        detail += "; last connection error: %s" % last_error
    raise TimeoutError("%s (after %.1f s)" % (detail, timeout))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=tuple(INFO))
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--serial", metavar="DEVICE", help="RS485 adapter; UART1 9600 or UART0 19200 8N1")
    transport.add_argument("--tcp", type=valid_tcp_endpoint, metavar="HOST:PORT",
                           help="RS485 Ethernet gateway; configure its baudrate for the selected UART")
    parser.add_argument("--uart", type=normalize_uart, choices=("UART0", "UART1"), default="UART1", help="UART0=RS485-1/2 at19200; UART1=CAN-socket RS485 at9600")
    parser.add_argument("--address", type=int, default=0, help="Target pack0..21; on UART1 nonzero with info/diagnostics")
    parser.add_argument("--no-wait", action="store_true", help="show the immediate ACK without waiting for the DIP update")
    parser.add_argument("--expected-slaves", type=int, metavar="N", help="expected physical slave count after stop (0..15); default: any positive count")
    args = parser.parse_args()
    if args.expected_slaves is not None:
        if args.action != "stop" or not 0 <= args.expected_slaves <= 15:
            parser.error("--expected-slaves requires stop and a value from 0 to 15")
    try:
        sent = request(args.action, args.address, uart=args.uart)
    except ValueError as error:
        parser.error(str(error))
    print("TX", sent.decode("ascii").rstrip("\r"))
    if not args.serial and not args.tcp:
        print("No port selected; nothing sent.")
        return
    if args.uart == "UART0" and args.expected_slaves is not None:
        parser.error("--expected-slaves is only supported on UART1")
    exchange = (lambda packet, timeout=3: exchange_serial(args.serial, packet, timeout, baud=19200) if args.uart=="UART0" else exchange_serial(args.serial, packet, timeout)) if args.serial else (
        lambda packet, timeout=3: exchange_tcp(args.tcp, packet, timeout))
    try:
        raw, (rtn, info) = exchange(sent)
    except (OSError, ValueError) as error:
        raise SystemExit("Connection or response failed: %s" % error) from error
    print("RX", raw.decode("ascii", "replace").rstrip("\r"))
    if rtn:
        raise SystemExit("BMS returned RTN %02X" % rtn)
    if args.action == "diagnostics":
        try:print(json.dumps(parse_diagnostics(info),indent=2))
        except ValueError as error:raise SystemExit(str(error)) from error
        return
    if args.action == "info":
        try:
            details = parse_info(info)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print("base=%s patch=%s build-id=%s" % (
            details["base_version"], details["patch_version"], details["build_id"]))
        if "hard_stop" in details:
            hard_stop=("configurable (default=%s; state requires Group0)" % ("on" if details["hard_stop_default"] else "off")) if details.get("configurable_hard_stop") else ("on" if details["hard_stop"] else "off")
            print("info-format=%d image-flags=0x%02X hard-stop=%s positive-flags=%s" % (details["info_format"], details["image_flags"], hard_stop, "yes" if details["positive_flags"] else "no"))
        if "extended_diagnostics" in details:
            print("diagnostics=%s checkpoint-before-reset=%s" % ("yes" if details["extended_diagnostics"] else "no", "yes" if details["checkpoint_before_reset"] else "no"))
        return
    try:
        details = parse_status(info)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.action in ("start", "stop") and details["flag"] is None:
        raise SystemExit("Unexplained maintenance marker %08X" % details["marker"])
    if args.uart == "UART0" and args.action == "stop":
        if details["flag"] != 0:
            raise SystemExit("Marker was not cleared")
        print("marker=%08X (%s) effective-slaves=%d" % (details["marker"],details["marker_state"],details["effective_slaves"]))
        print("UART0 ACK confirms marker readback; polling/DIP transition is not asserted.")
        return
    if args.action in ("start", "stop") and not args.no_wait:
        def query_status(remaining):
            _, (status_rtn, status_info) = exchange(request("status"), remaining)
            if status_rtn:
                raise ValueError("Invalid status reply: RTN %02X, INFO %r" %
                                 (status_rtn, status_info))
            status = parse_status(status_info)
            if status["flag"] is None:
                raise ValueError("Unexplained maintenance marker %08X" % status["marker"])
            return status["flag"], status["effective_slaves"]

        try:
            result = wait_for_state(args.action, query_status, args.expected_slaves)
        except (TimeoutError, ValueError) as error:
            raise SystemExit(str(error)) from error
        # The waiter only returns a known marker state, confirmed by a fresh 02.
        details = parse_status((bytes(4) if result[0] else b"\xff" * 4) + bytes([result[1]]))
    print("marker=%08X (%s) effective-slaves=%d" % (
        details["marker"], details["marker_state"], details["effective_slaves"]))


if __name__ == "__main__":
    main()
