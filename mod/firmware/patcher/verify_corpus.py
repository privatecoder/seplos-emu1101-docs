#!/usr/bin/env python3
"""Reproducible local matrix; snapshots inputs before generating any outputs."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from seplos.cli import run_worker,publish
from seplos.profiles import SUPPORTED_VERSIONS
from corpus import PROJECT_ROOT, corpus_groups


def main():
 p=argparse.ArgumentParser();p.add_argument('--firmware-root',type=Path,default=PROJECT_ROOT);p.add_argument('--out',type=Path,required=True);p.add_argument('--maint-version',choices=SUPPORTED_VERSIONS,required=True)
 a=p.parse_args();root=a.firmware_root.resolve();out=a.out.resolve()
 if out.exists():p.error('matrix output already exists')
 try:groups=corpus_groups(root)
 except FileNotFoundError as exc:p.error(str(exc))
 files=[(name,path) for name,paths in groups for path in paths]
 out.mkdir();matrix=[]
 for index,(group,path) in enumerate(files):
  for mode,hard in (('patch','preserve'),('patch','enable')):
   profile='maint'+a.maint_version.replace('.','')+('-preserve' if hard=='preserve' else '-hard-stop')
   dest=out/f'{index:02d}-{profile}'
   report,artifacts=run_worker(path,mode,hard_stop=hard,maint_version=a.maint_version)
   publish(dest,report,artifacts)
   already=group not in ('Original Firmware','Hard-Stop')
   small='16.04.06' in path.name and mode=='patch'
   old_gate=a.maint_version.startswith('1.6') and mode=='patch' and any(v in path.name for v in ('16.06.03','16.06.04','16.06.05'))
   expected='refused' if already or small or old_gate else 'passed'
   actual=report['status']
   if small:
    valid=actual=='refused' and 'UART1 buffers too small' in report.get('error','')
   elif old_gate and not already:valid=actual=='refused' and 'unsupported MAINT1.6 gate ABI' in report.get('error','')
   else:valid=actual==expected
   row={'input':str(path.relative_to(root)),'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'profile':profile,'expected':expected,'status':actual,'expected_result':valid,'tests':len(report.get('tests',[])),'report':str(dest.relative_to(out)/'report.json'),'output_sha256':report.get('output_file_sha256'),'reason':report.get('error')}
   matrix.append(row);print(json.dumps({k:row[k] for k in ('input','profile','status','tests','expected_result','reason')},ensure_ascii=False),flush=True)
 (out/'matrix.json').write_text(json.dumps({'inputs':len(files),'runs':len(matrix),'all_expected':all(r['expected_result'] for r in matrix),'results':matrix},ensure_ascii=False,indent=2)+'\n')
 lines=['# Firmware test matrix','',f'{len(files)} inputs, {len(matrix)} profile checks. No hardware flash.','', '| Input | Profile | Result | Tests | Report |','|---|---|---|---:|---|']
 for r in matrix:lines.append(f"| {r['input']} | {r['profile']} | {r['status']} | {r['tests']} | [JSON]({r['report']}) |")
 (out/'README.md').write_text('\n'.join(lines)+'\n')
 return 0 if all(r['expected_result'] for r in matrix) else 1
if __name__=='__main__':raise SystemExit(main())
