#!/usr/bin/env python3
"""Verify release identities; optionally rebuild through the mandatory CLI suite."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

# Python -I omits the script directory; resolve sibling modules from this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import ORIGINALS, PROJECT_ROOT, RELEASES, fixture
from seplos.image import Image

PUBLIC_METADATA = PROJECT_ROOT / 'mod' / 'firmware' / 'releases'


def verify_existing(raw, metadata):
    from seplos.profiles import require_profile
    require_profile(metadata['patch_version'])
    """Check exact EHEX/APP hashes and the embedded MNT identity independently."""
    image = Image.parse(raw.decode('ascii'))
    actual = {'ehex_sha256': hashlib.sha256(raw).hexdigest(),
              'app_sha256': image.sha, 'app_bytes': len(image.app)}
    for key in ('ehex_sha256', 'app_sha256', 'app_bytes'):
        if actual[key] != metadata[key]:
            raise ValueError(f'{key} mismatch for {metadata["name"]}')
    if image.app.count(b'MNT') != 1:
        raise ValueError(f'info_hex mismatch for {metadata["name"]}')
    offset = image.app.index(b'MNT')
    info_format = metadata['info_format']
    info_bytes = metadata['info_bytes']
    if info_format not in (3, 4) or info_bytes != (19 if info_format == 4 else 18):
        raise ValueError('info_hex format/length mismatch')
    # The APP template reserves two zero bytes; the handler fills the OEM
    # version from its read-only version source when it answers INFO=03.
    embedded = bytearray(image.app[offset:offset + info_bytes])
    if embedded[:4] != b'MNT' + bytes([info_format]) or embedded[4:6] != bytes(2):
        raise ValueError('info_hex OEM version template mismatch')
    embedded[4:6] = bytes(fixture('oem-16.06.13-facts')['facts']['oracle']['base_version'])
    info = bytes(embedded)
    if 'info_hex' in metadata and bytes.fromhex(metadata['info_hex']) != info:
        raise ValueError(f'info_hex mismatch for {metadata["name"]}')
    revision = info_format == 4
    version = bytes(map(int, metadata['patch_version'].split('.')))
    if len(version) != (3 if revision else 2) or version != info[7:10 if revision else 9]:
        raise ValueError(f'patch_version mismatch for {metadata["name"]}')
    build_id = info[10:18] if revision else info[9:17]
    if build_id.hex() != metadata['build_id']:
        raise ValueError(f'build_id mismatch for {metadata["name"]}')
    if info[-1] != metadata['image_flags']:
        raise ValueError(f'image_flags mismatch for {metadata["name"]}')
    actual.update(build_id=build_id.hex(), info_hex=info.hex(),
                  patch_version=metadata['patch_version'], image_flags=info[-1])
    return actual


def verify_source(source):
    """Pin the reconstruction source to the reviewed OEM container and APP."""
    expected = fixture('oem-16.06.13-facts')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected['input_sha256']:
        raise ValueError('OEM source sha256 mismatch')
    image = Image.parse(raw.decode('ascii'))
    if image.sha != expected['facts']['original_app_sha256']:
        raise ValueError('OEM source APP sha256 mismatch')
    return {'input': expected['input'], 'ehex_sha256': hashlib.sha256(raw).hexdigest(),
            'app_sha256': image.sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='fresh verification report directory')
    parser.add_argument('--images', type=Path, default=RELEASES, help='read-only release EHEX directory')
    parser.add_argument('--metadata-dir', type=Path, default=PUBLIC_METADATA,
                        help='metadata for the two supported current releases')
    parser.add_argument('--rebuild', action='store_true', help='run the real CLI worker and mandatory emulator suites')
    parser.add_argument('--source', type=Path, default=ORIGINALS / 'CAN1101[V16.06.13_PN01_250607].ehex')
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error('verification output already exists')
    metadata_paths = sorted(args.metadata_dir.glob('*.json'))
    if not metadata_paths:
        parser.error(f'missing required release metadata: {args.metadata_dir}')
    profiles = [(path, json.loads(path.read_text())) for path in metadata_paths]
    if args.metadata_dir.resolve() == PUBLIC_METADATA.resolve() and len(profiles) != 2:
        parser.error('expected exactly two current public release metadata files')
    from seplos.profiles import require_profile
    for _, metadata in profiles:
        require_profile(metadata['patch_version'])
    source = verify_source(args.source)
    # Verify every required release before creating output or rebuilding anything.
    rows = []
    for path, metadata in profiles:
        if Path(metadata['name']).name != metadata['name']:
            raise ValueError('release name must be a plain filename')
        raw = (args.images / metadata['name']).read_bytes()
        rows.append({'metadata': path.name, 'filename': metadata['name'],
                     'existing': verify_existing(raw, metadata)})
    args.out.mkdir(parents=True, exist_ok=False)
    for (path, metadata), row in zip(profiles, rows):
        if not args.rebuild:
            continue
        from seplos.cli import publish, run_worker
        info = bytes.fromhex(row['existing']['info_hex'])
        report, artifacts = run_worker(args.source, 'patch', info[6],
                                       maint_version=metadata['patch_version'])
        if report.get('status') != 'passed' or not report.get('suite_complete'):
            raise ValueError(f'mandatory rebuild suite failed: {report.get("error", report.get("status"))}')
        rebuilt = verify_existing(artifacts['firmware.ehex'], metadata)
        if report['build']['build_id'] != rebuilt['build_id']:
            raise ValueError('worker build_id mismatch')
        if artifacts['firmware.ehex'] != (args.images / metadata['name']).read_bytes():
            raise ValueError('reconstructed release bytes differ')
        publish(args.out / path.stem, report, artifacts)
        row.update(rebuilt=rebuilt, suite=report['suite'], tests=len(report['tests']),
                   byte_identical=True)
    result = {'passed': True, 'rebuild': args.rebuild, 'source': source,
              'profiles': len(rows), 'results': rows}
    with (args.out / 'results.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'rebuild': args.rebuild, 'profiles': len(rows)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
