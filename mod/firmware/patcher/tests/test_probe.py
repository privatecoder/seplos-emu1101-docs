from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover

class Probe(unittest.TestCase):
 def test_probe_implemented(self):
  self.assertTrue((ROOT/'seplos'/'machine.py').exists(), 'OEM execution probe missing')
 def test_each_oem_actual_layout_and_serialization(self):
  from seplos.machine import probe
  for path in sorted((ORIGINALS).glob('*.ehex')):
   with self.subTest(image=path.name):
    im=Image.read(path); facts=discover(im)
    if '16.04.06' in path.name:
     with self.assertRaisesRegex(ValueError,'UART1 buffers too small'):probe(im,facts)
     continue
    facts=probe(im,facts)
    ram=facts['ram']
    self.assertGreaterEqual(ram['rx_limit'],165)
    self.assertGreaterEqual(ram['tx_length']-ram['tx'],175)
    self.assertEqual(ram['group0'],0x20000028)
    self.assertEqual(ram['address'],0x20000027)
    self.assertEqual(ram['name'],0x20000042)
    self.assertEqual(ram['string1'],0x2000004C)
    self.assertEqual(ram['string2'],0x2000006A)
    self.assertTrue(facts['oracle']['defaults_roundtrip'])
    self.assertIn('modbus_gate',ram)
    self.assertTrue(facts['oracle']['modbus_response'])
    self.assertEqual(facts['oracle']['lcd_payload_length'],168)
    self.assertEqual(facts['oracle']['crc_123456789'],0x31c3)

if __name__=='__main__':unittest.main()
