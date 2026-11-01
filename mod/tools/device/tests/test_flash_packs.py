"""Offline sequential-update state machine; no device or TCP access."""
import contextlib,copy,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]

def load(test,name):
 p=HERE/(name+'.py');test.assertTrue(p.is_file(),name+' feature missing')
 spec=importlib.util.spec_from_file_location('batch_test_'+name,p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

class BatchTests(unittest.TestCase):
 def setUp(self):
  self.m=load(self,'flash_packs');self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.image=self.root/'image.ehex';self.image.write_bytes(b'input-pinned-for-model')
  import hashlib
  self.meta=dict(name='image.ehex',patch_version='1.6.4',build_id='a8676b52bae281ff',image_flags=254,info_format=5,remote_capabilities=15,info_hex='4D4E540510060D010604A8676B52BAE281FFFE000F',ehex_sha256=hashlib.sha256(self.image.read_bytes()).hexdigest())
 def plan(self,count=3,mode='master',profile='full'):
  return dict(count=count,mode=mode,profile=profile,addresses=self.m.plan_addresses(count,mode),release=dict(metadata=copy.deepcopy(self.meta),image_path=self.image,prepared=('synthetic',)),gap_ms=350)
 def backend(self,plan):
  class Backend:
   def __init__(b):b.events=[];b.calls={};b.flashed=[];b.after_change=None;b.fail=None;b.quiet_fail=False;b.boot=False;b.zero=False;b.status=dict(marker=0,flag=1,effective_slaves=0);b.closed=False;b.states={a:self.snapshot(a) for a in plan['addresses']}
   def __enter__(b):return b
   def __exit__(b,*args):b.closed=True
   def prepare_master(b):b.events.append(('prepare-master',))
   def quiet(b):
    b.events.append(('quiet',))
    if b.quiet_fail:raise RuntimeError('unexpected bus traffic')
   def no_bootloader(b):
    b.events.append(('no-bootloader',))
    if b.boot:raise RuntimeError('bootloader already present')
   def no_pack_zero(b):
    b.events.append(('no-zero',))
    if b.zero:raise RuntimeError('address zero present')
   def master_status(b):b.events.append(('master-status',));return b.status
   def snapshot(b,a):
    b.events.append(('snapshot',a));b.calls[a]=b.calls.get(a,0)+1;s=copy.deepcopy(b.states[a])
    if a in b.flashed and b.after_change:b.after_change(s)
    return s
   def settle(b):b.events.append(('settle',))
   def flash(b,release,address,gap):
    b.events.append(('flash',address));b.flashed.append(address)
    # Every target backup must exist before the first reset/flash.
    for a in plan['addresses']:assert (self.root/'run'/f'pack-{a:02d}-before.json').is_file()
    if b.fail==address:raise RuntimeError('uncertain WFD ACK; no retry')
    return dict(blocks=1)
  return Backend()
 def snapshot(self,a):
  p=bytearray(169);p[0]=a;p[1]=60;p[122]=27;p[150]=8;p[151]=255;p[158]=8;p[159:169]=b'SYNTHETIC0'
  return dict(address=a,version_hex=(b'SYNTHETIC0'+b'\x10\x06'+b'V'*20).hex(),parameters_hex=p.hex(),battery_sn_hex=(b'BATT'+bytes([65+a])*26).hex(),bms_sn_hex=(b'BOARD'+bytes([65+a])*25).hex(),info_hex=self.meta['info_hex'],info=dict(image_flags=254),diagnostics=dict(parameters=dict(primary='valid',backup='valid',primary_lock=False,backup_lock=False),runtime_lock=False,runtime_magic_valid=True,runtime_consistent=True))
 def run_it(self,plan,b):return self.m.run_batch(plan,lambda log:b,self.root/'run')
 def test_twelve_count_has_two_exact_address_ranges(self):
  self.assertEqual(self.m.plan_addresses(12,'master'),list(range(12)));self.assertEqual(self.m.plan_addresses(12,'external'),list(range(1,13)))
 def test_invalid_and_out_of_DIP_range_counts_refused(self):
  for n,mode in [(0,'master'),(-1,'external'),(17,'master'),(16,'external'),(True,'master'),(12,'other')]:
   with self.subTest(n=n,mode=mode),self.assertRaises(ValueError):self.m.plan_addresses(n,mode)
 def test_all_backups_precede_first_reset_and_all_targets_verified(self):
  p=self.plan();b=self.backend(p);r=self.run_it(p,b);self.assertEqual(r['status'],'verified');self.assertEqual(r['verified_addresses'],[0,1,2]);self.assertEqual(b.flashed,[0,1,2]);self.assertTrue(b.closed)
  first=b.events.index(('flash',0));self.assertTrue(all(('snapshot',a) in b.events[:first] for a in p['addresses']))
 def test_external_counts_start_at_one_and_refuse_zero_pack(self):
  p=self.plan(mode='external');b=self.backend(p);b.zero=True
  with self.assertRaises(RuntimeError):self.run_it(p,b)
  self.assertEqual(b.flashed,[])
 def test_external_mode_does_not_start_or_clear_maintenance(self):
  p=self.plan(mode='external');b=self.backend(p);self.run_it(p,b);self.assertNotIn(('prepare-master',),b.events);self.assertEqual(b.flashed,[1,2,3])
 def test_master_pause_does_not_readdress_zero(self):
  p=self.plan();b=self.backend(p);self.run_it(p,b);self.assertEqual(b.flashed[0],0);self.assertIn(('prepare-master',),b.events)
 def test_master_polling_or_unknown_marker_blocks_entire_batch(self):
  for status in (dict(marker=0xffffffff,flag=0,effective_slaves=11),dict(marker=0x1234,flag=None,effective_slaves=0)):
   with self.subTest(status=status):
    p=self.plan();b=self.backend(p);b.status=status
    with self.assertRaises(RuntimeError):self.run_it(p,b)
    self.assertEqual(b.flashed,[])
    import shutil
    shutil.rmtree(self.root/'run')
 def test_missing_pack_before_first_reset_stops_everything(self):
  p=self.plan();b=self.backend(p);del b.states[2]
  with self.assertRaises(Exception):self.run_it(p,b)
  self.assertEqual(b.flashed,[])
 def test_duplicate_or_placeholder_BMS_serial_blocks_bank(self):
  for duplicate in (True,False):
   p=self.plan();b=self.backend(p);b.states[2]['bms_sn_hex']=b.states[1]['bms_sn_hex'] if duplicate else (b'\0'*30).hex()
   with self.assertRaises(ValueError):self.run_it(p,b)
   self.assertEqual(b.flashed,[])
   import shutil
   shutil.rmtree(self.root/'run')
 def test_automatic_addressing_refused_before_reset(self):
  p=self.plan();b=self.backend(p);raw=bytearray.fromhex(b.states[2]['parameters_hex']);raw[158]|=32;b.states[2]['parameters_hex']=raw.hex()
  with self.assertRaises(ValueError):self.run_it(p,b)
  self.assertEqual(b.flashed,[])
 def test_active_live_or_stored_lock_prevents_light_downgrade(self):
  for evidence in ('live','stored','cache','unknown'):
   p=self.plan(profile='light');b=self.backend(p)
   if evidence=='live':
    raw=bytearray.fromhex(b.states[1]['parameters_hex']);raw[151]&=~32;b.states[1]['parameters_hex']=raw.hex()
   elif evidence=='stored':b.states[1]['diagnostics']['parameters']['backup_lock']=True
   elif evidence=='cache':b.states[1]['diagnostics']['runtime_lock']=True
   else:b.states[1]['diagnostics']=None
   with self.assertRaises(ValueError):self.run_it(p,b)
   self.assertEqual(b.flashed,[])
   import shutil
   shutil.rmtree(self.root/'run')
 def test_helper_failure_stops_without_next_address_or_recovery(self):
  p=self.plan();b=self.backend(p);b.fail=1
  with self.assertRaisesRegex(RuntimeError,'uncertain'):self.run_it(p,b)
  self.assertEqual(b.flashed,[0,1]);r=json.loads((self.root/'run/report.json').read_text());self.assertEqual(r['verified_addresses'],[0]);self.assertEqual(r['failed_address'],1);self.assertEqual(r['status'],'failed');self.assertTrue(b.closed)
 def test_post_readback_mismatch_never_advances(self):
  for field in ('parameters_hex','bms_sn_hex','battery_sn_hex','info_hex','version_hex'):
   p=self.plan();b=self.backend(p);b.after_change=lambda s,field=field:s.__setitem__(field,'00')
   with self.subTest(field=field),self.assertRaises((ValueError,RuntimeError)):self.run_it(p,b)
   self.assertEqual(b.flashed,[0]);self.assertTrue((self.root/'run/pack-00-after.json').is_file())
   import shutil
   shutil.rmtree(self.root/'run')
 def test_busy_bus_or_existing_bootloader_never_resets(self):
  for attr in ('quiet_fail','boot'):
   p=self.plan();b=self.backend(p);setattr(b,attr,True)
   with self.assertRaises(RuntimeError):self.run_it(p,b)
   self.assertEqual(b.flashed,[])
   import shutil
   shutil.rmtree(self.root/'run')
 def test_existing_output_directory_never_opens_backend(self):
  out=self.root/'run';out.mkdir();(out/'keep').write_text('keep')
  with self.assertRaises(FileExistsError):self.m.run_batch(self.plan(),lambda log:self.fail('port opened'),out)
  self.assertEqual((out/'keep').read_text(),'keep')
 def test_source_file_changes_refused_before_reset(self):
  p=self.plan();b=self.backend(p);self.image.write_bytes(b'changed')
  with self.assertRaises(ValueError):self.run_it(p,b)
  self.assertEqual(b.flashed,[])
 def test_pinned_release_defaults_to_offline_plan(self):
  release=self.plan()['release']
  with patch.object(self.m,'load_release',return_value=release),patch.object(self.m,'SerialBackend',side_effect=AssertionError('device opened')),contextlib.redirect_stdout(io.StringIO()) as out:
   self.assertEqual(self.m.main(['12','--mode','master','--profile','full']),0)
  self.assertEqual(json.loads(out.getvalue())['addresses'],list(range(12)))
 def test_same_uart_adapter_or_callin_alias_rejected_before_open(self):
  for a,b in [('/dev/cu.usbX','/dev/cu.usbX'),('/dev/cu.usbX','/dev/tty.usbX')]:
   with self.subTest(a=a,b=b),patch.object(self.m,'SerialBackend',side_effect=AssertionError('device opened')),contextlib.redirect_stderr(io.StringIO()):
    self.assertNotEqual(self.m.main(['12','--mode','master','--profile','full','--execute','--port',a,'--maintenance-port',b]),0)

 def synthetic_release(self):
  import hashlib,struct
  header=b'SWM181RCT6_64_M0EMU1101_10D_HW16RS485'.ljust(256,b'\0')
  image=self.m.transport.flasher.Image(tuple(':10000000'+header[i:i+16].hex().upper()+'AA' for i in range(0,256,16)),struct.pack('<II',0x20002000,0xc1)+bytes(4096-8),(':04000005000000C136',':00000001FF'))
  app=bytearray(image.app);token=b'MNT\5\0\0\x0d\1\6\4UPID0000\xfe\0\x0f';app[512:533]=token;bid=hashlib.sha256(app).digest()[:8];app[522:530]=bid;image=image.with_app(app);raw=image.render().encode()
  meta={**self.meta,'app_bytes':len(app),'app_sha256':image.sha,'ehex_sha256':hashlib.sha256(raw).hexdigest(),'build_id':bid.hex(),'info_bytes':21,'info_hex':(token[:4]+b'\x10\6'+token[6:10]+bid+token[18:]).hex()}
  directory=self.root/'metadata';directory.mkdir();(directory/'maint-full.json').write_text(json.dumps(meta));self.image.write_bytes(raw);return directory,raw
 def test_load_release_pins_verified_bytes_without_reopening_for_frames(self):
  directory,raw=self.synthetic_release()
  with patch.object(self.m.transport.flasher,'prepare_image',side_effect=AssertionError('must use pinned bytes')):
   release=self.m.load_release('full',self.image,metadata_dir=directory)
  self.assertEqual(release['prepared'][0][256:256+4096],self.m.transport.flasher.Image.parse(raw.decode()).app)
 def test_wrong_image_digest_fails_before_preparation(self):
  directory,raw=self.synthetic_release();self.image.write_bytes(raw+b'changed')
  with patch.object(self.m.transport.flasher,'prepare_image',side_effect=AssertionError('unvalidated bytes prepared')),self.assertRaises(ValueError):self.m.load_release('full',self.image,metadata_dir=directory)
 def test_lost_previously_present_cell_or_pack_measurements_stops(self):
  for measure in ('cells','pack'):
   p=self.plan();b=self.backend(p)
   for a in p['addresses']:
    raw=bytearray(75);raw[:3]=bytes([0,a,16]);raw[35]=6;raw[54]=10
    for i in range(16):raw[3+2*i:5+2*i]=(3300).to_bytes(2,'big')
    raw[50:52]=(5280).to_bytes(2,'big');b.states[a]['telemetry_hex']=raw.hex()
   def zero(s):
    raw=bytearray.fromhex(s['telemetry_hex'])
    if measure=='cells':raw[3:35]=bytes(32)
    else:raw[50:52]=bytes(2)
    s['telemetry_hex']=raw.hex()
   b.after_change=zero
   with self.subTest(measure=measure),self.assertRaises(RuntimeError):self.run_it(p,b)
   self.assertEqual(b.flashed,[0])
   import shutil
   shutil.rmtree(self.root/'run')

 def test_twelve_complete_updates_in_each_mode(self):
  for mode in ('master','external'):
   p=self.plan(count=12,mode=mode);b=self.backend(p);result=self.run_it(p,b)
   self.assertEqual(b.flashed,p['addresses']);self.assertEqual(result['verified_addresses'],p['addresses'])
   import shutil
   shutil.rmtree(self.root/'run')

 def test_marker_start_then_confirmation_failure_is_recorded(self):
  p=self.plan();b=self.backend(p)
  def prepare():b.maintenance_start_attempted=True;b.maintenance_started=True;raise TimeoutError('pause confirmation missing')
  b.prepare_master=prepare
  with self.assertRaises(TimeoutError):self.run_it(p,b)
  report=json.loads((self.root/'run/report.json').read_text());self.assertTrue(report.get('maintenance_start_attempted'));self.assertTrue(report.get('maintenance_started'));self.assertFalse(report.get('maintenance_pause_confirmed',False));self.assertEqual(b.flashed,[])

if __name__=='__main__':unittest.main()
