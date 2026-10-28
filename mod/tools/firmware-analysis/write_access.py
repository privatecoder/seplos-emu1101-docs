#!/usr/bin/env python3
"""Current offline capability catalogue for Seplos BMS 2.0/10E/V16 (EMU1101).

Release identities come from mod/firmware/releases. Verification checks current
input bytes and MNT04 metadata, and does not claim a new native test run.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _paths import PROJECT_ROOT, PATCHER_ROOT

ROOT = PROJECT_ROOT
_DATA = json.loads((HERE / 'write_access_data.json').read_text())
_IDENTITY = ('build_id', 'image_flags', 'info_format', 'app_sha256', 'ehex_sha256',
             'extended_diagnostics', 'checkpoint_before_reset',
             'configurable_hard_stop', 'hard_stop_default')


def catalogue():
    data = copy.deepcopy(_DATA)
    for version, profile in data['profiles'].items():
        manifest = json.loads((ROOT / profile['manifest']).read_text())
        if manifest['patch_version'] != version:
            raise ValueError(f'release version mismatch: {profile["manifest"]}')
        profile.update({key: manifest[key] for key in _IDENTITY if key in manifest})
    return data


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '|' + '|'.join('---' for _ in headers) + '|'] +
                     ['| ' + ' | '.join(str(x).replace('|', '\\|') for x in row) + ' |' for row in rows])


def display_ports(value):
    """Canonical port names in presentation only; extracted JSON stays literal."""
    names = {'R': 'UART0', 'C': 'UART1', 'D': 'UART2'}
    return re.sub(r'\b[RCD]\b', lambda match: names[match[0]], str(value))


def port_rows(rows):
    return [[display_ports(cell) for cell in row] for row in rows]


def render():
    data = catalogue()
    profiles = data['profiles']
    doc = (HERE / 'write_access.template.md').read_text()
    chunks = {
        '@PROFILES@': table(('Firmware', 'Build ID', 'MNT04 image flags', '.ehex file SHA-256'),
            [('Original16.06.13', '—', '—', f'`{data["base_image"]["ehex_sha256"]}`')] +
            [(v, f'`{p["build_id"]}`', f'`0x{p["image_flags"]:02X}`', f'`{p["ehex_sha256"]}`') for v, p in profiles.items()]),
        '@MATRIX@': table(('Value / action', 'Command', 'Original .13', 'MAINT1.5.3', 'MAINT1.6.3'), port_rows(data['matrix'])),
        '@READS@': table(('Read operation', 'Command', 'Original .13', 'MAINT1.5.3', 'MAINT1.6.3'), port_rows(data['selected_read_commands'])),
        '@GROUP0@': table(('Field', 'Original .13', 'MAINT1.5.3', 'MAINT1.6.3', 'Write route / exception'), port_rows(data['group0'])),
        '@PARAMETERS@': table(('Index', 'Value', 'Raw unit', 'OEM .13 RAM'),
            [(f'P{p["index"]}', p['name'], p['unit'], f'`{p["ram"]:#010x}`') for p in data['parameters']]),
        '@BITS@': table(('Group', 'Bit', 'Meaning'),
            [(f'Group{b["group"]}', b['bit'], display_ports(b['name'])) for b in data['function_bits']]),
    }
    for token, chunk in chunks.items():
        if doc.count(token) != 1:
            raise ValueError('invalid template token ' + token)
        doc = doc.replace(token, chunk)
    return doc


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify():
    sys.path.insert(0, str(PATCHER_ROOT))
    from seplos.image import Image
    data = catalogue()
    base = data['base_image']
    path = ROOT / base['path']
    image = Image.read(path)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == base['ehex_sha256'], 'OEM EHEX hash mismatch')
    require(image.sha == base['app_sha256'], 'OEM application hash mismatch')
    verified = {}
    for version, profile in data['profiles'].items():
        manifest = json.loads((ROOT / profile['manifest']).read_text())
        path = ROOT / 'local/releases' / manifest['name']
        image = Image.read(path)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest['ehex_sha256'], f'{version}: EHEX hash mismatch')
        require(image.sha == manifest['app_sha256'], f'{version}: application hash mismatch')
        require(len(image.app) == manifest['app_bytes'], f'{version}: application extent mismatch')
        info = bytes.fromhex(manifest['info_hex'])
        expected = (b'MNT' + bytes([manifest['info_format']]) + bytes.fromhex('10060D') +
                    bytes(map(int, version.split('.'))) + bytes.fromhex(manifest['build_id']) +
                    bytes([manifest['image_flags']]))
        require(info == expected and len(info) == manifest['info_bytes'] == 19,
                f'{version}: MNT04 release metadata mismatch')
        # The handlers replace template bytes 4/5 with the OEM version RAM.
        # payload.s info_copy and marker_uart0.s .Lm0_info_copy define this ABI.
        template = info[:4] + b'\0\0' + info[6:]
        require(image.app.count(template) == 1, f'{version}: MNT04 template missing or ambiguous in application')
        offset = image.app.index(template) + 10
        neutral = bytearray(image.app)
        neutral[offset:offset + 8] = b'UPID0000'
        require(hashlib.sha256(neutral).digest()[:8].hex() == manifest['build_id'],
                f'{version}: MNT04 build ID does not match application')
        verified[version] = {'manifest': profile['manifest'], 'ehex_sha256': manifest['ehex_sha256'],
                             'app_sha256': image.sha, 'build_id': manifest['build_id'],
                             'info_hex': info.hex().upper()}
    require((len(data['parameters']), len(data['function_bits']), len(data['matrix'])) == (87, 64, 23),
            'capability dimensions changed')
    return {'passed': True, 'verification': 'current release hashes and MNT04 metadata; no native emulation',
            'profiles': verified, 'parameter_count': 87, 'switch_positions': 64,
            'action_rows': 23, 'hardware_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--markdown', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        value = render() if args.markdown else json.dumps(verify() if args.verify else catalogue(), ensure_ascii=False, indent=2) + '\n'
        if args.out:
            with args.out.open('x') as stream:
                stream.write(value)
        else:
            print(value, end='')
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'write_access: {exc}\n')


if __name__ == '__main__':
    main()
