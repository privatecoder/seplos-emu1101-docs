"""Shared source, vendor and ignored-data locations for offline tools.

Paths derive from this source file; no command needs the project as its cwd.
Firmware fixtures are files in local/, never links inside the public mod tree.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

TOOLS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_ROOT.parent.parent
PATCHER_ROOT = PROJECT_ROOT / 'mod/firmware/patcher'
LOCAL_ROOT = PROJECT_ROOT / 'local'


def analysis_arguments(usage):
    """Parse the shared data directory while preserving classic positional CLIs."""
    parser = argparse.ArgumentParser(description=usage, usage='%(prog)s --data-dir DIR ' + usage)
    parser.add_argument('--data-dir', type=Path, required=True, help='Directory containing vVERSION.raw and vVERSION.dis')
    args, remaining = parser.parse_known_args()
    sys.argv[1:] = remaining
    return args.data_dir.resolve()


def research_input(name, *, root=PROJECT_ROOT, registry=None):
    """Require one exact reviewed input before a native research probe runs.

    This registry binds reports to their preserved source bytes. It is separate
    from the firmware corpus and never turns cached analysis into patch approval.
    Unknown names, missing files and stale reports fail without path searching.
    """
    registry = Path(registry) if registry is not None else TOOLS_ROOT / 'research-inputs.json'
    data = json.loads(registry.read_text())
    if data.get('schema') != 1:
        raise ValueError('unsupported research input registry schema')
    try:
        entry = data['inputs'][name]
    except KeyError as exc:
        raise KeyError('unknown research input: ' + name) from exc
    relative = Path(entry['path'])
    if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
        raise ValueError('research input path must be project relative: ' + str(relative))
    path = Path(root) / relative
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'missing research input {name}: {path}') from exc
    if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError(f'research input integrity mismatch {name}: {path}')
    return path
