"""Execute emitted Thumb, including original action branches and RTC drivers."""
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,ascii_frame,frame
from seplos.build import build
from seplos.selftest import ascii_payload


class PowerRTC(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  cls.facts=probe(cls.original,discover(cls.original))
  cls.image,cls.report=build(cls.original,cls.facts,base_revision=13,maint_version='1.5.3')
 def board(self,address=1,enabled=False):
  m=Machine(self.image,self.facts);m.defaults(address)
  m.put(m.r['group0'],bytes([(m.num(m.r['group0'])&~8)|(8 if enabled else 0)]))
  return m
 def test_power_and_clock_set_locked_by_legacy_default(self):
  for cmd,data in ((0x45,bytes.fromhex('000410')),(0x45,bytes.fromhex('00041f')),
                   (0x45,bytes.fromhex('000600')),(0x4e,bytes.fromhex('07ea0a12142030'))):
   m=self.board()
   self.assertEqual(ascii_payload(m.transact(ascii_frame(1,cmd,data),True),1),(5,b''))
   self.assertEqual(m.saves,[])
 def test_new_permission_immutable_and_atomic_over_uart1(self):
  for enabled in (False,True):
   m=self.board(enabled=enabled);before=m.payload();p=bytearray(before)
   p[150]^=8;p[130]=110
   self.assertEqual(m.transact(frame(1,0xa1,p),True),frame(1,0xe3))
   self.assertEqual(m.payload(),before);self.assertEqual(m.saves,[])
 def test_capability_in_unchanged_mnt04_layout(self):
  m=self.board();rtn,data=ascii_payload(m.transact(ascii_frame(1,0x64,b'\x03'),True),1)
  self.assertEqual((rtn,len(data),data[:4],data[7:9]),(0,19,b'MNT\x04',b'\x01\x05'))
  self.assertEqual(data[18],58)
 def test_nonhex_raw_address_must_not_alias_own_address(self):
  for address,offset,character in ((1,3,'G'),(0,4,'Z')):
   m=self.board(address,enabled=True)
   raw=bytearray(ascii_frame(address,0x45,bytes.fromhex('00041F')))
   raw[offset]=ord(character)  # Keep checksum for the normalized numeric address.
   before=m.read(self.facts['power_rtc']['system_status'])
   self.assertEqual(m.transact(raw,True),b'')
   self.assertEqual(m.read(self.facts['power_rtc']['system_status']),before)
 def test_executable_contract(self):
  from seplos.power_rtc_tests import validate_power_rtc
  checks=validate_power_rtc(self.original,self.image,self.facts)
  self.assertGreaterEqual(len(checks),30)
  self.assertTrue(all(c['passed'] for c in checks))


if __name__=='__main__':unittest.main()
