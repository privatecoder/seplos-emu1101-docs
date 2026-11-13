# Firmware analysis

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The [capability renderer](write_access.py) compares the exact OEM 16.06.13,
EMU1101-EXT Light 1.5.5 and Full 1.6.5 images, covering 87 parameters, 64 switch
positions and 23 action rows. Function availability starts at Light 1.5.3+ /
Full 1.6.3+, with shared remote reads from `.4+` and atomic cleanup from `.5+`.
Public release JSONs supply the current identities.

```sh
PROJECT='/path/to/Seplos V2 10E BMS'
SEPLOS_PY="$HOME/.local/share/seplos-oem-patcher/venv/bin/python"
ANALYSIS="$PROJECT/mod/tools/firmware-analysis"
cd /private/tmp
"$SEPLOS_PY" -I -B "$ANALYSIS/write_access.py" --verify
"$SEPLOS_PY" -I -B "$ANALYSIS/write_access.py" --markdown --out /private/tmp/new-matrix.md
```

`--verify` checks the OEM and two current release EHEX/application hashes,
EXT05 metadata/template and source-defined build-ID digest against
`mod/firmware/releases/*.json`. It needs no historical build reports and runs
no native emulation. The template reserves two zero bytes for the OEM family
version copied at runtime. This is static input verification, not a fresh
native regression result. `--out` refuses an existing
file. [UART capabilities](../../docs/firmware/uart-write-capabilities.md) and
[OpenBMS integration](../../docs/firmware/openbms-monitor.md) describe the current
contracts; [OEM analysis](../../../analysis/README.md) remains separate.

| Tool | Purpose / inputs |
|---|---|
| `ehex2bin.py OUTPUT_DIR INPUT.ehex...` | Permissive historical format inspection; requires an existing output directory and overwrites matching `.bin` filenames. Use a fresh directory, or the strict Image/LLVM preparation below for comparisons. |
| `show.py`, `xref.py`, `sw.py`, `findsw.py`, `ramref.py`, `eff.py`, `lits.py`, `cmpfn.py` | Inspect generated `vVERSION.raw` and `vVERSION.dis`; supply `--data-dir DIR` explicitly, followed by the existing positional arguments. `cmpfn.py` finds `show.py` beside its own source. |
| `funcs.py A.dis B.dis` | Compare function bodies from explicit disassembly inputs. |
| `crc.py` | CRC16/XMODEM demonstration and check value. |
| `batterymonitor_agreement.py` | Inventory the immutable vendor BatteryMonitor ZIP directly; XML/executable bytes are data and are never executed. Optional `--agreement` accepts another ZIP or an extracted Agreement directory. Temporary extraction uses `/private/tmp`. |
| `probe_pack_cutoff.py` | Original power/wakeup/current-limit counterexamples with synthetic OEM state. |
| `verify_intra_pack_fixtures.py` | Standard-library checks of private 0x5A captures: strict framing/checksum, decoded expectations and retained source SHA. Never accesses a port. |
| `probe_legacy_uart0_fc03.py` | Four saved-fact-bound native checks for OEM 16.04.06 versus 16.06.03. |

Rendered Markdown uses canonical UART names. The catalogue verifies the two current EXT05 releases directly.

The OEM-native probes use the patcher `seplos` package and Unicorn/LLVM.
The checked [research input registry](../research-inputs.json) binds exact
report/fact paths and hashes. The OEM FC03 probe requires its retained facts;
the intra-pack verifier requires private capture fixtures. Missing or changed
inputs fail instead of silently selecting another image. The capability
renderer separately reads current release metadata and images.

Native JIT execution may be restricted by the calling environment. Run native
checks in a normal local process when the sandbox disallows Unicorn JIT.
The model does not prove electrical timing, brownout behavior or physical gates.

## Strict comparison input preparation

The current patcher `Image` validates the OEM pseudo-header, checksums, record
continuity, extent and vectors before decoding. `Code` uses the current LLVM
Cortex-M0 disassembler. This offline command creates a fresh output directory;
the OEM EHEX input is read only. Set `SEPLOS_LLVM_BIN` if LLVM is not discovered.

```sh
"$SEPLOS_PY" -I -B - "$PROJECT" \
  "$PROJECT/vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex" \
  /private/tmp/seplos-oem13-dis 13 <<'PY'
from pathlib import Path
import hashlib, json, re, sys
project, source, output = map(Path, sys.argv[1:4])
version = sys.argv[4]
sys.path.insert(0, str(project / 'mod/firmware/patcher'))
from seplos.image import Image
from seplos.thumb import Code, command, llvm
image = Image.read(source)
code = Code(image.app)
# Remove the ephemeral LLVM ELF filename from the text header.
disassembly = re.sub(r'(?m)^.*app[.]elf:', 'app.elf:', code.disassembly)
output.mkdir()  # Refuse an existing output directory.
with (output / f'v{version}.raw').open('xb') as stream:
    stream.write(image.app)
with (output / f'v{version}.dis').open('x') as stream:
    stream.write(disassembly)
with (output / 'inputs.json').open('x') as stream:
    json.dump({'source': str(source),
               'ehex_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'app_sha256': image.sha,
               'llvm_objdump': command([llvm('llvm-objdump'), '--version'])},
              stream, indent=2)
PY
"$SEPLOS_PY" -I -B "$ANALYSIS/show.py" --data-dir /private/tmp/seplos-oem13-dis 13 09b4 10
"$SEPLOS_PY" -I -B "$ANALYSIS/cmpfn.py" --data-dir /private/tmp/seplos-oem13-dis 13 09b4 13 09b4
```

Generate each selected version under a fresh directory, then place the chosen
`vVERSION.raw`/`vVERSION.dis` pairs together in an explicit comparison directory.
`show.py` rejects missing inputs, empty raw data and start addresses without a
decoded body. `cmpfn.py` requires both `show.py` processes to succeed with
nonempty bodies before reporting equality. Linear disassembly can interpret
literal pools as instructions; comparisons do not establish function semantics.

```sh
"$SEPLOS_PY" -I -B -m unittest discover -s "$ANALYSIS/tests" -v
```
