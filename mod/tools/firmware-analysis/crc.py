
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

def seplos_bin_crc(data):
    crc=0
    for b in data:
        m=0x80
        while m:
            hi=crc&0x8000
            crc=(crc<<1)&0xffff
            if hi: crc^=0x1021
            if b&m: crc^=0x1021
            m>>=1
    return crc
def xmodem(data):
    crc=0
    for b in data:
        crc^=b<<8
        for _ in range(8):
            crc=((crc<<1)^0x1021)&0xffff if crc&0x8000 else (crc<<1)&0xffff
    return crc
t=b'123456789'
print(hex(seplos_bin_crc(t)), hex(xmodem(t)), hex(xmodem(t+b'\0\0')))
print(hex(seplos_bin_crc(bytes([0x01,0xAA,0x00]))))
