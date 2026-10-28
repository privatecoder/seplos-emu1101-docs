"""Native UART0 marker and information access for both current profiles."""
from pathlib import Path
import copy,sys,unittest,subprocess,hashlib,json,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,ascii_frame
from seplos.build import build
from seplos.cutoff import discover_cutoff
from seplos.selftest import ascii_payload
from seplos.thumb import Code


class MarkerUART0(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  cls.base=probe(cls.original,discover(cls.original));discover_cutoff(cls.original,cls.base)
  cls.profiles={}
  for version in ('1.5.3','1.6.3'):
   facts=copy.deepcopy(cls.base)
   image,report=build(cls.original,facts,13,maint_version=version)
   cls.profiles[version]=(image,facts,report)
  cls.tx=next(i.target for i in reversed(Code(cls.original.app).body(cls.base['cutoff']['uart0_dispatch'])) if i.op=='bl')
 def board(self,v,a=0):
  im,f,_=self.profiles[v];m=Machine(im,f);m.defaults(a);return m
 def query(self,m,info=b'\2',target=None,raw=None):
  d=m.facts.get('marker_uart0',m.facts['cutoff']);a=m.num(m.r['address'])
  packet=raw or ascii_frame(a if target is None else target,0x64,info)
  m.put(d['uart0_rx'],packet);m.put(d['uart0_rx']+0x1f6,len(packet).to_bytes(2,'little'));m.put(d['uart0_state'],b'\4')
  previous=m.callback
  def peripheral(board,pc):
   if pc==self.tx:board.ret();return True
   return bool(previous and previous(board,pc))
  m.callback=peripheral
  try:m.run(d['uart0_dispatch'])
  finally:m.callback=previous
  if not m.num(d['uart0_state']):return None
  return ascii_payload(m.read(d['uart0_state']+1,m.num(d['uart0_rx']-6,2)),a)
 def test_mnt04_versions_match_R_and_C(self):
  for v in self.profiles:
   for a in (0,1,11,21):
    with self.subTest(version=v,address=a):
     m=self.board(v,a);c=ascii_payload(m.transact(ascii_frame(a,0x64,b'\3'),True),a);data=c[1]
     self.assertEqual((c[0],len(data),data[:4],data[7:10]),(0,19,b'MNT\4',bytes(map(int,v.split('.')))))
     self.assertEqual(self.query(m,b'\3'),c);self.assertEqual(data[18],254 if v=='1.6.3' else 58)
 def test_status_all_addresses_without_permissions(self):
  for v in self.profiles:
   for a in (0,1,11,15,21):
    with self.subTest(version=v,address=a):
     m=self.board(v,a);m.put(m.r['group0'],b'\0');m.put(m.r['slaves'],b'\7')
     for marker in (0xffffffff,0,0x12345678):
      raw=marker.to_bytes(4,'little');m.put(0x23000,raw);self.assertEqual(self.query(m),(0,raw+b'\7'))
     self.assertEqual(m.flash_ops,[])
 def test_clear_is_local_verified_unconditional_and_idempotent(self):
  for v in self.profiles:
   for a in (0,1,11,21):
    with self.subTest(version=v,address=a):
     m=self.board(v,a);m.put(m.r['group0'],b'\0');m.put(0x23000,bytes(4));before=m.payload()
     self.assertEqual(self.query(m,b'\0\xc3\x5a'),(0,b'\xff'*4+bytes([m.num(m.r['slaves'])])))
     self.assertEqual(self.query(m,b'\0\xc3\x5a')[0],0);self.assertEqual(m.read(0x23000,4),b'\xff'*4)
     self.assertEqual(m.flash_ops,[('erase',0x23000)]);self.assertEqual(m.payload(),before)
 def test_unknown_marker_and_erase_failure_not_success(self):
  for v in self.profiles:
   for failed in (False,True):
    with self.subTest(version=v,failed=failed):
     m=self.board(v,11);raw=bytes(4) if failed else b'xV4\x12';m.put(0x23000,raw);m.iap_fail=failed
     self.assertEqual(self.query(m,b'\0\xc3\x5a'),(5,b''));self.assertEqual(m.read(0x23000,4),raw)
 def test_foreign_FF_and_nonhex_never_erase(self):
  for v in self.profiles:
   for a in (0,1,21,255):
    m=self.board(v,11);m.put(0x23000,bytes(4));self.assertIsNone(self.query(m,b'\0\xc3\x5a',a));self.assertEqual(m.flash_ops,[])
   for offset in (3,4,10,11,19,20):
    m=self.board(v,11);m.put(0x23000,bytes(4));raw=bytearray(ascii_frame(11,0x64,b'\0\xc3\x5a'));raw[offset]=ord('G')
    if offset<19:raw[-5:-1]=f'{(-sum(raw[1:-5]))&65535:04X}'.encode()
    result=self.query(m,raw=bytes(raw));self.assertFalse(result and result[0]==0);self.assertEqual(m.flash_ops,[])
 def test_R_start_unsupported(self):
  for v in self.profiles:
   m=self.board(v);self.assertEqual(self.query(m,b'\1\xc3\x5a'),(5,b''));self.assertEqual(m.flash_ops,[])
 def test_R_does_not_clobber_C_or_display(self):
  for v in self.profiles:
   m=self.board(v,11);regions=[(m.r['rx']-1,0x250),(m.r['lcd_meta']-0xc0,0x1ba)]
   for a,n in regions:m.put(a,bytes((i*17+3)&255 for i in range(n)))
   snapshots=[m.read(a,n) for a,n in regions];self.assertEqual(self.query(m,b'\3')[0],0)
   self.assertEqual([m.read(a,n) for a,n in regions],snapshots)
 def test_new_CLI_profiles_publish_only_after_mandatory_suites(self):
  from seplos.marker_uart0_tests import REQUIRED
  source=next((ORIGINALS).glob('*16.06.13*ehex'))
  for v in self.profiles:
   with tempfile.TemporaryDirectory() as temp:
    dest=Path(temp)/'build';cmd=[sys.executable,'-I',str(ROOT/'seplos_patch.py'),'patch',str(source),'--maint-version',v,'--base-revision','13','--out',str(dest)]
    result=subprocess.run(cmd,cwd='/private/tmp',capture_output=True,text=True,timeout=120)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    r=json.loads((dest/'report.json').read_text());self.assertEqual(r['build']['patch_version'],v)
    self.assertTrue(set(REQUIRED)<={x['name'] for x in r['tests']})
    self.assertEqual(hashlib.sha256((dest/'firmware.ehex').read_bytes()).hexdigest(),r['output_file_sha256'])
 def test_publisher_rejects_wrong_format_version_or_missing_marker_test(self):
  from seplos.cli import run_worker,SCHEMA
  from seplos.marker_uart0_tests import REQUIRED
  source=next((ORIGINALS).glob('*16.06.13*ehex'))
  base=dict(schema=SCHEMA,mode='patch',maint_version='1.5.3',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint153-real-thumb-v1',suite_complete=True,
   tests=[dict(name=x,passed=True) for x in [*REQUIRED,*[f'other-{i}' for i in range(60)]]],build=dict(patch_version='1.5.3',info_format=4,info_bytes=19,uart0_marker=True,image_flags=58))
  for kind,error in [('format','revision UART0 marker contract missing'),('version','worker version differs'),('test','mandatory UART0 marker suite incomplete')]:
   r=copy.deepcopy(base)
   if kind=='format':r['build']['info_format']=3
   elif kind=='version':r['build']['patch_version']='1.5'
   else:r['tests']=[x for x in r['tests'] if x['name']!=REQUIRED[0]]
   with tempfile.TemporaryDirectory() as temp:
    worker=Path(temp)/'worker.py';worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(r)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,maint_version='1.5.3')
    self.assertEqual(artifacts,{});self.assertIn(error,result['error'])
 def test_161_full_R_power_chain_FF_protection_and_marker_independence(self):
  for address in (0,1,11):
   with self.subTest(address=address):
    m=self.board('1.6.3',address);d=m.facts['cutoff'];m.put(0x23000,bytes(4))
    self.assertEqual(self.query(m,raw=ascii_frame(address,0x45,b'\0\4\x1f')),(0,b''))
    self.assertEqual(m.num(d['ram']),1);writes=len(m.nv_ops)
    self.query(m,raw=ascii_frame(255,0x45,b'\0\4\x10'))
    self.assertEqual(m.num(d['ram']),1);self.assertEqual(len(m.nv_ops),writes)
    self.assertEqual(self.query(m,b'\0\xc3\x5a')[0],0)
    self.assertEqual(m.num(d['ram']),1);self.assertEqual(len(m.nv_ops),writes)
    raw=bytearray(ascii_frame(address,0x45,b'\0\4\x10'));raw[3]=ord('G');raw[-5:-1]=f'{(-sum(raw[1:-5]))&65535:04X}'.encode()
    self.assertIsNone(self.query(m,raw=bytes(raw)));self.assertEqual(m.num(d['ram']),1)
    self.assertEqual(self.query(m,raw=ascii_frame(address,0x45,b'\0\4\x10')),(0,b''))
    self.assertEqual(m.num(d['ram']),0)
 def test_161_full_R_power_chain_NVM_failure_still_RTN08(self):
  m=self.board('1.6.3',11);m.nv_fail_at={2}
  self.assertEqual(self.query(m,raw=ascii_frame(11,0x45,b'\0\4\x1f')),(8,b''))
  self.assertEqual(m.num(m.facts['cutoff']['ram']),1)

if __name__=='__main__':unittest.main()
