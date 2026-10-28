#!/usr/bin/env python3
"""Inventory OEM BatteryMonitor Agreement XML without executing OEM software.

Stdlib only; python3 -I from a neutral directory. --out creates a new JSON file.
Schema declarations are reported as declarations, not proven firmware behavior.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = PROJECT_ROOT
DEFAULT = PROJECT_ROOT / 'vendor/software/batterymonitor/BatteryMonitor V2.1.13_20.zip'

def children(node):
    return {e.tag: (e.text or '').strip() for e in node}

def number(text):
    return str(Decimal(text.replace(',', '.')).normalize())

def profile(path, base):
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024 or b'<!DOCTYPE' in raw.upper():
        raise ValueError(f'Unexpected XML size or DOCTYPE: {path.name}')
    root = ET.fromstring(raw)
    assert root.tag == 'protocolConfig' and root.findtext('filetype') == 'Protocol'
    parameters = []
    for row in root.findall('int_para_Group/int_para'):
        item = children(row)
        item['index_decimal'] = int(item['ParaIndex'], 16)
        item['scale_normalized'] = number(item['Scale'])
        parameters.append(item)
    blocks = []
    for block in root.findall('teleMeter_Group/teleMeter_Block'):
        blocks.append(dict(type=block.findtext('teleMeterType'),
            count_field=block.findtext('NumFieldEnable'),
            fields=[children(n) for n in block.findall('teleMeterNode')]))
    bits = root.find('bit_para_Group')
    return dict(path=str(path.relative_to(base)), sha256=hashlib.sha256(raw).hexdigest(),
        byte_length=len(raw), basic=children(root.find('basicConfig')),
        telemetry=blocks, parameters=parameters,
        parameter_width_counts=dict(Counter(p['ByteNum'] for p in parameters)),
        bit_start_hex=bits.findtext('bitParaStartIndex'),
        bit_start_decimal=int(bits.findtext('bitParaStartIndex'), 16),
        bit_bytes=int(bits.findtext('bitParaByteNum')),
        bit_definitions=[children(n) for n in bits.findall('bit_para')],
        controls=[children(n) for n in root.findall('teleControl_Group/teleControl')],
        calibration=[children(n) for n in root.findall('adjust_para_Group/int_para')],
        literal_values=[(e.text or '').strip() for e in root.iter('Value')],
        can_options=[children(n) for n in root.findall('canProtocol/canTypeBlock')],
        serial_options=[children(n) for n in root.findall('serialPortProtocol/serialPortTypeBlock')])

def catalogue(base):
    base = base.resolve()
    if base.is_file():
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory(prefix='seplos-agreement-',dir='/private/tmp') as directory:
            destination=Path(directory)
            with zipfile.ZipFile(base) as archive:
                for member in archive.infolist():
                    # Some vendor ZIP entries contain UTF-8 without the language flag.
                    filename=member.filename
                    if not member.flag_bits & 0x800:
                        try:filename=filename.encode('cp437').decode('utf-8')
                        except UnicodeError:pass
                    parts=Path(filename).parts
                    if '__MACOSX' in parts or '..' in parts or Path(filename).is_absolute():continue
                    if 'Agreement' in parts and filename.endswith('.xml'):
                        target=destination/'Agreement'/Path(*parts[parts.index('Agreement')+1:])
                    elif parts[-1:] == ('BatteryMonitor.exe',):target=destination/'BatteryMonitor.exe'
                    else:continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(archive.read(member))
            result=catalogue(destination/'Agreement')
            result['source_archive']=dict(name=base.name,sha256=hashlib.sha256(base.read_bytes()).hexdigest())
            return result
    if not base.is_dir():raise FileNotFoundError(f'Agreement directory or vendor ZIP missing: {base}')
    profiles = [profile(path, base) for path in sorted(base.rglob('*.xml'))]
    by_name = {p['path']: p for p in profiles}
    ref = by_name.get('16S_V20_ADDR_EN.xml')
    signature = lambda p: [(n['index_decimal'], n['ByteNum'], n['scale_normalized']) for n in p['parameters']]
    result = dict(schema='seplos-oem-batterymonitor-agreement-v1', profile_count=len(profiles),
        profiles=profiles, all_parameter_maps_match_root_16s_en=(
            all(signature(p) == signature(ref) for p in profiles) if ref else None),
        hardware_access=False, target_executed=False)
    exe = base.parent / 'BatteryMonitor.exe'
    if exe.is_file():
        raw = exe.read_bytes()
        result['companion_executable'] = dict(name=exe.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    comma_copies = []
    for path in sorted(base.glob('英文操作系统/*.xml')):
        original = base / path.name.replace('_V20B_', '_V20_')
        if original.is_file():
            left = list(ET.parse(original).getroot().iter())
            right = list(ET.parse(path).getroot().iter())
            converted = lambda node: (node.tag, node.attrib, (node.text or '').strip().replace('.', ','))
            literal = lambda node: (node.tag, node.attrib, (node.text or '').strip())
            comma_copies.append(dict(path=str(path.relative_to(base)), root=original.name,
                solely_dot_to_comma_values=(len(left) == len(right) and
                    all(converted(a) == literal(b) for a, b in zip(left, right)))))
    result['decimal_separator_copies'] = comma_copies
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agreement', type=Path, default=DEFAULT)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    output = json.dumps(catalogue(args.agreement), ensure_ascii=False, indent=2) + '\n'
    if args.out:
        with args.out.open('x', encoding='utf-8') as stream:
            stream.write(output)
    else:
        print(output, end='')

if __name__ == '__main__':
    main()
