#!/usr/bin/env python3
"""Sequential current-MAINT updates over local UART0, offline plan by default.

COUNT 12: --mode master targets 0..11; --mode external targets 1..12.
Only --execute opens a port. External requesters must already be stopped.
An active maintenance marker does not change master address 0. Recovery is
never automatic; a failed/uncertain transaction stops the whole batch.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _paths import PROJECT_ROOT,PATCHER_ROOT,LOCAL_ROOT
import argparse,hashlib,importlib.util,json,os,uuid
from datetime import datetime,timezone


def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

transport=load('pack_batch_transport',Path(__file__).with_name('batch_transport.py'))
SerialBackend=transport.SerialBackend
METADATA_ROOT=PROJECT_ROOT/'mod/firmware/releases'


def plan_addresses(count,mode):
 if mode not in ('master','external'):raise ValueError('mode must be master or external')
 maximum=16 if mode=='master' else 15
 if type(count) is not int or not 1<=count<=maximum:raise ValueError(f'{mode}: count must be 1..{maximum} (normal DIP addresses only)')
 start=0 if mode=='master' else 1
 return list(range(start,start+count))


def load_release(profile,image=None,metadata_dir=None):
 if profile not in ('light','full'):raise ValueError('profile must be light or full')
 path=Path(metadata_dir or METADATA_ROOT)/f'maint-{profile}.json';meta_raw=path.read_bytes();meta=json.loads(meta_raw)
 name=meta['name']
 if Path(name).name!=name or name in ('.','..') or not name.endswith('.ehex'):raise ValueError('Release name must be a plain EHEX filename')
 if not meta['patch_version'].startswith('1.5.' if profile=='light' else '1.6.'):raise ValueError('Release profile/version mismatch')
 image=Path(image or LOCAL_ROOT/'releases'/name).resolve();raw=image.read_bytes()
 sys.path.insert(0,str(PATCHER_ROOT))
 verifier=load('batch_release_verifier',PATCHER_ROOT/'verify_releases.py')
 verifier.verify_existing(raw,meta)
 prepared=transport.flasher.prepare_bytes(raw)
 # A path changed between validation and preparation must not be flashed.
 if image.read_bytes()!=raw:raise ValueError('Image changed during validation')
 return dict(metadata=meta,image_path=image,metadata_path=path.resolve(),
             metadata_sha256=hashlib.sha256(meta_raw).hexdigest(),prepared=prepared)


def check_source(release):
 if hashlib.sha256(release['image_path'].read_bytes()).hexdigest()!=release['metadata']['ehex_sha256']:
  raise ValueError('Image changed since validation; no further flash')
 if release.get('metadata_path') and hashlib.sha256(release['metadata_path'].read_bytes()).hexdigest()!=release['metadata_sha256']:
  raise ValueError('Release metadata changed since validation; no further flash')


def public_plan(plan):
 meta=plan['release']['metadata']
 return dict(count=plan['count'],mode=plan['mode'],addresses=plan['addresses'],profile=plan['profile'],
             image=str(plan['release']['image_path']),patch_version=meta['patch_version'],
             build_id=meta['build_id'],ehex_sha256=meta['ehex_sha256'],gap_ms=plan['gap_ms'])


def save_json(path,data,replace=False):
 path=Path(path)
 if not replace:
  with path.open('x') as f:json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  return
 temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with temp.open('x') as f:json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()


def validate_snapshot(snapshot,address):
 if snapshot.get('address')!=address:raise ValueError('Snapshot belongs to another target')
 for field,size in (('version_hex',32),('parameters_hex',169),('battery_sn_hex',30),('bms_sn_hex',30)):
  if len(bytes.fromhex(snapshot[field]))!=size:raise ValueError('Invalid snapshot '+field)
 raw=bytes.fromhex(snapshot['parameters_hex'])
 if raw[0]!=address:raise ValueError('Foreign parameter payload')
 transport.parameters.decode_parameters(raw[1:],address)
 if raw[158]&32:raise ValueError(f'Pack {address}: automatic addressing Group7.Bit5 must be off')
 serial=bytes.fromhex(snapshot['bms_sn_hex'])
 if not serial.strip(b'\0 \xff0'):raise ValueError(f'Pack {address}: placeholder/empty BMS serial; unique identity required')
 return serial


def guard_light_downgrade(snapshot,profile):
 info=snapshot.get('info') or {}
 if profile!='light' or not info.get('image_flags',0)&4:return
 raw=bytes.fromhex(snapshot['parameters_hex']);diag=snapshot.get('diagnostics')
 if not raw[151]&32:raise ValueError('Active individual lock: do not downgrade to light; no automatic unlock')
 if not diag:raise ValueError('Cannot establish persisted lock state before light downgrade')
 p=diag['parameters']
 if (p['primary']!='valid' or p['backup']!='valid' or p['primary_lock'] is not False or p['backup_lock'] is not False
     or diag['runtime_lock'] is not False or not diag['runtime_magic_valid'] or not diag['runtime_consistent']):
  raise ValueError('Stored/runtime lock active or uncertain; light downgrade blocked')


def require_paused(status):
 # OEM with manually halted polling has no 64/02; full baseline reachability
 # and passive silence are still required. Current MAINT must report zero.
 if status is None:return
 if status['flag'] not in (0,1) or status['effective_slaves']!=0:
  raise RuntimeError('Master polling is not confirmed paused, or its marker is unknown')


def compare_baseline(before,current):
 for field in ('version_hex','parameters_hex','battery_sn_hex','bms_sn_hex','info_hex'):
  if before.get(field)!=current.get(field):raise RuntimeError('Target changed since bank backup: '+field)


def verify_after(before,after,meta):
 address=before['address'];validate_snapshot(after,address)
 for field in ('parameters_hex','battery_sn_hex','bms_sn_hex'):
  if bytes.fromhex(before[field])!=bytes.fromhex(after[field]):raise RuntimeError('Post-flash readback differs: '+field)
 if bytes.fromhex(after['info_hex'] or '')!=bytes.fromhex(meta['info_hex']):raise RuntimeError('Post-flash MAINT build/flags/capabilities differ from selected image')
 # 51 carries only the two-byte OEM family version, not an exact patch ID.
 if bytes.fromhex(after['version_hex'])[10:12]!=bytes.fromhex(meta['info_hex'])[4:6]:raise RuntimeError('Post-flash OEM family version mismatch')


def verify_measurements(before,after):
 if not before.get('telemetry_hex'):return
 old=bytes.fromhex(before['telemetry_hex']);new=bytes.fromhex(after.get('telemetry_hex',''))
 if len(old)!=75 or len(new)!=75 or old[:3]!=new[:3] or new[:3]!=bytes([0,before['address'],16]):raise RuntimeError('Incomplete or changed 16S telemetry after flash')
 for offset in (*range(3,35,2),50):
  if int.from_bytes(old[offset:offset+2],'big') and not int.from_bytes(new[offset:offset+2],'big'):
   raise RuntimeError('Previously present cell/pack measurement became zero after flash')


def run_batch(plan,backend_factory,out):
 check_source(plan['release']);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 report=dict(plan=public_plan(plan),status='running',phase='preflight',verified_addresses=[],failed_address=None,
             maintenance_cleared=False,results=[])
 report_path=out/'report.json';save_json(report_path,report);backend=None
 def record(phase,address=None):
  report.update(phase=phase,current_address=address);save_json(report_path,report,replace=True)
 try:
  with (out/'bus.log').open('x') as log,backend_factory(log) as backend:
   if plan['mode']=='master':backend.prepare_master()
   for key in ('maintenance_started','maintenance_start_attempted','maintenance_pause_confirmed'):report[key]=getattr(backend,key,False)
   backend.quiet();backend.no_bootloader()
   if plan['mode']=='external':backend.no_pack_zero()
   else:require_paused(backend.master_status())
   baselines={};serials=set()
   for address in plan['addresses']:
    record('bank-backup',address);snapshot=backend.snapshot(address)
    save_json(out/f'pack-{address:02d}-before.json',snapshot)
    serial=validate_snapshot(snapshot,address);guard_light_downgrade(snapshot,plan['profile'])
    if serial in serials:raise ValueError('Duplicate BMS serial across intended addresses')
    serials.add(serial);baselines[address]=snapshot
   for address in plan['addresses']:
    record('target-preflight',address);check_source(plan['release'])
    backend.quiet();backend.no_bootloader()
    if plan['mode']=='master':require_paused(backend.master_status())
    else:backend.no_pack_zero()
    current=backend.snapshot(address);validate_snapshot(current,address);guard_light_downgrade(current,plan['profile'])
    compare_baseline(baselines[address],current)
    print(f'Pack {address:02d}: backup/identity confirmed; starting one flash.',file=sys.stderr,flush=True)
    record('flashing',address);result=backend.flash(plan['release'],address,plan['gap_ms'])
    record('verifying',address);backend.settle();after=backend.snapshot(address)
    save_json(out/f'pack-{address:02d}-after.json',after)
    verify_after(baselines[address],after,plan['release']['metadata']);verify_measurements(baselines[address],after)
    if plan['mode']=='master':require_paused(backend.master_status())
    report['verified_addresses'].append(address);report['results'].append(dict(address=address,verified=True,flash=result))
    record('verified',address);print(f'Pack {address:02d}: exact MAINT identity, parameters and serials verified.',file=sys.stderr,flush=True)
   report.update(status='verified',phase='complete',current_address=None);save_json(report_path,report,replace=True)
   return report
 except BaseException as error:
  if backend is not None:
   for key in ('maintenance_started','maintenance_start_attempted','maintenance_pause_confirmed'):report[key]=getattr(backend,key,False)
  report.update(status='failed',failed_address=report.get('current_address'),error=str(error),
                error_type=type(error).__name__,automatic_recovery=False)
  save_json(report_path,report,replace=True);raise


def port_key(value):
 p=Path(value).resolve();name=p.name
 if name.startswith(('cu.','tty.')):name=name.split('.',1)[1]
 return str(p.parent/name)


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('count',type=lambda text:int(text,10),help='Number of packs, decimal; not the highest address')
 parser.add_argument('--mode',required=True,choices=('master','external'),help='master: addresses 0..N-1; external: 1..N')
 parser.add_argument('--profile',required=True,choices=('light','full'),help='Current reviewed MAINT release')
 parser.add_argument('--image',type=Path,help='Alternate path to the exact same release bytes')
 parser.add_argument('--port',help='UART0 USB-RS485 adapter at 19200 baud')
 parser.add_argument('--maintenance-port',help='Optional separate UART1 adapter at 9600 baud; master mode only')
 parser.add_argument('--gap-ms',type=int,default=350)
 parser.add_argument('--out',type=Path,help='Fresh batch directory (default under local/devices/flash-logs)')
 group=parser.add_mutually_exclusive_group();group.add_argument('--execute',action='store_true',help='Actually update devices; default is offline plan only');group.add_argument('--dry-run',action='store_true')
 args=parser.parse_args(argv)
 try:
  addresses=plan_addresses(args.count,args.mode)
  if not 0<=args.gap_ms<=1000:raise ValueError('--gap-ms must be 0..1000')
  if args.maintenance_port and args.mode!='master':raise ValueError('--maintenance-port only applies to master mode')
  if args.port and args.maintenance_port and port_key(args.port)==port_key(args.maintenance_port):raise ValueError('UART0 and UART1 adapters must be different physical ports')
  if args.execute and not args.port:raise ValueError('--execute requires --port')
  release=load_release(args.profile,args.image)
  plan=dict(count=args.count,mode=args.mode,profile=args.profile,addresses=addresses,release=release,gap_ms=args.gap_ms)
  if not args.execute:print(json.dumps(public_plan(plan),indent=2));return 0
  out=args.out or LOCAL_ROOT/'devices/flash-logs'/('batch-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
  print('Batch logs/backups: '+str(out),file=sys.stderr,flush=True)
  result=run_batch(plan,lambda log:SerialBackend(args.port,log,args.maintenance_port),out)
  print(json.dumps(result,indent=2));return 0
 except (OSError,ValueError,RuntimeError) as error:
  print(f'Error: {error}\nBatch stopped; no automatic recovery, retry or maintenance clear.',file=sys.stderr);return 1
 except KeyboardInterrupt:
  print('Interrupted; no automatic recovery or maintenance clear. Check the batch report.',file=sys.stderr);return 130

if __name__=='__main__':raise SystemExit(main())
