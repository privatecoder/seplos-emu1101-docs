"""Maintainer-only enrollment of reviewed OEM/Hard-Stop structural contracts.

Never invoked by runtime patching. Updating this file's output requires review.
"""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.thumb import Code
from seplos.guards import contracts
out={'function_contracts':[],'initialization':[],'provenance':[]}
paths=sorted((ORIGINALS).glob('*.ehex'))+sorted((LEGACY/'Hard-Stop').glob('*.ehex'))
for p in paths:
 im=Image.read(p);facts=discover(im);c=Code(im.app);items,init=contracts(c,facts)
 for item in items:
  if item['contract'] not in out['function_contracts']:out['function_contracts'].append(item['contract'])
 if init not in out['initialization']:out['initialization'].append(init)
 out['provenance'].append({'input':p.name,'app_sha256':im.sha,'file_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'checked_functions':len(items)})
 print(p.name,len(items))
(ROOT/'seplos'/'shapes.json').write_text(json.dumps(out,indent=2)+'\n')
