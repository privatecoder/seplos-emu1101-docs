"""Addressed UART1 parameters, MAINT 1.2+ (1.5 permission error supported).

Offline unless a port is explicit.
"""
from __future__ import annotations

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT

import argparse
import binascii
from contextlib import contextmanager
import json
import math
from pathlib import Path
import socket
import sys
import time


class ProtocolError(ValueError):
    pass


class CommandRejected(ProtocolError):
    pass


class WriteOutcomeUnknown(RuntimeError):
    pass


class ReadbackMismatch(RuntimeError):
    pass


def valid_address(address):
    if type(address) is not int or not 0 <= address <= 21:
        raise ValueError('pack address must be an integer in 0..21')
    return address


def make_frame(address, command, data=b''):
    valid_address(address)
    if type(command) is not int or not 0 <= command <= 255 or len(data) > 223:
        raise ValueError('invalid command or data length')
    body = bytes([address, command, len(data)]) + bytes(data)
    return b'\x55' + body + binascii.crc_hqx(body, 0).to_bytes(2, 'big') + b'\xaa'


def parse_frame(raw, address, command):
    valid_address(address)
    if len(raw) < 7 or raw[0] != 0x55 or raw[-1] != 0xAA:
        raise ProtocolError('invalid binary frame markers/length')
    if len(raw) != raw[3] + 7:
        raise ProtocolError('binary frame length mismatch')
    if binascii.crc_hqx(raw[1:-3], 0) != int.from_bytes(raw[-3:-1], 'big'):
        raise ProtocolError('binary CRC mismatch')
    if raw[1] != address:
        raise ProtocolError(f'response address {raw[1]} differs from requested address {address}')
    if raw[2] != command:
        errors = {0x81: 'unknown command', 0x83: 'invalid parameter block markers',
                  0x87: 'invalid command data length', 0xE2: 'parameter validation rejected',
                  0xE3: 'permission denied: UART1 writing disabled or protected maintenance bit changed'}
        if raw[2] in errors and raw[3] == 0:
            raise CommandRejected(f'{errors[raw[2]]} (0x{raw[2]:02X})')
        raise ProtocolError(f'unexpected response command 0x{raw[2]:02X}')
    return bytes(raw[4:-3])


def decode_parameters(payload, address):
    valid_address(address)
    if len(payload) != 168 or payload[0] != 60 or payload[121] != 27 or payload[149] != 8:
        raise ProtocolError('invalid parameter block layout')
    return {
        'format': 'seplos-uart1-parameters-v1', 'pack_address': address,
        'parameters_u16': [int.from_bytes(payload[i:i + 2], 'big') for i in range(1, 121, 2)],
        'parameters_u8': list(payload[122:149]), 'function_switches': list(payload[150:158]),
        'device_name_hex': payload[158:168].hex(),
    }


def encode_parameters(config, address):
    valid_address(address)
    if not isinstance(config, dict) or config.get('format') != 'seplos-uart1-parameters-v1':
        raise ValueError('unsupported parameter JSON format')
    if type(config.get('pack_address')) is not int or config['pack_address'] != address:
        raise ValueError('file pack address differs from explicit target address')
    blocks = []
    for key, count, width in (('parameters_u16', 60, 2), ('parameters_u8', 27, 1),
                              ('function_switches', 8, 1)):
        values = config.get(key)
        if not isinstance(values, list) or len(values) != count:
            raise ValueError(f'{key} must contain exactly {count} integers')
        if any(type(value) is not int or not 0 <= value < (1 << (width * 8)) for value in values):
            raise ValueError(f'{key} contains a noninteger or out-of-range value')
        blocks.append(bytes([count]) + b''.join(value.to_bytes(width, 'big') for value in values))
    return b''.join(blocks)


def _read_exact(stream, length, deadline):
    result = bytearray()
    while len(result) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('binary response deadline expired')
        stream.set_timeout(remaining)
        part = stream.read(length - len(result))
        if not part:
            raise TimeoutError('binary response incomplete or connection closed')
        result.extend(part)
    return bytes(result)


def exchange(stream, address, command, payload=b'', timeout=3.0):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    request = make_frame(address, command, payload)
    stream.set_timeout(timeout)
    sent = stream.write(request)
    if sent != len(request):
        raise OSError('incomplete request write')
    deadline = time.monotonic() + timeout
    while True:
        header = _read_exact(stream, 4, deadline)
        if header[0] != 0x55 or header[3] > 168:
            raise ProtocolError('unexpected response header; check exclusive gateway access')
        raw = header + _read_exact(stream, header[3] + 3, deadline)
        if raw == request:  # Some adapters/gateways echo TX; never resend the request.
            continue
        return parse_frame(raw, address, command)


def read_parameters(stream, address, timeout=3.0):
    return decode_parameters(exchange(stream, address, 0x47, timeout=timeout), address)


def write_parameters(stream, address, config, timeout=3.0):
    payload = encode_parameters(config, address)
    try:
        ack = exchange(stream, address, 0xA1, payload, timeout)
        if ack:
            raise ProtocolError('write acknowledgment must have zero data bytes')
    except CommandRejected:
        raise
    except (OSError, ProtocolError) as error:
        raise WriteOutcomeUnknown('Schreibausgang unbekannt; kein automatischer Wiederholversuch. '
                                  'Vor einem weiteren Schreiben den Pack frisch auslesen.') from error
    # Exactly one write, then a fresh addressed read. Never automatically replay A1.
    result = read_parameters(stream, address, timeout)
    if encode_parameters(result, address) != payload:
        raise ReadbackMismatch('Schreib-ACK erhalten, aber zurückgelesene Parameter weichen ab')
    return result


class SocketStream:
    def __init__(self, connection):
        self.connection = connection

    def write(self, data):
        self.connection.sendall(data)
        return len(data)

    def read(self, count):
        return self.connection.recv(count)

    def set_timeout(self, seconds):
        self.connection.settimeout(seconds)


class SerialStream:
    def __init__(self, connection):
        self.connection = connection

    def write(self, data):
        return self.connection.write(data)

    def read(self, count):
        return self.connection.read(count)

    def set_timeout(self, seconds):
        self.connection.timeout = seconds
        self.connection.write_timeout = seconds


@contextmanager
def open_stream(args):
    if args.tcp:
        host, separator, port = args.tcp.rpartition(':')
        if not separator or not host or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError('--tcp expects HOST:PORT')
        with socket.create_connection((host.strip('[]'), int(port)), timeout=args.timeout) as connection:
            yield SocketStream(connection)
    else:
        try:
            import serial
        except ImportError as error:
            raise RuntimeError('Serial access requires pyserial; TCP/offline use only the standard library') from error
        with serial.Serial(args.serial, 9600, timeout=args.timeout, write_timeout=args.timeout) as connection:
            yield SerialStream(connection)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('read', 'write'))
    parser.add_argument('--address', required=True, type=int, help='pack address 0..21 (decimal)')
    parser.add_argument('--file', type=Path, help='write input JSON; required for write')
    parser.add_argument('--output', type=Path, help='save a live read or verified readback as JSON')
    parser.add_argument('--timeout', type=float, default=3.0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--tcp', metavar='HOST:PORT')
    group.add_argument('--serial', metavar='DEVICE')
    args = parser.parse_args(argv)
    try:
        valid_address(args.address)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError('--timeout must be finite and positive')
        if args.action == 'write' and args.file is None:
            raise ValueError('write requires --file')
        if args.action == 'read' and args.file is not None:
            raise ValueError('--file is only valid for write')
        config = json.loads(args.file.read_text()) if args.file is not None else None
        data = encode_parameters(config, args.address) if args.action == 'write' else b''
        command = 0xA1 if args.action == 'write' else 0x47
        if not args.tcp and not args.serial:
            if args.output:
                raise ValueError('--output requires an explicit --tcp or --serial port')
            print(make_frame(args.address, command, data).hex(' '))
            return 0
        with open_stream(args) as stream:
            result = (write_parameters(stream, args.address, config, args.timeout)
                      if args.action == 'write' else read_parameters(stream, args.address, args.timeout))
        rendered = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered)
        else:
            print(rendered, end='')
        if args.action == 'write':
            print('Schreiben quittiert und Parameter durch erneutes Lesen bestätigt.', file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
