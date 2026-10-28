from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image,ImageError
from seplos.analysis import discover
from seplos.guards import guard
from seplos.thumb import Code,encode_bl
OEM=next((ORIGINALS).glob('*16.06.13*ehex'))

class Negative(unittest.TestCase):
 def test_nonhex_header_and_payload_whitespace_rejected(self):
  lines=OEM.read_text().splitlines();lines[16]=lines[16][:11]+' '+lines[16][11:]
  with self.assertRaises(ImageError):Image.parse('\n'.join(lines))
  lines=OEM.read_text().splitlines();lines[15]=lines[15][:11]+'  '+lines[15][13:]
  with self.assertRaises(ImageError):Image.parse('\n'.join(lines))
 def test_swapped_call_to_other_known_function_rejected(self):
  im=Image.read(OEM);facts=discover(im);c=Code(im.app)
  call=next(i for i in c.body(facts['functions']['dip']) if i.op=='bl')
  data=bytearray(im.app);data[call.at:call.at+4]=encode_bl(call.at,facts['functions']['crc']);bad=im.with_app(data)
  with self.assertRaisesRegex(ValueError,'contract'):guard(bad,discover(bad))
 def test_changed_high_ram_literal_rejected(self):
  im=Image.read(OEM);facts=discover(im);c=Code(im.app);i=c.window(facts['functions']['validator'],2)[1]
  pool=((i.at+4)&~3)+(int.from_bytes(i.raw,'little')&255)*4
  data=bytearray(im.app);data[pool:pool+4]=(i.literal+0x80).to_bytes(4,'little');bad=im.with_app(data)
  with self.assertRaises(ValueError):guard(bad,discover(bad))
 def test_changed_referenced_rom_table_rejected(self):
  im=Image.read(OEM);facts=discover(im);c=Code(im.app)
  candidates=[i.literal for i in c.body(facts['functions']['dip']) if i.literal is not None and facts['functions']['main']<i.literal<len(im.app)]
  self.assertTrue(candidates)
  data=bytearray(im.app);data[candidates[0]]^=1;bad=im.with_app(data)
  with self.assertRaises(ValueError):guard(bad,discover(bad))
 def test_ambiguous_duplicate_signature_rejected(self):
  im=Image.read(OEM);facts=discover(im);c=Code(im.app);start=facts['functions']['crc'];body=c.body(start)
  data=bytearray(im.app)
  if len(data)%4!=start%4:data+=b'\x00\xbf'
  new=len(data);end=max(i.at+i.size for i in body);copy=bytearray(im.app[start:end])
  while (new+len(copy))%4:copy+=b'\x00\xbf'
  for i in body:
   if i.op=='ldr' and '[pc,' in i.args:
    h=int.from_bytes(i.raw,'little');pool=((i.at+4)&~3)+(h&255)*4
    offset=(new+len(copy)-((new+i.at-start+4)&~3))//4
    copy[i.at-start:i.at-start+2]=((h&0xff00)|offset).to_bytes(2,'little');copy+=im.app[pool:pool+4]
  data+=copy
  with self.assertRaisesRegex(ValueError,'found 2'):discover(im.with_app(data))

if __name__=='__main__':unittest.main()
