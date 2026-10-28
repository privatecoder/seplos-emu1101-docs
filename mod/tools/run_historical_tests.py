#!/usr/bin/env python3
"""List or execute the retained, frozen offline historical test suites.

The default action only lists suites and prerequisites. Execution requires
--suite and a fresh --out directory. Each job runs in its own Python process
with -I -B and /private/tmp as cwd. No installation, network, device access or
permission escalation is performed by this runner. Frozen native tests need
appropriate execution permissions supplied by the caller.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

MANIFEST = Path(__file__).with_name('historical-tests.json')
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ignored(path):
    return path.name == '.DS_Store' or '__pycache__' in path.parts or path.suffix == '.pyc'


def verify_inventory(workspace, inventory):
    """Check the full frozen tree before any archived Python is executed."""
    root = workspace/'mod'
    if not root.is_dir():
        raise ValueError('Missing historical mod directory: ' + str(root))
    if not inventory.is_file():
        raise ValueError('Missing historical source inventory: ' + str(inventory))
    rows = json.loads(inventory.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Historical source inventory must be a nonempty list')
    expected = set()
    for row in rows:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
            raise ValueError('Invalid inventory path: ' + str(relative))
        if ignored(relative):
            continue
        if relative in expected:
            raise ValueError('Duplicate inventory path: ' + str(relative))
        expected.add(relative)
        path = root/relative
        if row['type'] == 'symlink':
            if not path.is_symlink() or os.readlink(path) != row['target']:
                raise ValueError('Missing or changed historical symlink: ' + str(relative))
            if not path.exists():
                raise ValueError('Missing historical symlink target: ' + str(relative))
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Historical source symlink escapes mod: ' + str(relative))
        elif row['type'] == 'file':
            if path.is_symlink() or not path.is_file():
                raise ValueError('Missing historical source file: ' + str(relative))
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Historical source checksum mismatch: ' + str(relative))
        else:
            raise ValueError('Unknown inventory entry type: ' + str(relative))
    actual = {path.relative_to(root) for path in root.rglob('*') if (path.is_file() or path.is_symlink()) and not ignored(path)}
    extra = actual - expected
    if extra:
        raise ValueError('Unlisted historical source: ' + ', '.join(map(str, sorted(extra))))
    return hashlib.sha256(inventory.read_bytes()).hexdigest()


def run_job(job, workspace, output):
    """Run one known suite and require a successful positive test count."""
    identifier = job['id']
    command = [sys.executable, '-I', '-B']
    native = output/(identifier + '.native.json')
    if job['kind'] == 'patcher':
        command += [str(workspace/'mod'/job['runner']), '--report', str(native)]
    else:
        command += ['-m', 'unittest', 'discover', '-s', str(workspace/'mod'/job['directory']), '-v']
    started = time.monotonic()
    with (output/(identifier+'.log')).open('x') as log:
        result = subprocess.run(command, cwd='/private/tmp', stdout=log, stderr=subprocess.STDOUT)
    report = dict(id=identifier, suite=job['suite'], command=command, returncode=result.returncode, seconds=round(time.monotonic()-started,3), tests=0, passed=False, log=identifier+'.log')
    if job['kind'] == 'patcher':
        try:
            source = json.loads(native.read_text())
            count = source['tests']
            report['tests'] = count
            report['passed'] = result.returncode == 0 and source['passed'] is True and type(count) is int and count > 0 and source.get('failures') == 0 and source.get('errors') == 0
        except (OSError, ValueError, KeyError, TypeError) as error:
            report['error'] = 'Invalid or missing native report: ' + str(error)
    else:
        text = (output/report['log']).read_text()
        matches = re.findall(r'^Ran (\d+) tests? in ', text, re.MULTILINE)
        report['tests'] = int(matches[-1]) if matches else 0
        report['passed'] = result.returncode == 0 and report['tests'] > 0 and bool(re.search(r'^OK\s*$',text,re.MULTILINE))
    if not report['passed'] and 'error' not in report:
        report['error'] = 'Child failed or no positive successful test count was reported'
    (output/(identifier+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--list', action='store_true', help='List frozen jobs and prerequisites; no archive needed (default action)')
    parser.add_argument('--suite', choices=('legacy','device','patcher','all'))
    parser.add_argument('--out', type=Path, help='Fresh directory for per-job logs and JSON reports')
    parser.add_argument('--workspace', type=Path, help='Historical project directory containing mod, vendor and local')
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text())
    if args.list and args.suite:
        parser.error('--list and --suite cannot be combined')
    if not args.suite:
        if args.out:
            parser.error('--out requires an explicit --suite')
        for job in manifest['jobs']:
            print('%s: %s (%s)' % (job['suite'],job['id'],job['directory']))
        print('Default workspace: ' + manifest['default_workspace'])
        for requirement in manifest['requirements']:
            print('Requires: ' + requirement)
        return 0
    if args.out is None:
        parser.error('--suite requires --out FRESH_DIR')
    workspace = (args.workspace or PROJECT_ROOT/manifest['default_workspace']).resolve()
    if args.out.exists() or args.out.is_symlink():
        print('Output path already exists: ' + str(args.out), file=sys.stderr)
        return 1
    output = args.out.resolve()
    jobs = [job for job in manifest['jobs'] if args.suite == 'all' or job['suite'] == args.suite]
    try:
        fingerprint = verify_inventory(workspace, workspace/manifest['inventory'])
        for job in jobs:
            directory = workspace/'mod'/job['directory']
            if not directory.is_dir() or not list(directory.glob('test*.py')):
                raise ValueError('Missing or empty historical test directory: ' + str(directory))
            if job['kind'] == 'patcher' and not (workspace/'mod'/job['runner']).is_file():
                raise ValueError('Missing historical patcher runner')
        output.mkdir(parents=True, exist_ok=False)
        reports = [run_job(job,workspace,output) for job in jobs]
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error),file=sys.stderr)
        return 1
    passed = bool(reports) and all(report['passed'] for report in reports)
    summary = dict(passed=passed, workspace=str(workspace), inventory_sha256=fingerprint, tests=sum(report['tests'] for report in reports), jobs=reports)
    (output/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=passed,tests=summary['tests'],jobs=len(reports),report=str(output/'report.json'))))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
