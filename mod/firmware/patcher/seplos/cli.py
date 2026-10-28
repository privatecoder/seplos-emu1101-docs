"""Bounded child pipeline and no-overwrite publication after mandatory tests."""
from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess,sys,tempfile,time,traceback
from .image import Image
from .profiles import SUPPORTED_VERSIONS,require_profile,require_mode

HERE=Path(__file__).resolve().parents[1]
SCHEMA='seplos-patcher-report-1'


def worker_job(source,out,mode,revision,hard_stop,maint_version):
 require_profile(maint_version);require_mode(mode)
 positive_flags=True
 import resource
 resource.setrlimit(resource.RLIMIT_CPU,(75,80))
 resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
 from .analysis import discover
 from .guards import guard
 report={'schema':SCHEMA,'tool_version':'2.0.0','mode':mode,'maint_version':maint_version,'positive_flags':positive_flags,'input':str(source),'status':'refused','stage':'container','tests':[]}
 started=time.monotonic()
 try:
  if not __debug__:raise RuntimeError('Python -O is unsupported: assertions must be enabled')
  if source.stat().st_size>2*1024*1024:raise ValueError('input exceeds 2 MiB container limit')
  raw=source.read_bytes();report['input_file_sha256']=hashlib.sha256(raw).hexdigest()
  im=Image.parse(raw.decode('ascii'));report['input_app_sha256']=im.sha
  report['stage']='discovery';facts=discover(im);report['facts']=facts
  report['stage']='complete-code-contracts';guard(im,facts)
  from .hardstop import locate,apply,validate_hardstop
  facts['hard_stop']=locate(im,facts)
  report['hard_stop']={**facts['hard_stop'],'requested':hard_stop}
  report['stage']='OEM-execution-probes'
  from .machine import probe
  probe(im,facts)
  if mode=='analyze':
   if maint_version.startswith('1.6'):
    from .cutoff import discover_cutoff
    report['stage']='cutoff-code-contracts';discover_cutoff(im,facts)
   if maint_version.count('.')==2:
    from .marker_uart0 import discover_marker_uart0
    report['stage']='UART0-marker-contract';discover_marker_uart0(im,facts)
   if maint_version=='1.6.3':
    from .service import discover_service
    report['stage']='service-contract';discover_service(im,facts)
   if maint_version=='1.5.3':
    from .storage_diagnostics import discover_diagnostics
    report['stage']='storage_diagnostics-contract';discover_diagnostics(im,facts)
   if maint_version=='1.6.3':
    from .configurable_hardstop import discover_configurable
    report['stage']='configurable_hardstop-contract';discover_configurable(im,facts)
   report.update(status='compatible',stage='complete')
  else:
   from .build import build
   from .selftest import validate
   report['stage']='build';candidate,built=build(im,facts,revision,hard_stop=='enable',maint_version=maint_version)
   assembly=built.pop('resolved_assembly');disassembly=built.pop('disassembly');report['build']=built
   report['stage']='mandatory-emulator-tests'
   report['tests']=validate(im,candidate,facts,built)
   if hard_stop=='enable':
    hs_image,hs_detail=apply(im,facts)
    report['tests'].extend(validate_hardstop(im,hs_image,facts,hs_detail))
   output=candidate.render().encode('ascii')
   report['output_file_sha256']=hashlib.sha256(output).hexdigest()
   # Staging is private. The parent publishes only after exit and report validation.
   (out/'firmware.ehex').write_bytes(output)
   (out/'payload.resolved.s').write_text(assembly)
   (out/'payload.dis').write_text(disassembly)
   report.update(status='passed',stage='complete',suite='maint'+maint_version.replace('.','')+'-real-thumb-v1',suite_complete=True)
 except Exception as exc:
  report['error']=f'{type(exc).__name__}: {exc}'
  report['traceback']=traceback.format_exc()
  if report['stage'] in ('mandatory-emulator-tests','hard-stop-tests'):report['status']='test_failed'
 report['elapsed_seconds']=round(time.monotonic()-started,3)
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 return 0 if report['status'] in ('passed','compatible') else 1


def run_worker(source,mode,revision=255,timeout=120,worker=None,hard_stop='preserve',*,maint_version):
 require_profile(maint_version);require_mode(mode)
 positive_flags=True
 source=Path(source).resolve();worker=Path(worker or HERE/'seplos_patch.py')
 fallback={'schema':SCHEMA,'input':str(source),'status':'worker_failed','mode':mode}
 with tempfile.TemporaryDirectory(prefix='seplos-worker-') as tmp:
  tmp=Path(tmp)
  args=[sys.executable,'-I',str(worker),'_worker',str(source),'--out',str(tmp),'--mode',mode,'--base-revision',str(revision),'--hard-stop',hard_stop,'--maint-version',maint_version]
  proc=subprocess.Popen(args,cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  try:
   stdout,stderr=proc.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate()
   fallback['error']='worker exceeded wall-clock limit';return fallback,{}
  if proc.returncode not in (0,1) or not (tmp/'report.json').is_file():
   fallback.update(error=f'worker exit/signal {proc.returncode}; no complete result',stderr=stderr.decode(errors='replace')[-4000:]);return fallback,{}
  try:
   report=json.loads((tmp/'report.json').read_text())
   if report.get('schema')!=SCHEMA or report.get('mode')!=mode:raise ValueError('incomplete report schema')
   if report.get('maint_version')!=maint_version:raise ValueError('worker profile differs from request')
   if report.get('positive_flags',False)!=positive_flags:raise ValueError('worker polarity differs from request')
   if report.get('status') not in ('passed','compatible'):return report,{}
   if proc.returncode!=0 or report.get('stage')!='complete':raise ValueError('inconsistent worker completion')
   if hashlib.sha256(source.read_bytes()).hexdigest()!=report['input_file_sha256']:raise ValueError('input changed while processing')
   if mode=='analyze':return report,{}
   tests=report.get('tests',[])
   expected_suite='maint'+maint_version.replace('.','')+'-real-thumb-v1'
   if report.get('suite')!=expected_suite or report.get('suite_complete') is not True or len(tests)<60 or not all(t.get('passed') is True for t in tests):raise ValueError('mandatory suite incomplete')
   if mode=='patch' and maint_version.startswith('1.6') and (report['build'].get('patch_version')!=maint_version or len([t for t in tests if t.get('name','').startswith('cutoff-')])<30):raise ValueError('mandatory1.6 suite incomplete')
   if mode=='patch':
    built=report['build']
    if built.get('patch_version')!=maint_version:raise ValueError('worker version differs from request')
    if maint_version.count('.')==2:
     from .marker_uart0_tests import REQUIRED
     if built.get('info_format')!=4 or built.get('info_bytes')!=19 or not built.get('uart0_marker') or not built.get('image_flags',0)&16:raise ValueError('revision UART0 marker contract missing')
     if not set(REQUIRED)<={t['name'] for t in tests}:raise ValueError('mandatory UART0 marker suite incomplete')
    if maint_version=='1.6.3':
     from .service_tests import REQUIRED
     if not built.get('service') or not built.get('extended_diagnostics') or not built.get('checkpoint_before_reset') or built.get('image_flags',0)&0x60!=0x60:raise ValueError('service capabilities missing')
     if not set(REQUIRED)<={t['name'] for t in tests}:raise ValueError('mandatory service suite incomplete')
    if maint_version=='1.5.3':
     from .storage_diagnostics_tests import REQUIRED
     if not built.get('storage_diagnostics') or not built.get('extended_diagnostics') or built.get('image_flags',0)&0xfe!=0x3a or built.get('cutoff') or built.get('checkpoint_before_reset') or built.get('ram_bytes')!=0:raise ValueError('storage_diagnostics capability contract missing')
     expected={**report.get('facts',{}).get('hooks',{}),**report.get('facts',{}).get('marker_uart0',{}).get('hooks',{})}
     if len(expected)!=5 or built.get('hooks')!=expected:raise ValueError('storage_diagnostics five-hook contract missing')
     if not set(REQUIRED)<={t['name'] for t in tests}:raise ValueError('mandatory storage_diagnostics suite incomplete')
    if maint_version=='1.6.3':
     from .configurable_hardstop_tests import REQUIRED
     if not built.get('configurable_hard_stop') or built.get('image_flags',0)&0xfe!=0xfe or type(built.get('hard_stop_default')) is not bool or bool(built.get('image_flags',0)&1)!=built['hard_stop_default']:raise ValueError('configurable_hardstop capability/default contract missing')
     h=report.get('facts',{}).get('configurable_hardstop',{})
     if len(built.get('hooks',{}))!=21 or built['hooks'].get('hook_configurable_hard_stop')!=h.get('site') or built.get('ram_bytes')!=4:raise ValueError('configurable_hardstop hook/RAM contract missing')
     if not set(REQUIRED)<={t['name'] for t in tests}:raise ValueError('mandatory configurable_hardstop suite incomplete')
    if built.get('positive_flags',False)!=positive_flags or bool(built.get('image_flags',0)&8)!=positive_flags:raise ValueError('build polarity differs from request')
    if positive_flags and maint_version.startswith('1.6'):
     from .permissions_tests import REQUIRED
     if not set(REQUIRED)<={t['name'] for t in tests}:raise ValueError('mandatory positive-flag suite incomplete')
   output=(tmp/'firmware.ehex').read_bytes()
   if hashlib.sha256(output).hexdigest()!=report['output_file_sha256']:raise ValueError('output digest mismatch')
   candidate=Image.parse(output.decode('ascii'))
   if candidate.sha!=report['build']['app_sha256']:raise ValueError('app digest mismatch')
   names=('firmware.ehex','payload.resolved.s','payload.dis')
   return report,{name:(tmp/name).read_bytes() for name in names}
  except Exception as exc:
   fallback['error']=str(exc);return fallback,{}


def publish(out,report,artifacts):
 out=Path(out)
 out.mkdir(parents=False,exist_ok=False)  # Exclusive claim; never replace a directory.
 for name in ('payload.resolved.s','payload.dis'):
  if name in artifacts:
   with (out/name).open('xb') as stream:stream.write(artifacts[name])
 with (out/'report.json').open('x',encoding='utf-8') as stream:
  json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
 if 'firmware.ehex' in artifacts:
  # Atomic no-replace hard link within one filesystem; firmware appears last.
  with tempfile.NamedTemporaryFile(dir=out,prefix='.candidate-',delete=False) as stream:
   stream.write(artifacts['firmware.ehex']);stream.flush();os.fsync(stream.fileno());staged=Path(stream.name)
  try:os.link(staged,out/'firmware.ehex')
  finally:staged.unlink()


def main(argv=None):
 p=argparse.ArgumentParser(description='Offline OEM analysis + mandatory tested MAINT1.5.3/1.6.3 patch. Never flashes hardware.')
 sub=p.add_subparsers(dest='command',required=True)
 for name in ('analyze','patch','_worker'):
  q=sub.add_parser(name,help='private bounded worker' if name=='_worker' else name)
  q.add_argument('input',type=Path);q.add_argument('--out',required=True,type=Path,help='new output directory; parent must exist')
  q.add_argument('--base-revision',type=int,default=255,help='explicit OEM third component 0..254; default 255=unknown (not inferred from filename)')
  q.add_argument('--hard-stop',choices=('preserve','enable'),default='preserve',help='patch: preserve existing charge-inhibit behavior (default), or enable SP80 hard stop (1.6.3: default for legacy config)')
  q.add_argument('--maint-version',choices=SUPPORTED_VERSIONS,required=True,help='required current MAINT profile; positive permissions are automatic')
  if name=='_worker':q.add_argument('--mode',required=True,choices=('analyze','patch'))
 args=p.parse_args(argv)
 if not 0<=args.base_revision<=255:p.error('base revision must be 0..255')
 if args.command=='_worker':return worker_job(args.input,args.out,args.mode,args.base_revision,args.hard_stop,args.maint_version)
 if args.out.exists() or args.out.is_symlink():p.error('output path already exists; overwrite refused')
 if not args.out.parent.is_dir():p.error('output parent directory must exist')
 report,artifacts=run_worker(args.input,args.command,args.base_revision,hard_stop=args.hard_stop,maint_version=args.maint_version)
 try:publish(args.out,report,artifacts)
 except OSError as exc:p.error(str(exc))
 print(json.dumps({'status':report['status'],'report':str(args.out/'report.json'),'tests_passed':len(report.get('tests',[])),'firmware':str(args.out/'firmware.ehex') if artifacts else None,'error':report.get('error')},ensure_ascii=False))
 return 0 if report['status'] in ('passed','compatible') else 1
