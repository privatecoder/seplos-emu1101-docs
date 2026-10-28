#!/usr/bin/env python3
"""Offline, source-bound lookup of retained firmware knowledge.

Only refresh writes indexes. Query operations never run firmware, LLVM, a native
emulator or a serial transport. Identity is a full application SHA256 comparison;
container identity is recorded separately. Cached knowledge is not patch approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 1
INDEX_FILES = ('images', 'topics', 'builds', 'dependencies')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def bind(root, path):
    raw = path.read_bytes()
    return {'path': path.relative_to(root).as_posix(), 'bytes': len(raw), 'sha256': digest(raw)}


def check_bindings(root, bindings):
    problems = []
    for item in bindings:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            problems.append({'path': item['path'], 'problem': 'unsafe-path'})
            continue
        path = root / relative
        if not path.is_file():
            problems.append({'path': item['path'], 'problem': 'missing'})
        else:
            raw = path.read_bytes()
            if len(raw) != item['bytes'] or digest(raw) != item['sha256']:
                problems.append({'path': item['path'], 'problem': 'changed'})
    return problems


def read_image(path, root=PROJECT_ROOT):
    # Import only strict data parsing, never the CLI or emulator. -I invocation
    # deliberately excludes cwd; this inserts the maintained parser source only.
    sys.path.insert(0, str(root / 'mod/firmware/patcher'))
    try:
        from seplos.image import Image
        raw = path.read_bytes()
        image = Image.parse(raw.decode('ascii'))
        return {'file_sha256': digest(raw), 'file_bytes': len(raw),
                'app_sha256': image.sha, 'app_bytes': len(image.app)}
    finally:
        sys.path.pop(0)


def match_image(identity, records):
    matches = [record for record in records
               if record.get('app_sha256') == identity['app_sha256']]
    exact = [record for record in matches if record.get('file_sha256') == identity['file_sha256']]
    status = ('known-exact-container' if exact else 'known-application-different-container'
              if matches else 'unknown-application')
    return {'identity': status, 'matches': exact or matches,
            'scope': 'Full application bytes only; no claim of hardware or runtime equivalence.'}


def release_match(identity, metadata):
    return (identity.get('file_sha256') == metadata.get('ehex_sha256') and
            identity.get('app_sha256') == metadata.get('app_sha256'))


def report_status(data):
    tests = data.get('tests', []) if isinstance(data, dict) else []
    if not isinstance(tests, list):
        tests = []
    passed = sum(isinstance(test, dict) and test.get('passed') is True for test in tests)
    failed = [test.get('name', '(unnamed)') for test in tests
              if isinstance(test, dict) and test.get('passed') is False]
    status = data.get('status') if isinstance(data, dict) else None
    verdict = ('recorded-failure' if failed or status in ('failed', 'error', 'test_failed') else
               'recorded-refusal' if status == 'refused' else
               'recorded-failure' if isinstance(data, dict) and data.get('error') else
               'recorded-pass' if status == 'passed' else 'unclassified')
    return {'verdict': verdict, 'declared_status': status, 'error': data.get('error') if isinstance(data, dict) else None, 'passed_tests': passed,
            'failed_tests': failed, 'suite_complete': data.get('suite_complete') if isinstance(data, dict) else None,
            'scope': 'Saved report evidence; not a fresh test result or hardware proof.'}


def _relative(root, paths):
    return [p.relative_to(root).as_posix() for p in paths if p.is_file()]


def _first_paragraph(path):
    # Prefer the short plain-text conclusion after the title/port legend.
    paragraphs = path.read_text(encoding='utf-8').split('\n\n')
    for paragraph in paragraphs:
        text = paragraph.strip()
        if text and not text.startswith(('#', '>', '|', '```', '- ', '1. ')):
            return ' '.join(text.split())[:600]
    return ''


def refresh(root):
    directory = root/'local/index'
    directory.mkdir(parents=True, exist_ok=True)
    old_topics = load(directory/'topics.json', {})
    bindings = {}
    errors = []

    def add(path):
        if path.is_file():
            item = bind(root, path)
            bindings[item['path']] = item

    metadata = []
    for path in sorted((root/'mod/firmware/releases').glob('*.json')):
        add(path)
        metadata.append((path.relative_to(root).as_posix(), load(path)))

    # Explicit canonical roots: never walk history/snapshots or its compatibility
    # view, and never scan source snapshots embedded in build bundles.
    image_paths = set()
    for base in ('vendor/firmware', 'local/releases', 'local/fixtures/corpus'):
        image_paths.update((root/base).rglob('*.ehex'))
    image_paths.update((root/'local/builds').glob('oem*/maint-*/*/*.ehex'))
    images = []
    for path in sorted(image_paths):
        add(path)
        relative = path.relative_to(root).as_posix()
        role = ('OEM' if relative.startswith('vendor/') else 'build-output'
                if relative.startswith('local/builds/') else 'fixture'
                if relative.startswith('local/fixtures/') else 'retained-release')
        try:
            identity = read_image(path, root)
            record = dict(path=relative, roles=[role], **identity)
            for meta_path, meta in metadata:
                if release_match(identity, meta):
                    record['release'] = {'metadata': meta_path,
                        **{key: meta[key] for key in ('patch_version', 'build_id', 'image_flags',
                            'hardware_tested', 'flashed', 'release_status') if key in meta}}
                    record['roles'].append('current-release')
            images.append(record)
        except (ValueError, UnicodeError, OSError) as exc:
            errors.append({'path': relative, 'problem': 'invalid-image', 'detail': str(exc)})

    for meta_path, meta in metadata:
        expected_path = 'local/releases/' + meta.get('name', '')
        matches = [item for item in images if item['path'] == expected_path]
        if len(matches) != 1 or not release_match(matches[0], meta):
            errors.append({'path': expected_path, 'problem': 'release-metadata-mismatch',
                           'metadata': meta_path})

    artifacts = []
    for path in sorted((root/'local/artifacts/firmware').glob('*/binding.json')):
        add(path)
        data = load(path)
        for expected in data.get('artifacts', []):
            errors.extend(check_bindings(root, [expected]))
        source = next((item for item in images if item['path'] == data.get('source')), None)
        if (source is None or source.get('app_sha256') != data.get('app_sha256')
                or source.get('file_sha256') != data.get('container_sha256')
                or source.get('app_bytes') != data.get('app_bytes')):
            errors.append({'path': str(path.relative_to(root)), 'problem': 'artifact-source-binding-mismatch'})
        files = sorted(p for p in path.parent.iterdir() if p.is_file() and p != path)
        for item in files:
            add(item)
        artifacts.append({'binding': path.relative_to(root).as_posix(), 'facts': data,
                          'files': _relative(root, files)})

    canonical = []
    for path in sorted((root/'local/builds').glob('oem*/maint-*/*/report.json')):
        data = load(path)
        add(path)
        build = data.get('build', {})
        bundle = path.parent
        candidate = next((item for item in images if item['path'] == str((bundle/'firmware.ehex').relative_to(root))), None)
        if candidate is None or candidate['app_sha256'] != build.get('app_sha256') or candidate['file_sha256'] != data.get('output_file_sha256'):
            errors.append({'path': str(path.relative_to(root)), 'problem': 'build-output-binding-mismatch'})
        supporting = []
        for name in ('payload.resolved.s', 'payload.dis', 'reproduction.json', 'delta-from-base.json'):
            item = bundle/name
            if item.is_file():
                supporting.append(item)
                add(item)
        source_manifests = [p for p in bundle.glob('*manifest*.json') if p.is_file()]
        for item in source_manifests:
            add(item)
        source_files = sorted(item for item in (bundle/'source-snapshot').rglob('*') if item.is_file()) if (bundle/'source-snapshot').is_dir() else []
        for item in source_files:
            add(item)
        canonical.append({'path': bundle.relative_to(root).as_posix(),
            'report': path.relative_to(root).as_posix(),
            'patch_version': build.get('patch_version', data.get('maint_version')),
            'build_id': build.get('build_id'),
            'input_app_sha256': data.get('input_app_sha256'),
            'output_app_sha256': build.get('app_sha256'),
            'output_file_sha256': data.get('output_file_sha256'),
            'suite': data.get('suite'), **report_status(data),
            'supporting': _relative(root, supporting),
            'source_manifests': _relative(root, source_manifests),
            'source_files_bound': len(source_files),
            'sources': _relative(root, [bundle/'source-snapshot']) or
                       ([str((bundle/'source-snapshot').relative_to(root))] if (bundle/'source-snapshot').is_dir() else [])})

    runs = []
    runs_roots = [root/'local/builds/runs'] + sorted((root/'local/history/sessions').glob('*/reports'))
    run_paths = {path for base in runs_roots if base.exists() for path in base.rglob('*')}
    for path in sorted(run_paths):
        if not path.is_file() or 'source-snapshot' in path.parts:
            continue
        if path.suffix == '.json':
            try:
                data = load(path)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(data, dict) or not ('tests' in data or 'status' in data):
                continue
            add(path)
            runs.append({'path': path.relative_to(root).as_posix(), **report_status(data),
                         'input_app_sha256': data.get('input_app_sha256'),
                         'output_app_sha256': data.get('build', {}).get('app_sha256') if isinstance(data.get('build'), dict) else None})
        elif path.suffix == '.log':
            text = path.read_text(encoding='utf-8', errors='replace')
            failures = re.findall(r'^.*(?:FAILED \(|^FAIL:|^ERROR:|AssertionError|Traceback \().*$', text, re.M)
            result = ('recorded-failure' if failures else 'recorded-pass' if re.search(r'^OK(?:\s*\([^\n]*\))?\s*$', text, re.M) else 'unclassified')
            add(path)
            runs.append({'path': path.relative_to(root).as_posix(), 'verdict': result,
                         'failure_markers': failures[:10], 'scope': 'Saved log markers; source/image binding must be checked separately.'})

    topics = []
    for path in sorted((root/'local/research').glob('*/README.md')):
        add(path)
        topics.append({'id': path.parent.name, 'path': path.relative_to(root).as_posix(),
                       'summary': _first_paragraph(path)})
    decisions_path = root/'local/history/decisions.json'
    decisions_data = load(decisions_path, {})
    decisions = (decisions_data if isinstance(decisions_data, list) else
                 decisions_data.get('records', decisions_data.get('knowledge_index', decisions_data.get('decisions', []))))
    if decisions_path.exists():
        add(decisions_path)
    for decision in decisions:
        for item in decision.get('source_bindings', []):
            path = root/item['path']
            if path.is_file():
                add(path)
                if digest(path.read_bytes()) != item['sha256']:
                    errors.append({'path': item['path'], 'problem': 'decision-source-digest-mismatch'})
            else:
                errors.append({'path': item['path'], 'problem': 'missing-decision-source'})

    # Models and signatures are part of the inspection context. A changed model
    # invalidates this index's freshness even if all firmware bytes stayed equal.
    for base, patterns in (('mod/firmware/patcher', ('seplos/*.py', 'seplos/*.json', 'corpus.json', 'requirements.txt')),
                           ('mod/tools', ('*.py', '*.json', 'firmware-analysis/*.py', 'firmware-analysis/*.json'))):
        for pattern in patterns:
            for path in sorted((root/base).glob(pattern)):
                add(path)
    registry_path = root/'mod/tools/research-inputs.json'
    registry = load(registry_path, {})
    if registry_path.exists():
        add(registry_path)
        for expected in registry.get('inputs', {}).values():
            errors.extend(check_bindings(root, [expected]))
            add(root/expected['path'])
    # Private reusable fixtures/notes are also inspection inputs; hash them
    # without walking captured binaries or compatibility/frozen source trees.
    for base, patterns in (
        ('local/fixtures/emulation', ('**/*.json',)),
        ('local/research', ('*/*.md', 'provenance/*.json', 'monitor-design/*.json')),
        ('local/devices/configuration', ('history-*.md',)),
        ('local/history', ('sessions/index.json',))):
        for pattern in patterns:
            for path in sorted((root/base).glob(pattern)):
                add(path)
    historical_manifest = root/'local/history/snapshots/mod-before-current-cleanup-2026-10-26/source-manifest.json'
    add(historical_manifest)
    add(root/'local/index/paths.json')
    all_bindings = [bindings[key] for key in sorted(bindings)]
    generation = digest(json.dumps(all_bindings, sort_keys=True).encode())
    common = {'schema': SCHEMA, 'generation': generation}
    payloads = {
        'images': {**common, 'images': images, 'artifacts': artifacts, 'errors': errors,
                   'scope': 'Strict EHEX/application identities and artifact provenance; not firmware test approval.'},
        'builds': {**common, 'canonical': canonical, 'runs': runs,
                   'scope': 'Saved reports only. A final/green filename is never evidence of success.'},
        'topics': {**common, 'topics': topics, 'decisions': decisions,
                   'curated_topics': old_topics.get('curated_topics', []),
                   'scope': 'Read the referenced topic scope and exact image/source bindings before reuse.'},
        'dependencies': {**common, 'bindings': all_bindings, 'research_inputs': registry,
            'requirements': [
                {'operation': 'find/topic/builds/dependencies/verify', 'requires': 'Python 3.11+ standard library and retained JSON indexes/data; no native execution'},
                {'operation': 'identify/refresh', 'requires': 'Maintained seplos.image strict parser; standard library only; no emulation'},
                {'operation': 'patch or native probe', 'requires': 'Separate patcher/tool environment, mandatory tests and LLVM/Unicorn as documented; indexes never waive checks'},
                {'operation': 'frozen regression', 'requires': 'Intact source snapshot + legacy-input-view; run_historical_tests.py verifies frozen sources separately'}],
            'scope': 'Freshness of indexed files and model sources, not exhaustive frozen runtime closure or physical validation.'}}
    # All content is computed before publishing. Generation tags detect a mixed
    # interrupted refresh. Each file is replaced atomically on its own filesystem.
    for name, payload in payloads.items():
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory,
                                         prefix='.'+name, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        temporary.replace(directory/(name+'.json'))
    return {'generation': generation, 'images': len(images), 'artifacts': len(artifacts),
            'canonical_builds': len(canonical), 'run_records': len(runs), 'topics': len(topics),
            'decisions': len(decisions), 'bindings': len(all_bindings), 'errors': errors}


def indexes(root):
    result = {}
    for name in INDEX_FILES:
        path = root/'local/index'/(name+'.json')
        if not path.is_file():
            raise ValueError('Missing index '+str(path)+'; run refresh first.')
        result[name] = load(path)
    return result


def emit(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT_ROOT, help='Alternative complete library root; defaults beside this script')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('refresh', help='Rebuild indexes atomically from canonical files; preserve curated_topics')
    sub.add_parser('verify', help='Hash indexed inputs/models and report changed/missing files')
    identify = sub.add_parser('identify', help='Strictly identify EHEX application and container hashes')
    identify.add_argument('image', type=Path)
    find = sub.add_parser('find', help='Find concise topic, decision, image and build pointers')
    find.add_argument('query')
    topic = sub.add_parser('topic', help='Read one exact topic/decision id (no fuzzy inference)')
    topic.add_argument('name')
    builds_parser = sub.add_parser('builds', help='List canonical builds and a concise retained-failure summary')
    builds_parser.add_argument('--failures', action='store_true', help='Include full saved failure records')
    deps = sub.add_parser('dependencies', help='Show requirements and logical analysis inputs')
    deps.add_argument('--all-bindings', action='store_true')
    args = parser.parse_args(argv)
    root = args.project.resolve()
    try:
        if args.command == 'refresh':
            result = refresh(root)
            emit(result)
            return int(bool(result['errors']))
        if args.command == 'topic':
            data = load(root/'local/index/topics.json')
            if data is None:
                raise ValueError('Missing topics index; run refresh first.')
            matches = [item for key in ('topics', 'decisions', 'curated_topics')
                       for item in data.get(key, []) if item.get('id') == args.name]
            emit({'matches': matches})
            return 0 if matches else 1
        data = indexes(root)
        if args.command == 'verify':
            problems = check_bindings(root, data['dependencies']['bindings'])
            generations = {item.get('generation') for item in data.values()}
            if len(generations) != 1:
                problems.append({'problem': 'mixed-index-generations'})
            problems.extend(data['images'].get('errors', []))
            emit({'status': 'passed' if not problems else 'failed',
                  'bindings_checked': len(data['dependencies']['bindings']), 'problems': problems,
                  'scope': data['dependencies'].get('scope')})
            return int(bool(problems))
        if args.command == 'identify':
            identity = read_image(args.image.resolve(), root)
            result = match_image(identity, data['images']['images'])
            result['input'] = str(args.image)
            result.update(identity)
            result['next'] = ('Use the matching topic/model bindings, then perform mandatory patch analysis/tests.'
                              if result['matches'] else 'Unknown application: run the patcher analyze command on a fresh output path; review signature/model guards before patching. Do not borrow addresses from another image.')
            emit(result)
        elif args.command == 'builds':
            runs = data['builds']['runs']
            failures = [item for item in runs if item['verdict'] == 'recorded-failure']
            result = {'canonical': data['builds']['canonical'],
                      'run_counts': {verdict: sum(item['verdict'] == verdict for item in runs)
                                     for verdict in sorted({item['verdict'] for item in runs})},
                      'scope': data['builds']['scope']}
            if args.failures:
                result['failed_runs'] = failures
            else:
                result['failed_run_paths'] = [item['path'] for item in failures]
            emit(result)
        elif args.command == 'dependencies':
            deps = data['dependencies']
            emit({key: value for key, value in deps.items() if args.all_bindings or key != 'bindings'})
        elif args.command == 'find':
            query = args.query.casefold()
            matches = []
            for group, records in (('topic', data['topics'].get('topics', []) + data['topics'].get('curated_topics', [])),
                                   ('decision', data['topics'].get('decisions', [])),
                                   ('image', data['images']['images']),
                                   ('build', data['builds']['canonical'])):
                for record in records:
                    if query in json.dumps(record, ensure_ascii=False).casefold():
                        keys = ('id', 'path', 'summary', 'decision', 'scope', 'patch_version', 'build_id', 'app_sha256', 'sources', 'verdict')
                        matches.append({'kind': group, **{key: record[key] for key in keys if key in record}})
            emit({'matches': matches, 'count': len(matches)})
        return 0
    except (OSError, ValueError, KeyError, UnicodeError) as exc:
        print('knowledge: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
