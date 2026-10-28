from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.thumb import Code,encode_bl

class Guards(unittest.TestCase):
 def test_guard_implemented(self):self.assertTrue((ROOT/'seplos'/'guards.py').exists(),'semantic compatibility guards missing')
 def test_all_originals_and_patch_rejection(self):
  from seplos.guards import guard
  for path in sorted((ORIGINALS).glob('*.ehex')):
   im=Image.read(path);facts=discover(im);guard(im,facts)
   self.assertTrue(facts['guard_evidence'])
  for path in legacy_files():
   if any(x in str(path.parent) for x in ('Maintenance-Patch','UART1-Parameter-Patch','UART1-Identity-Patch','Maintenance-Split-Patch','Access-Control-Patch')):
    with self.subTest(patched=path.name),self.assertRaises(ValueError):
     im=Image.read(path);facts=discover(im);guard(im,facts)
 def test_new_hash_and_true_relocation(self):
  from seplos.guards import guard
  im=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')));facts=discover(im);code=Code(im.app)
  # Relocate entire CRC function plus its literal table; rewrite every direct BL.
  start=facts['functions']['crc'];end=start
  body=code.body(start)
  end=max(i.at+i.size for i in body)
  data=bytearray(im.app)
  if len(data)%4!=start%4:data.extend(b'\x00\xbf')
  new=len(data);copy=bytearray(im.app[start:end])
  while (new+len(copy))%4:copy.extend(b'\x00\xbf')
  for i in body:
   if i.op=='ldr' and '[pc,' in i.args:
    half=int.from_bytes(i.raw,'little');old_pool=((i.at+4)&~3)+(half&255)*4
    pool=new+len(copy);copy.extend(im.app[old_pool:old_pool+4])
    offset=(pool-((new+i.at-start+4)&~3))//4
    self.assertTrue(0<=offset<=255)
    copy[i.at-start:i.at-start+2]=((half&0xff00)|offset).to_bytes(2,'little')
  data.extend(copy);data[start:end]=b'\x00\xbf'*((end-start)//2)
  for site in code.callers(start):data[site:site+4]=encode_bl(site,new)
  relocated=im.with_app(data);found=discover(relocated);guard(relocated,found)
  self.assertEqual(found['functions']['crc'],new)
  from seplos.machine import probe
  from seplos.build import build
  from seplos.selftest import validate
  probe(relocated,found);patched,built=build(relocated,found,maint_version='1.5.3')
  self.assertGreaterEqual(len(validate(relocated,patched,found,built)),60)
 def test_sensor_switch_collision_rejected(self):
  from seplos.guards import guard
  im=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  # Documented OEM sensor check at 68A4; find via nearby Group0 literal instead of mutation of a file.
  code=Code(im.app);matches=[]
  for a,i in code.ins.items():
   if i.op=='lsls' and i.args=='r2, r2, #0x1e' and 0x6800<a<0x6900:matches.append(a)
  self.assertEqual(len(matches),1)
  data=bytearray(im.app);a=matches[0];word=int.from_bytes(data[a:a+2],'little');data[a:a+2]=(word+64).to_bytes(2,'little')
  bad=im.with_app(data)
  with self.assertRaises(ValueError):guard(bad,discover(bad))

if __name__=='__main__':unittest.main()
