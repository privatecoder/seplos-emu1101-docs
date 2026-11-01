"""Send a maintenance command to patched UART1, or print the frame offline.

Examples (nothing is sent without --serial or --tcp):
  python3 -I maintenance_client.py status
  python3 -I maintenance_client.py info
  python3 -I maintenance_client.py status --serial /dev/ttyUSB0
  python3 -I maintenance_client.py start --serial /dev/ttyUSB0
  python3 -I maintenance_client.py stop --tcp 192.0.2.1:8899

Current profiles: MAINT1.5.4/1.6.4; recognizes MNT02/03/04/05 and five-byte raw status; older status replies
are rejected. On UART1, INFO03 supports addressed packs0..21; status/start/stop remain master-only.
1.5.2/1.6.2 add addressed diagnostics (64/04, ten bytes, no writes) on UART0 and UART1.
1.5.4/1.6.4 add one-record history, calibration pages and checkpoint/live energy reads.
History shares the UART0/UART1 cursor; do not interleave independent readers. These
reads are snapshots, not guaranteed next-boot SOC or an atomic history download.
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


INFO = {"status": "02", "info": "03", "diagnostics": "04", "start": "01C35A", "stop": "00C35A",
        "calibration-active": "0500", "calibration-primary": "0501",
        "calibration-backup": "0502", "checkpoint-energy": "06"}
HISTORY = {"history-oldest": "0000", "history-next": "0001"}
READ_ACTIONS = frozenset(("info", "diagnostics", *HISTORY,
                          "calibration-active", "calibration-primary", "calibration-backup", "checkpoint-energy"))


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
    if uart == "UART1" and address and action not in READ_ACTIONS:
        raise ValueError("Only addressed read commands are available for nonzero pack addresses")
    if action in HISTORY:
        return frame(0x4B, HISTORY[action], address)
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
    """Decode MNT02/03/04 and MNT05 with explicit capability bits."""
    if (len(info), info[:4]) not in ((17,b"MNT\x02"),(18,b"MNT\x03"),(19,b"MNT\x04"),(21,b"MNT\x05")):
        raise ValueError("unknown maintenance info format or length")
    version_end = 10 if info[3] >= 4 else 9
    result = {
        "base_version": ("%d.%02d.?" % (info[4],info[5])) if info[6]==255 else "%d.%02d.%02d" % (info[4],info[5],info[6]),
        "patch_version": ".".join(str(x) for x in info[7:version_end]),
        "build_id": info[version_end:version_end+8].hex(),
    }
    if info[3] >= 3:
        flags=info[18] if info[3] >= 4 else info[17]
        result.update(info_format=info[3],image_flags=flags,hard_stop=bool(flags&1),positive_flags=bool(flags&8))
        if info[3] >= 4:
            result["uart0_marker"] = bool(flags&16)
            result["extended_diagnostics"] = bool(flags&32)
            result["checkpoint_before_reset"] = bool(flags&64)
            result["configurable_hard_stop"] = bool(flags&128)
            if flags&128:
                result["hard_stop_default"] = bool(flags&1)
                result["hard_stop"] = None  # Current state requires47/Group0.
    if info[3] == 5:
        caps = int.from_bytes(info[19:21], "big")
        if caps & ~0x000f:
            raise ValueError("unknown maintenance capability bits")
        result.update(capabilities=caps, uart1_history=bool(caps & 1),
                      calibration_pages=bool(caps & 2), persisted_soc_contents=bool(caps & 4),
                      full_width_energy=bool(caps & 8))
    return result


def hard_stop_state(group0, image_flags, info_format=4):
    """Decode an actual Group0 read; bit0 is a default with MNT04/05 bit7."""
    if type(group0) is not int or not 0<=group0<=255 or type(image_flags) is not int or not 0<=image_flags<=255:
        raise ValueError("Group0 and image flags must be bytes")
    if type(info_format) is not int or info_format not in (2,3,4,5):
        raise ValueError("unknown maintenance info format")
    default=bool(image_flags&1)
    if info_format<4 or not image_flags&128:
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


def parse_history(info):
    """Decode one 4B response only; never advance the shared history cursor."""
    if not info:
        return {"empty": True}
    if len(info) != 97 or info[0] != 1 or info[1] not in (0, 1):
        raise ValueError("unknown history format, flag or length")
    return dict(format=1, empty=False, last_record=bool(info[1]),
                year=int.from_bytes(info[2:4], "big"), record_tail_hex=info[4:].hex())


def _calibration_fields(raw):
    """Decode expected A0/51 record fields; native stored values are LE."""
    value = lambda offset, size=2, signed=False: int.from_bytes(raw[offset:offset+size], "little", signed=signed)
    return dict(invalid_flags=raw[2], cell_gains=[value(3+2*i) for i in range(16)],
                voltage_gains=[value(35), value(37)], current_gains=[value(39), value(45)],
                zero_raw=[value(41, 4, True), value(47, 4, True)], crc=value(51))


def parse_calibration(info):
    """64/05 snapshot: active values are BE; stored raw records retain LE.

    Classification and native CRC acceptance are separate firmware observations.
    Neither establishes physical calibration accuracy. Unexpected record shapes
    remain visible as raw prefixes and are not interpreted as expected fields.
    """
    if len(info) < 2 or info[0] != 1 or info[1] not in (0, 1, 2):
        raise ValueError("unknown calibration format or page")
    if info[1] == 0:
        if len(info) != 72 or info[2] & ~0x1c or info[3] > 16:
            raise ValueError("unknown active calibration length, flags or cell count")
        value = lambda offset, size=2, signed=False: int.from_bytes(info[offset:offset+size], "big", signed=signed)
        return dict(format=1, page="active", invalid_flags=info[2], cell_count=info[3],
                    cell_gains=[value(4+2*i) for i in range(16)],
                    voltage_gains=[value(36), value(38)], current_gains=[value(40), value(42)],
                    zero_raw=[value(44, 4, True), value(48, 4, True)],
                    references=[value(52), value(54)],
                    raw_currents=[value(56, 4, True), value(60, 4, True)],
                    converted_currents_ma=[value(64, 4, True), value(68, 4, True)])
    if len(info) != 58 or info[2] > 2 or info[3] not in (0, 1):
        raise ValueError("unknown stored calibration length or status")
    raw = info[5:58]
    if info[4] != raw[1] or (info[2] == 1 and (raw[:2] != b"\xa0\x33" or not info[3])):
        raise ValueError("inconsistent stored calibration metadata")
    return dict(format=1, page="primary" if info[1] == 1 else "backup",
                classification=("erased", "valid", "invalid")[info[2]],
                native_crc_accepted=bool(info[3]), declared_length=info[4],
                raw_prefix_hex=raw.hex(), fields=_calibration_fields(raw) if info[2] == 1 else None)


def parse_checkpoint_energy(info):
    """64/06 stored records and coherent live snapshot, not guaranteed boot SOC.

    The firmware may later checkpoint or modify parameters. Native CRC acceptance
    determines the observed boot choice independently of strict A0/20 shape.
    Energy counters are unsigned u32 in 0.1kWh, without OEM42's 65000 fallback.
    """
    if len(info) != 68 or info[0] != 1:
        raise ValueError("unknown checkpoint/energy format or length")
    if any(info[i] > 2 for i in (1, 2, 3, 5)) or info[4] & ~3:
        raise ValueError("unknown checkpoint/energy status")
    value = lambda offset, size=2: int.from_bytes(info[offset:offset+size], "big")
    def stored(offset, classification, accepted):
        raw = info[offset:offset+22]
        if classification == 1 and (raw[:2] != b"\xa0\x14" or not accepted):
            raise ValueError("inconsistent checkpoint metadata")
        fields = None
        if classification == 1:
            little = lambda position, size=2: int.from_bytes(raw[position:position+size], "little")
            fields = dict(remaining_cah=little(2), full_cah=little(4),
                          charged_energy_dkwh=little(6, 4), discharged_energy_dkwh=little(10, 4),
                          cycles=little(14), soc_cycle_reference_tenths=little(16),
                          soc_decrease_tenths=little(18), crc=little(20))
        return dict(classification=("erased", "valid", "invalid")[classification],
                    native_crc_accepted=bool(accepted), raw_hex=raw.hex(), fields=fields)
    return dict(format=1, comparison=("not-comparable", "identical", "different")[info[3]],
                native_crc_accept_mask=info[4], boot_choice=("fallback", "primary", "backup")[info[5]],
                live=dict(p58_full_cah=value(6), p59_remaining_cah=value(8),
                          charged_energy_dkwh=value(10, 4), discharged_energy_dkwh=value(14, 4),
                          remaining_cah=value(18), full_cah=value(20), soc_tenths=value(22)),
                primary=stored(24, info[1], info[4] & 1), backup=stored(46, info[2], info[4] & 2))


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
    raise TimeoutError("No valid response within %.1f s" % timeout)


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
    parser.add_argument("action", choices=(*INFO, *HISTORY))
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--serial", metavar="DEVICE", help="RS485 adapter; UART1 9600 or UART0 19200 8N1")
    transport.add_argument("--tcp", type=valid_tcp_endpoint, metavar="HOST:PORT",
                           help="RS485 Ethernet gateway; configure its baudrate for the selected UART")
    parser.add_argument("--uart", type=normalize_uart, choices=("UART0", "UART1"), default="UART1", help="UART0=RS485-1/2 at19200; UART1=CAN-socket RS485 at9600")
    parser.add_argument("--address", type=int, default=0, help="Target pack0..21; on UART1 nonzero with addressed read commands")
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
    decoder = (parse_history if args.action in HISTORY else
               parse_calibration if args.action.startswith("calibration-") else
               parse_checkpoint_energy if args.action == "checkpoint-energy" else
               parse_diagnostics if args.action == "diagnostics" else None)
    if decoder:
        try:
            print(json.dumps(decoder(info), indent=2))
        except ValueError as error:
            raise SystemExit(str(error)) from error
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
        if "capabilities" in details:
            print("capabilities=0x%04X history=%s calibration=%s persisted-soc=%s full-width-energy=%s" % (
                details["capabilities"], details["uart1_history"], details["calibration_pages"],
                details["persisted_soc_contents"], details["full_width_energy"]))
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
