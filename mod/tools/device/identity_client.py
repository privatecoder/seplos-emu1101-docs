"""MAINT 1.3: read addressed Battery_SN/BMS_SN via UART1, serial or TCP.

Without --serial/--tcp prints only the two raw read requests. No write support.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('identity_parameter_protocol',
    HERE / 'parameter_client.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def read_serial(stream, address, command, timeout=3.0):
    if command not in (0xA2, 0xA4):
        raise ValueError('Only read commands A2 and A4 are supported')
    data = protocol.exchange(stream, address, command, timeout=timeout)
    if len(data) != 30:
        raise protocol.ProtocolError('Serial number response must contain exactly 30 bytes')
    return data


def read_identity(stream, address, timeout=3.0):
    battery = read_serial(stream, address, 0xA2, timeout)
    bms = read_serial(stream, address, 0xA4, timeout)
    return {'format': 'seplos-uart1-identity-v1', 'pack_address': address,
            'battery_sn_hex': battery.hex(), 'bms_sn_hex': bms.hex(),
            'battery_sn': battery.rstrip(b' \x00').decode('ascii', 'replace'),
            'bms_sn': bms.rstrip(b' \x00').decode('ascii', 'replace')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', type=int, required=True, help='Pack address 0..21, decimal')
    parser.add_argument('--timeout', type=float, default=3.0, help='Total seconds per reply')
    parser.add_argument('--output', type=Path)
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument('--serial', metavar='DEVICE')
    transport.add_argument('--tcp', metavar='HOST:PORT')
    args = parser.parse_args(argv)
    try:
        protocol.valid_address(args.address)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError('--timeout must be finite and positive')
        if not args.serial and not args.tcp:
            if args.output:
                raise ValueError('--output requires a transport')
            for command in (0xA2, 0xA4):
                print(protocol.make_frame(args.address, command).hex(' '))
            return 0
        if args.output and args.output.exists():
            raise ValueError('Output exists; choose a new filename')
        with protocol.open_stream(args) as stream:
            result = read_identity(stream, args.address, args.timeout)
        rendered = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered)
        else:
            print(rendered, end='')
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
