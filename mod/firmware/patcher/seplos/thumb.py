"""LLVM Thumb decoding plus address-neutral structural signatures."""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import struct
import subprocess
import tempfile


def llvm(name):
    root = os.environ.get('SEPLOS_LLVM_BIN')
    candidates = ([str(Path(root) / name)] if root else []) + [shutil.which(name), '/opt/homebrew/opt/llvm/bin/' + name]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError('LLVM tool missing: ' + name + '; set SEPLOS_LLVM_BIN')


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30)


@dataclass
class Ins:
    at: int
    size: int
    op: str
    args: str
    raw: bytes
    literal: int | None = None
    target: int | None = None

    def token(self):
        if self.op == 'ldr' and '[pc,' in self.args:
            value = self.literal
            cls = 'ram' if value is not None and 0x20000000 <= value < 0x20004000 else 'flash' if value is not None and value < 0x40000 else value
            return ['ldr-pc', self.args.split(',')[0], cls]
        if self.target is not None:
            return [self.op]
        if self.op == 'adr':
            return ['adr', self.args.split(',')[0]]
        return [self.op, self.args]


class Code:
    def __init__(self, app):
        self.app = app
        with tempfile.TemporaryDirectory(prefix='seplos-dis-') as tmp:
            raw, elf = Path(tmp) / 'app.raw', Path(tmp) / 'app.elf'
            raw.write_bytes(app)
            command([llvm('llvm-objcopy'), '-I', 'binary', '-O', 'elf32-littlearm', '--rename-section', '.data=.text,alloc,load,code,readonly', str(raw), str(elf)])
            self.elf = elf.read_bytes()
            self.disassembly = command([llvm('llvm-objdump'), '-d', '--triple=thumbv6m-none-eabi', '--mcpu=cortex-m0', str(elf)])
        self.ins = {}
        self.switches = set()
        self._parse(self.disassembly)
        # Reviewed Keil __ARM_common_switch8, including the indirect BX tail.
        switch = bytes.fromhex('30b47446641e2578641cab4200d21d46635d5b00e31830bc1847')
        for at in self.ins:
            if app[at:at+len(switch)] == switch:
                self.switches.add(at)

    def _parse(self, text):
        for line in text.splitlines():
            m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{4}(?: [0-9a-f]{4})?)\s+\t(\S+)\s*(.*)', line)
            if not m:
                continue
            at, op, args = int(m[1], 16), m[3], m[4].split('@')[0].split('<')[0].strip()
            size = 2 * len(m[2].split())
            i = Ins(at, size, op, args, self.app[at:at+size])
            if op == 'ldr' and '[pc,' in args:
                offset = int(re.search(r'#(0x[0-9a-f]+|\d+)', args)[1], 0)
                address = ((at + 4) & ~3) + offset
                if address + 4 <= len(self.app):
                    i.literal = struct.unpack_from('<I', self.app, address)[0]
            if op.startswith('b') and op not in ('bx', 'blx', 'bics') and re.match(r'0x[0-9a-f]+$', args):
                i.target = int(args, 16)
            self.ins[at] = i


    def ensure(self, at):
        if at in self.ins and self.ins[at].op != '<unknown>':
            return
        # Linear raw-image disassembly can swallow an instruction after a literal
        # pool into an unknown 32-bit word. Restart LLVM at the proven CFG target.
        with tempfile.TemporaryDirectory(prefix='seplos-decode-') as tmp:
            elf = Path(tmp) / 'app.elf'
            elf.write_bytes(self.elf)
            decoded = command([llvm('llvm-objdump'), '-d', '--triple=thumbv6m-none-eabi', '--mcpu=cortex-m0', f'--start-address={at}', f'--stop-address={min(at+128,len(self.app))}', str(elf)])
            self._parse(decoded)
        if at not in self.ins or self.ins[at].op == '<unknown>':
            raise ValueError(f'unknown executable Thumb instruction at {at:x}')

    def switch_targets(self, i):
        lr = i.at + i.size
        count = self.app[lr]
        if not 1 <= count <= 128 or lr + count + 2 > len(self.app):
            raise ValueError('invalid Keil switch table')
        targets = [lr + self.app[lr+1+j] * 2 for j in range(count+1)]
        if any(t & 1 or not 0xc0 <= t < len(self.app) for t in targets):
            raise ValueError('invalid Keil switch target')
        return targets

    def window(self, at, n):
        out = []
        for _ in range(n):
            if at not in self.ins:
                return []
            i = self.ins[at]
            out.append(i)
            at += i.size
        return out

    def callers(self, target):
        return [a for a, i in self.ins.items() if i.op == 'bl' and i.target == target]

    def body(self, at, limit=4096):
        # Worklist follows real direct control flow, never walks a literal pool.
        todo, seen = [at], set()
        while todo:
            a = todo.pop()
            if a in seen:
                continue
            if len(seen) > limit or not 0xC0 <= a < len(self.app):
                raise ValueError(f'unsupported control flow at {a:x} from {at:x}')
            self.ensure(a)
            seen.add(a)
            i = self.ins[a]
            if i.op == 'bl' and i.target in self.switches:
                todo.extend(self.switch_targets(i))
                continue
            if i.op == 'bl' and i.target == 0xc8:
                # The reviewed Keil initializer ends with BL to the main veneer.
                # Only that exact non-returning transition skips its literal pool.
                init = self.ins[0xc4].target
                first = self.ins[init]
                pool = ((init+4)&~3) + (int.from_bytes(first.raw,'little')&255)*4
                if i.at+4 == pool:
                    todo.append(i.target)
                    continue
            if i.op == 'bx' or i.op == 'pop' and 'pc' in i.args:
                continue
            if i.op == 'b':
                todo.append(i.target)
                continue
            if i.target is not None and i.op != 'bl':
                todo.append(i.target)
            if i.op == 'ldr' and i.args.startswith('pc'):
                raise ValueError('indirect control flow unsupported')
            todo.append(a + i.size)
        return [self.ins[a] for a in sorted(seen)]


def encode_bl(site, target):
    delta = target - site - 4
    if (site | target) & 1 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError('invalid Thumb BL distance/alignment')
    imm = delta & ((1 << 25) - 1)
    s, i1, i2 = imm >> 24 & 1, imm >> 23 & 1, imm >> 22 & 1
    return struct.pack('<HH', 0xf000 | s << 10 | (imm >> 12 & 1023), 0xd000 | (~(i1 ^ s) & 1) << 13 | (~(i2 ^ s) & 1) << 11 | (imm >> 1 & 2047))
