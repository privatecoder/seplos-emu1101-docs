#!/usr/bin/env python3
"""Verify private 0x5A fixture framing, decoded fields and original source binding.

Standard-library, offline, read only. Appending CR to a printed frame is explicit
fixture reconstruction; it does not claim the source captured that terminal byte.
"""
from pathlib import Path
from decimal import Decimal
import argparse
import hashlib
import json
import struct

PROJECT = Path(__file__).resolve().parents[3]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(wire):
    require(isinstance(wire, str) and wire.startswith('~') and wire.endswith('\r'), 'Missing frame delimiters')
    raw = wire[:-1]
    require(len(raw) == 81, 'Invalid 0x5A response extent')
    try:
        header = bytes.fromhex(raw[1:13])
        body = bytes.fromhex(raw[13:-4])
        checksum = int(raw[-4:], 16)
    except ValueError as exc:
        raise ValueError('Invalid hexadecimal frame') from exc
    require(len(header) == 6 and len(body) == 32, 'Invalid header/body extent')
    require(header[0] == 0x20 and header[2:4] == b'\x46\x5a', 'Unsupported 0x5A header')
    length = int.from_bytes(header[4:], 'big')
    require(sum((length >> i) & 15 for i in (0, 4, 8, 12)) % 16 == 0, 'Invalid LENGTH check nibble')
    require(length & 0xFFF == len(body) * 2, 'LENGTH/body mismatch')
    require((sum(raw[1:-4].encode('ascii')) + checksum) % 65536 == 0, 'Invalid ASCII additive checksum')
    hi, lo, th, tl, current, voltage, rem, full, soc, port, *status = struct.unpack('>HHHHhHHHHH10B', body[2:])
    return dict(address=header[1], data_flag=body[0], constant=body[1],
        cell_max_v=Decimal(hi)/1000, cell_min_v=Decimal(lo)/1000,
        temperature_max_c=Decimal(th-2731)/10, temperature_min_c=Decimal(tl-2731)/10,
        current_a=Decimal(current)/100, pack_voltage_v=Decimal(voltage)/100,
        remaining_capacity_ah=Decimal(rem)/100, full_capacity_ah=Decimal(full)/100,
        soc_pct=Decimal(soc)/10, port_voltage_v=Decimal(port)/100,
        events_1_to_6_hex=bytes(status[:6]).hex().upper(), on_off=status[6],
        event7=status[7], event8=status[8], system_status=status[9])


def compare(actual, expected, *, complete):
    require(not complete or actual.keys() == expected.keys(), 'Expected decoded field set differs')
    for name, value in expected.items():
        require(name in actual, 'Unknown expected field: ' + name)
        observed = actual[name]
        equal = (observed == Decimal(str(value)) if isinstance(observed, (int, Decimal))
                 and not isinstance(observed, bool) else observed == value)
        require(equal, 'Decoded value differs: ' + name)


def verify_example(example, lines):
    wire = example['wire_ascii']
    printed = example['raw_source_ascii']
    require(printed == wire[:-1]+'\\r', 'Issue printed/wire frame differs')
    lo, hi = example['source_lines']
    require(type(lo) is int and type(hi) is int and 1 <= lo <= hi <= len(lines),
            'Invalid example source range')
    source = '\n'.join(lines[lo-1:hi])
    require(printed in source, 'Example frame differs from original source range')
    if 'log_bytes_dotted' in example:
        dotted = example['log_bytes_dotted']
        require(dotted in source, 'Example log differs from original source range')
        require(dotted.replace('.', '') == wire[1:-5], 'Example log/frame payload differs')
    compare(decode(wire), example['expected'], complete=True)


def verify(path, project=PROJECT):
    fixture = json.loads(Path(path).read_text())
    source = fixture['source']
    relative = Path(source['retained_path'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe source binding path')
    raw_source = (project/relative).read_bytes()
    require(hashlib.sha256(raw_source).hexdigest() == source['retained_sha256'] == source['original_sha256'], 'Source digest differs')
    lines = raw_source.decode('utf-8').splitlines()
    captures = fixture['captures']
    require(bool(captures), 'No captures')
    for capture in captures:
        require(capture['wire_ascii'] == capture['raw_source_ascii']+'\r', 'Printed/wire capture differs')
        require(capture['raw_source_ascii'] in lines[capture['source_line']-1], 'Source frame differs')
        decoded = decode(capture['wire_ascii'])
        compare(decoded, capture['expected'], complete=True)
        compare(decoded, capture['source_table_expected'], complete=False)
    examples = 0
    if 'issue_116_example' in fixture:
        example = fixture['issue_116_example']
        verify_example(example, lines)
        examples = 1
    mapping = fixture.get('decoder_log', {}).get('mapping', [])
    for row in mapping:
        require(row['original_log_label'] == lines[row['source_line']-1].split('|')[1].strip(), 'Original log label differs')
    return {'passed': True, 'captures': len(captures), 'separate_examples': examples,
            'log_labels': len(mapping), 'source_sha256': source['retained_sha256'],
            'scope': fixture['scope']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT)
    parser.add_argument('--fixtures', type=Path)
    args = parser.parse_args()
    try:
        path = args.fixtures or args.project/'local/fixtures/emulation/intra-pack/captures-5a.json'
        print(json.dumps(verify(path, args.project), indent=2))
        return 0
    except (OSError, ValueError, KeyError, IndexError, UnicodeError) as error:
        parser.exit(1, 'fixture verification failed: '+str(error)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
