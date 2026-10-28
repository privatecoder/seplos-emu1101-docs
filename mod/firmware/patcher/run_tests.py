#!/usr/bin/env python3
"""Persist standard-library unittest results and the tool bundle fingerprint."""
from pathlib import Path
import argparse,hashlib,json,platform,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))


def main():
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 log=a.report.with_suffix('.log')
 if a.report.exists() or log.exists():p.error('report/log already exists')
 root=Path(__file__).resolve().parent
 suite=unittest.defaultTestLoader.discover(str(root/'tests'))
 with log.open('x') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 paths=sorted((root/'seplos').glob('*.py'))+sorted((root/'seplos').glob('*.s'))+sorted((root/'seplos').glob('*.json'))+sorted(root.glob('*.py'))+sorted(root.glob('*.json'))+[root/'requirements.txt']
 files={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
 import unicorn
 report={'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'python':platform.python_version(),'unicorn':unicorn.__version__,'bundle_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),'files':files,'log':log.name}
 with a.report.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
 print(json.dumps({k:report[k] for k in ('passed','tests','failures','errors','python','unicorn','bundle_sha256')}))
 return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
