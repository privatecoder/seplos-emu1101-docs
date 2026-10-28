# Building and validating MAINT firmware

The patcher analyzes an OEM EHEX, resolves code/RAM contracts, assembles a complete version-specific appendix and runs mandatory Cortex-M0 execution tests. It runs offline without an LLM, network connection, historical patch chain or device access. It does not flash hardware.

## Environment

Require Python3.11+, `unicorn==2.1.4`, and LLVM programs `llvm-mc`, `llvm-objcopy`, `llvm-objdump`, `llvm-nm`. Tested environments include Python3.11 and3.14.7 with Homebrew LLVM22.1.5. Unicorn is the patcher's only additional Python package. Retain the separate device-tools environment at `~/.local/share/seplos-firmware-tools/venv`, which requires `pyserial==3.5` and `unicorn==2.1.4`. Do not use `python -O`, which disables assertions and is refused.

Set the project root to the checkout, quote paths, and use a neutral working directory. The project path contains a colon, so the virtual environment must be outside it. Retain the established patcher location `~/.local/share/seplos-oem-patcher/venv` and the separate device-tools environment. Set the interpreter variables explicitly; reuse them if they already contain the pinned dependencies:

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
export SEPLOS_PATCHER="$SEPLOS_PROJECT/mod/firmware/patcher"
export SEPLOS_VENV="$HOME/.local/share/seplos-oem-patcher/venv"
export SEPLOS_PYTHON="$SEPLOS_VENV/bin/python"
export SEPLOS_TOOLS_PY="$HOME/.local/share/seplos-firmware-tools/venv/bin/python"
# Optional when the four LLVM executables are not on PATH:
export SEPLOS_LLVM_BIN='/opt/homebrew/opt/llvm/bin'
cd /private/tmp
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" --help
```

For a fresh patcher environment, `sh "$SEPLOS_PATCHER/setup_venv.sh"` installs the pinned requirements into `SEPLOS_VENV`. Reuse an existing environment after checking its installed requirements. LLVM must already be installed. Use its actual location if different. Entry points explicitly load their own package relative to `__file__`, supporting isolated `-I` calls. Unicorn JIT may need execution outside a restrictive sandbox on macOS; ordinary local terminal execution does not have that sandbox restriction.

## Current profiles

Output directories must be new and their parent must exist. Inputs are never overwritten. Generated artifacts belong in project-relative `local/builds`; use separate fresh directories for each invocation.

```sh
SEPLOS_INPUT="$SEPLOS_PROJECT/vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" analyze "$SEPLOS_INPUT" \
  --maint-version 1.5.3 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint153-analysis-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --maint-version 1.5.3 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint153-build-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --maint-version 1.6.3 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint163-build-new"
```

The only profiles are1.5.3 and1.6.3; `--maint-version` is required. Positive permission polarity is fixed and automatic, with no polarity CLI option. `--hard-stop preserve` is default. For1.5.3, `--hard-stop enable` adds immutable static hard stop. For1.6.3 it selects the inherited image default; explicit Group0 selection still wins. Existing OEM-SP80 inputs retain their default. There is no operation to disable a previously static-hard-stop-patched input.

The third OEM version component is not present in the native51 source. Without `--base-revision`,64/03 usesFF for unknown. A supplied13 is recorded as a caller declaration; it is not inferred from the filename or treated as native code proof. Major/minor version comes from actual OEM execution.

## Compatibility and publication

Compatibility is established from understood function structure, call edges, ROM relationships and exact RAM/MMIO contracts, with actual OEM execution probes. Signatures were developed against seven originals and three examined hard-stop variants. They are not a version/hash-to-patch-address table. Relocations can work if the contracts match; unknown functions, RAM layouts, tables or startup forms are refused. An unknown image is never automatically admitted as trusted.

`analyze: compatible` establishes structural/probe compatibility. Only `patch: passed` includes the complete mandatory patch suite. Rejection, signal, timeout or test failure never publishes a finished image. A separate worker has a120-second wall limit, CPU/file limits and per-emulation instruction bounds; timeout also terminates its LLVM children. Final EHEX publication is atomic and refuses existing targets.

| Output | Meaning |
|---|---|
| `firmware.ehex` | Complete image, published only after mandatory success |
| `report.json` | Input/output hashes, resolved functions/hooks/RAM, guards, declared/native version source, build ID, flags and named tests |
| `payload.resolved.s` | Actual assembled source with resolved constants |
| `payload.dis` | Appendix disassembly; add `build.append_at` to relative offsets |

Existing SP80 inputs are recognized and their image default is preserved. The standalone hard-stop transformation is an internal component of current MAINT builds. Failed runs retain a phase/reason report but no `firmware.ehex`.

## Regression and corpus checks

```sh
"$SEPLOS_PYTHON" -I -m unittest discover -s "$SEPLOS_PATCHER/tests"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/run_tests.py" \
  --report /private/tmp/seplos-patcher-tests-new.json
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --maint-version 1.5.3 \
  --out /private/tmp/seplos-corpus153-new
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --maint-version 1.6.3 \
  --out /private/tmp/seplos-corpus163-new
```

The SHA-256/size registry in [corpus.json](../../firmware/patcher/corpus.json) names seven OEM inputs under `vendor/firmware`, eight historical fixtures under `local/fixtures` and one fixed ACCESS reference image under `local/releases`. It excludes newly generated outputs and rejects missing or changed inputs. The two immutable [test metadata fixtures](../../firmware/patcher/tests/fixtures/README.md) replace implicit historical build-report dependencies; the current suite never opens `local/builds/oem16.06.13` reports. For each selected profile, the16-input/32-run matrix exercises preserved and enabled hard-stop settings; intentional refusals are expected outcomes. Confirm exact accepted options with `--help` for the installed revision.

MAINT1.5.3 supports native06.03/.04/.05/.11/.12/.13 and examined hard-stop inputs;04.06 is refused because its170-byte TX buffer cannot hold the175-byte MAINT answer. MAINT1.6.3 additionally requires understood gate/NVM/startup ABIs from06.11/.12/.13; earlier gate forms are intentionally refused. Existing MAINT images are refused as already modified bases. There is no double-patch or bypass option.

Current1.5.3 requires194 mandatory actual-Thumb groups;1.6.3 requires273, including all256×256 Group0/Event6 combinations. Native tests cover serialization, validation, loading, CRC, UART ownership, addresses/modeled packs, malformed frames, IAP failures, permission/persistence, capacity effects, ABI and native hard-stop/GPIO paths. Peripheral models do not establish physical flash timing, electrical behavior, real interrupt latency, brownouts, bootloader failures or multi-board bus behavior. [Validation methods and limits](validation-methods-and-limits.md) distinguishes current release verification from historical image-bound probes.

Historical sources, shared code probes and retained input images remain available for research, but do not extend the current output profiles. The current pre-change patcher source snapshot is retained under ignored `local/history/snapshots/patcher-before-current-profiles-2026-10-28/project`.

Keep full reports/resolved sources under `local/builds`; keep selected actual images under `local/releases` and publish only reviewed scalar identifiers/checksums in [release metadata](../../firmware/releases/README.md). Before device work compare the chosen image and report, back up parameters and both SNs, and use the [flash procedure](../tools/flashing.md).

## Release identity checks

The two [release JSONs](../../firmware/releases/README.md) are the current identity authorities. Verify actual retained images without native emulation:

```sh
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PATCHER/verify_releases.py" \
  --out /private/tmp/seplos-current-identities-new
```

To rebuild those profiles through the real worker, including mandatory native tests, and require byte-identical EHEX:

```sh
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PATCHER/verify_releases.py" --rebuild \
  --out /private/tmp/seplos-current-rebuilds-new
```

Both require the pinned OEM source and actual release images. `--images DIR` selects their directory; `--metadata-dir DIR` explicitly selects another reviewed metadata set. A metadata field referring to a build report is never followed. The embedded MNT template reserves two OEM-family bytes for runtime; verification checks the template and reconstructs those bytes from pinned OEM facts. Outputs refuse existing directories.

The complete frozen builders, tests and laboratory arrangement are retained under ignored `local/history/snapshots/mod-before-current-cleanup-2026-10-26/project`. Use the [historical runner](../../tools/run_historical_tests.py) with `--list` or an explicit `--suite`; it checks the source inventory before running version-bound tests. This workspace is separate from the current fixture/test dependency boundary. Keep the fixture registry and complete source inventory with retained validation reports: a top-level entry-point fingerprint alone does not inventory nested fixture files.
