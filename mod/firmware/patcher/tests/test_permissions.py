"""Intrinsic positive permissions and persistent off-state safety."""
from pathlib import Path
import copy,hashlib,inspect,json,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,ascii_frame,frame
from seplos.build import build
from seplos.selftest import ascii_payload
from unicorn.arm_const import UC_ARM_REG_PC


class Permissions(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  cls.base=probe(cls.original,discover(cls.original))
  cls.facts=copy.deepcopy(cls.base)
  cls.image,cls.report=build(cls.original,cls.facts,13,maint_version='1.6.3')
 def board(self,bit3=True,bit4=True,address=1):
  m=Machine(self.image,self.facts);m.defaults(address)
  group=(m.num(m.r['group0'])&~0x18)|(8 if bit3 else 0)|(16 if bit4 else 0)
  m.put(m.r['group0'],bytes([group]));return m
 def query(self,m,cmd,data=b''):
  adr=m.num(m.r['address']);return ascii_payload(m.transact(ascii_frame(adr,cmd,data),True),adr)
 def u0(self,m,value):
  d=self.facts['cutoff'];m.put(d['uart0_rx'],ascii_frame(m.num(m.r['address']),0x45,bytes([0,4,value])))
  m.put(d['uart0_state'],b'\3');m.put(d['uart0_rtn'],b'\0')
  m.run(d['entries']['hook_cut_uart0_power']);return m.num(d['uart0_rtn'])
 def reboot(self,m):
  n=Machine(self.image,self.facts);n.put(0x25000,m.read(0x25000,8192));n.defaults(m.num(m.r['address']));return n
 def test_version_and_positive_capability(self):
  m=self.board();rtn,data=self.query(m,0x64,b'\3')
  self.assertEqual((rtn,len(data),data[:4],data[7:9],data[18]),(0,19,b'MNT\4',b'\1\6',254))
  self.assertTrue(self.report['positive_flags'])
 def test_bit3_one_allows_zero_denies_power_RTC_and_reset(self):
  for enabled in (False,True):
   for cmd,data in ((0x45,b'\0\4\x10'),(0x45,b'\0\4\x1f'),(0x45,b'\0\6\0'),(0x4e,bytes.fromhex('07EA0A15010203'))):
    with self.subTest(enabled=enabled,command=cmd,info=data.hex()):
     m=self.board(enabled,False);reset=self.facts['power_rtc']['reset']
     if enabled and data==b'\0\6\0':
      m.pause=reset;m.feed(ascii_frame(1,cmd,data));site=self.facts['hooks']['hook_dispatch'];m.execute(site,site+4)
      self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),reset);self.assertFalse(m.output)
     else:self.assertEqual(self.query(m,cmd,data),(0 if enabled else 5,b''))
 def test_bit4_one_persists_zero_preserves_soft_off_independent_of_bit3(self):
  for b3 in (False,True):
   for b4 in (False,True):
    with self.subTest(bit3=b3,bit4=b4):
     m=self.board(b3,b4);self.assertEqual(self.u0(m,0x1f),0)
     self.assertEqual(m.num(self.facts['cutoff']['ram']),int(b4))
     self.assertEqual(bool(m.nv_ops),b4)
     if b4:
      self.assertEqual(m.num(self.facts['cutoff']['onoff'])&0x17,0)
      self.assertEqual(self.reboot(m).num(self.facts['cutoff']['ram']),1)
 def test_disabling_bit4_and_import_cannot_release_existing_latch(self):
  m=self.board();self.assertEqual(self.u0(m,0x1f),0);self.assertEqual(m.num(self.facts['cutoff']['ram']),1)
  p=bytearray(m.payload());p[150]&=~16
  self.assertEqual(m.transact(frame(1,0xa1,p),True),frame(1,0xa1))
  n=self.reboot(m);self.assertEqual(n.num(self.facts['cutoff']['ram']),1)
  self.assertFalse(n.num(n.r['group0'])&16)
  self.assertEqual(self.u0(n,0x10),0);self.assertEqual(n.num(self.facts['cutoff']['ram']),0)
 def test_no_parameter_migration_or_bit5_semantics_change(self):
  for group in (0xe7,0xef,0xf7,0xff):
   m=self.board();m.put(m.r['group0'],bytes([group]));m.run(self.facts['cutoff']['entries']['hook_cut_serializer_0'])
   self.assertEqual(self.reboot(m).num(m.r['group0']),group)
  for bit in (2,3,5):
   m=self.board();before=m.payload();p=bytearray(before);p[150]^=1<<bit
   self.assertEqual(m.transact(frame(1,0xa1,p),True),frame(1,0xe3));self.assertEqual(m.payload(),before)


if __name__=='__main__':unittest.main()
