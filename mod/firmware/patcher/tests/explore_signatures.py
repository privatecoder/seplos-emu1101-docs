"""Maintainer helper, never needed by the distributed patcher.

Generate address-neutral signatures from the documented 16.06.13 OEM image.
Reference addresses are only bootstrap annotations, never a runtime address map.
"""
from pathlib import Path
import sys, json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.thumb import Code
REF = {'uart1_send':0x25B2,'dip':0x2112,'serializer':0x4890,'loader':0x496A,'validator':0x4C3C,'iap_read':0x47A8,'iap_write':0x4748,'capacity_save':0x5564,'crc':0x75E6,'lcd_write':0x7F82,'lcd_read':0x7EA2,'iap_erase':0xBC88,'iap_program':0xBCB6,'identity_serializer':0x53D8}
code=Code(Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex').app)
sigs={k:[i.token() for i in code.window(a,12)] for k,a in REF.items()}
(ROOT/'seplos'/'signatures.json').write_text(json.dumps(sigs,indent=2)+'\n')
for path in sorted((ORIGINALS).glob('*.ehex')):
 c=Code(Image.read(path).app)
 print(path.name)
 for k,s in sigs.items():
  hits=[hex(a) for a in c.ins if [i.token() for i in c.window(a,len(s))]==s]
  print(k,hits)
