# Analysis Tools

These scripts were used to examine the firmware images in `../firmware/ehex/*.ehex`. All scripts are plain Python 3 scripts without external dependencies. Only LLVM is required for disassembly (`brew install llvm` → `/opt/homebrew/opt/llvm/bin/`).

> Security note: firmware files are untrusted data. Always run the scripts with `python3 -I` and not from inside the directory that contains the firmware.

## 1. `.ehex` → binary image

```sh
mkdir -p /tmp/seplos/bin
python3 -I ehex2bin.py /tmp/seplos/bin ../firmware/ehex/*.ehex
# Output: header string, address range, stack pointer, reset vector, entry, constants
cd /tmp/seplos/bin
for f in *.bin; do v=$(echo "$f" | sed -E 's/.*V16\.([0-9]+\.[0-9]+).*/\1/'); cp "$f" v$v.raw; done
```

`ehex2bin.py` skips the 16 leading header records with checksum `AA` (256-byte header) and then parses normal Intel HEX (types 00/04/05). Gaps are filled with `0xFF`.

## 2. Disassembly (Thumb, Cortex-M0)

```sh
L=/opt/homebrew/opt/llvm/bin
for v in 04.06 06.03 06.04 06.05 06.11 06.12 06.13; do
  $L/llvm-objcopy -I binary -O elf32-littlearm \
     --rename-section .data=.text,alloc,load,code,readonly v$v.raw v$v.elf
  $L/llvm-objdump -d --triple=thumbv6m-none-eabi --mcpu=cortex-m0 v$v.elf > v$v.dis
done
```

Literal pools and jump tables are disassembled as code as well. This is normal for raw images.

## 3. Helper scripts

The scripts read `vXX.YY.raw` and `vXX.YY.dis` from the current directory. The simplest approach is to copy them to `/tmp/seplos/bin` and run them there. `cmpfn.py` calls `show.py` in the same directory.

```sh
cp *.py /tmp/seplos/bin/ && cd /tmp/seplos/bin
```

| Script | Purpose | Example |
|---|---|---|
| `show.py <ver> <hexaddr> [n]` | Print the function from the address up to the next `push {…lr}`; literal loads resolved as `=0xVALUE` | `python3 -I show.py 06.13 10d6` |
| `xref.py <ver> 0xVALUE…` | Which functions load this constant/address from a literal pool | `python3 -I xref.py 06.13 0x20000024` |
| `sw.py <ver> <bl-addr>:<base>` | Decode a Keil `__ARM_common_switch8` jump table (value − base → target) | `python3 -I sw.py 06.13 1160:42 117e:a0` |
| `findsw.py <ver> 0x42 0xa0` | Finds the `bl` addresses of the switch helpers after `subs rX,#base` (input for `sw.py`) | – |
| `funcs.py a.dis b.dis` | Function-by-function comparison of two versions (normalized, similarity, NEW/REMOVED/CHANGED) | `python3 -I funcs.py v06.12.dis v06.13.dis` |
| `lits.py v1 v2 …` | New/removed non-RAM constants in literal pools between versions | `python3 -I lits.py 06.12 06.13` |
| `cmpfn.py v1 addr1 v2 addr2 [shift] [x]` | Compare two functions normalized (branch targets relative, RAM addresses ≥ `0x200000C0` optionally shifted by `shift`). With a 6th argument the diff is printed | `python3 -I cmpfn.py 06.12 352c 06.13 364a 8 x` |
| `ramref.py <ver> 0xADDR…` | Find RAM accesses also via base+offset (not only direct literals) | `python3 -I ramref.py 06.13 0x200000f7` |
| `eff.py <ver> lo hi` | All read/write accesses to a RAM range `[lo,hi)` with function | `python3 -I eff.py 06.13 2000164c 20001680` |
| `crc.py` | CRC-16/XMODEM of the binary protocol (self-test "123456789" → 0x31C3) | `python3 -I crc.py` |

Byte-exact comparison of two images (e.g. 06.04 vs. 06.05 "SP80"):

```sh
cmp -l v06.04.raw v06.05.raw     # offsets decimal+1, values octal!
```

## 4. Hard stop (SP80 behaviour) for other versions

`hardstop.py` changes the event-6 mask in the function "charging forbidden" from `0x71` to `0x73` and recalculates the checksum of the affected Intel HEX line. It refuses to patch unless the expected instruction sequence is found at the offset.

```sh
python3 -I tools/hardstop.py "firmware/ehex/CAN1101[V16.06.13_PN01_250607].ehex" 706C out.ehex
# Offsets: 16.06.04 658A (reproduces SP80 byte for byte), 16.06.11 6EA0, 16.06.12 6EA0, 16.06.13 706C
```

What this changes and when it makes sense: [docs/intermittent-recharge-soft-vs-hard-stop.md](../docs/intermittent-recharge-soft-vs-hard-stop.md). Untested on hardware; flashing modified firmware is at your own risk.
