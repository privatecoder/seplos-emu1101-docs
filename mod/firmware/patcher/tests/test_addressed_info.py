"""Generic builder uses actual OEM parser/sender for per-pack MNT04 info."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,ascii_frame
from seplos.build import build
from seplos.selftest import ascii_payload

class AddressedInfo(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  im=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  cls.facts=probe(im,discover(im));cls.image,cls.report=build(im,cls.facts,base_revision=13,maint_version='1.5.3')
 def board(self,address):
  m=Machine(self.image,self.facts);m.defaults(address);return m
 def test_slave_info_is_addressed_and_maintenance_stays_master_only(self):
  expected=b'MNT\x04\x10\x06\x0d\x01\x05\x03'+bytes.fromhex(self.report['build_id'])+b'\x3a'
  for address in (0,1,11,15,21):
   m=self.board(address);m.put(m.r['group0'],b'\x00');m.put(0x23000,b'\x78\x56\x34\x12')
   self.assertEqual(ascii_payload(m.transact(ascii_frame(address,0x64,b'\x03'),True),address),(0,expected))
   self.assertEqual(m.flash_ops,[]);self.assertEqual(m.saves,[])
   if address:
    for data in (b'\x01\xc3\x5a',):
     self.assertEqual(m.transact(ascii_frame(address,0x64,data),True),b'')
   self.assertEqual(m.transact(ascii_frame(255,0x64,b'\x03'),True),b'')
   self.assertEqual(m.flash_ops,[]);self.assertEqual(m.read(0x23000,4),b'\x78\x56\x34\x12')
