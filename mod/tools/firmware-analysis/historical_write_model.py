"""Fixed OEM16.06.13/MAINT1.5/MAINT1.6 data for historical native probes.

This extracted model preserves exact image hashes, entry points and A1 fields.
Current release identities and positive switch polarity live in write_access.py.
Provenance and original source hashes: write_access_provenance.json.
"""
from pathlib import Path
import json

_data = json.loads(Path(__file__).with_suffix('.json').read_text())
IMAGES = _data['IMAGES']
ENTRY_POINTS = _data['ENTRY_POINTS']
PARAMETERS = _data['PARAMETERS']
FUNCTION_BITS = _data['FUNCTION_BITS']
