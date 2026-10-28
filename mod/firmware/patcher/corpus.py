"""Locate read-only firmware inputs from the installed patcher, independent of cwd."""
from pathlib import Path
import hashlib
import json

PATCHER_ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((PATCHER_ROOT / 'corpus.json').read_text())


def project_root():
    for candidate in PATCHER_ROOT.parents:
        if (candidate / 'vendor' / 'firmware').is_dir() and (candidate / 'mod' / 'firmware' / 'patcher').is_dir():
            return candidate
    raise FileNotFoundError('project layout missing: expected vendor/firmware beside mod/firmware/patcher')


PROJECT_ROOT = project_root()
ORIGINALS = PROJECT_ROOT / MANIFEST['originals']
RELEASES = PROJECT_ROOT / MANIFEST['releases']
LEGACY = PROJECT_ROOT / MANIFEST['legacy']


def _checked_bytes(path, metadata, label):
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'missing required {label}: {path}') from exc
    if len(raw) != metadata['bytes'] or hashlib.sha256(raw).hexdigest() != metadata['sha256']:
        raise ValueError(f'{"fixture" if label.startswith("metadata fixture") else label} integrity mismatch: {path}')
    return raw


def fixture(name, root=PATCHER_ROOT / 'tests' / 'fixtures'):
    """Read one maintained metadata fixture; never fall back to historical reports."""
    root = Path(root)
    try:
        registry = json.loads((root / 'registry.json').read_text())
        entry = registry['fixtures'][name]
    except (FileNotFoundError, KeyError) as exc:
        raise FileNotFoundError(f'missing required metadata fixture registry/name: {name}') from exc
    raw = _checked_bytes(root / entry['file'], entry, f'metadata fixture: {name}')
    return json.loads(raw)


def corpus_groups(root=PROJECT_ROOT):
    """Require all 16 named, hashed inputs; unrelated files never extend the corpus."""
    groups = []
    for group in MANIFEST['groups']:
        directory = root / group['directory']
        files = []
        for entry in group['files']:
            path = directory / entry['name']
            _checked_bytes(path, entry, 'corpus input')
            files.append(path)
        groups.append((group['name'], files))
    return groups


def legacy_files():
    return [path for name, files in corpus_groups() if name != 'Original Firmware' for path in files]


def historical_input(value):
    """Resolve input names recorded in preserved pre-layout corpus reports."""
    path = Path(value)
    if path.parts and path.parts[0] == 'Original Firmware':
        return ORIGINALS.joinpath(*path.parts[1:])
    prefix = ('Firmware-Patcher', 'tests', 'fixtures', 'legacy')
    if path.parts[:4] == prefix:
        if path.parts[4:5] == ('Access-Control-Patch',):
            return RELEASES.joinpath(*path.parts[5:])
        return LEGACY.joinpath(*path.parts[4:])
    return PROJECT_ROOT / path
