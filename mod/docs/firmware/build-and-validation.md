# Building and validating MAINT firmware

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The patcher analyzes an OEM EHEX, resolves code/RAM contracts, assembles a complete version-specific appendix and runs mandatory Cortex-M0 execution tests. It runs offline without an LLM, network connection, historical patch chain or device access. It does not flash hardware.

## Environment

Require Python 3.11+, `unicorn==2.1.4`, and LLVM programs `llvm-mc`, `llvm-objcopy`, `llvm-objdump`, `llvm-nm`. Tested environments include Python 3.11 and 3.14.7 with Homebrew LLVM 22.1.5. Unicorn is the patcher's only additional Python package. Retain the separate device-tools environment at `~/.local/share/seplos-firmware-tools/venv`, which requires `pyserial==3.5` and `unicorn==2.1.4`. Do not use `python -O`, which disables assertions and is refused.

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
mkdir -p "$SEPLOS_PROJECT/local/builds/runs"
SEPLOS_INPUT="$SEPLOS_PROJECT/vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" analyze "$SEPLOS_INPUT" \
  --maint-version 1.5.4 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint154-analysis-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --maint-version 1.5.4 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint154-build-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --maint-version 1.6.4 --base-revision 13 \
  --out "$SEPLOS_PROJECT/local/builds/runs/maint164-build-new"
```

The only profiles are 1.5.4 and 1.6.4; `--maint-version` is required. Positive permission polarity is fixed and automatic, with no polarity CLI option. `--hard-stop preserve` is default. For 1.5.4, `--hard-stop enable` adds immutable static hard stop. For 1.6.4 it selects the inherited image default; explicit Group0 selection still wins. Existing OEM-SP80 inputs retain their default. There is no operation to disable a previously static-hard-stop-patched input.

The third OEM version component is not present in the native 51 source. Without `--base-revision`, 64/03 uses FF for unknown. A supplied 13 is recorded as a caller declaration; it is not inferred from the filename or treated as native code proof. Major/minor version comes from actual OEM execution.

## Compatibility and publication

Compatibility is established from understood function structure, call edges, ROM relationships and exact RAM/MMIO contracts, with actual OEM execution probes. Signatures were developed against seven originals and three examined hard-stop variants. They are not a version/hash-to-patch-address table. Relocations can work if the contracts match; unknown functions, RAM layouts, tables or startup forms are refused. An unknown image is never automatically admitted as trusted.

`analyze: compatible` establishes structural/probe compatibility. Only `patch: passed` includes the complete mandatory patch suite. Rejection, signal, timeout or test failure never publishes a finished image. A separate worker has a 120-second wall limit, CPU/file limits and per-emulation instruction bounds; timeout also terminates its LLVM children. Final EHEX publication is atomic and refuses existing targets.

| Output | Meaning |
|---|---|
| `firmware.ehex` | Complete image, published only after mandatory success |
| `report.json` | Input/output hashes, resolved functions/hooks/RAM, guards, declared/native version source, build ID, flags and named tests |
| `payload.resolved.s` | Actual assembled source with resolved constants |
| `payload.dis ` | Appendix disassembly; add `build.append_at` to relative offsets |

Existing SP80 inputs are recognized and their image default is preserved. The standalone hard-stop transformation is an internal component of current MAINT builds. Failed runs retain a phase/reason report but no `firmware.ehex`.

## Regression and corpus checks

```sh
"$SEPLOS_PYTHON" -I -m unittest discover -s "$SEPLOS_PATCHER/tests"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/run_tests.py" \
  --report /private/tmp/seplos-patcher-tests-new.json
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --maint-version 1.5.4 \
  --out /private/tmp/seplos-corpus154-new
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --maint-version 1.6.4 \
  --out /private/tmp/seplos-corpus164-new
```

The SHA-256/size registry in [corpus.json](../../firmware/patcher/corpus.json) names seven OEM inputs under `vendor/firmware `, eight historical fixtures under `local/fixtures` and one fixed ACCESS reference image under `local/releases`. It excludes newly generated outputs and rejects missing or changed inputs. The two immutable [test metadata fixtures](../../firmware/patcher/tests/fixtures/README.md) replace implicit historical build-report dependencies; the current suite never opens `local/builds/oem16.06.13` reports. For each selected profile, the 16-input/32-run matrix exercises preserved and enabled hard-stop settings; intentional refusals are expected outcomes. Confirm exact accepted options with `--help` for the installed revision.

The retained OEM corpus currently produces these results with either hard-stop option:

| OEM input | MAINT 1.5.4 | MAINT 1.6.4 |
|---|---|---|
| 16.04.06 | Refused: UART1 buffers are too small | Refused: UART1 buffers are too small |
| 16.06.03 / 16.06.04 / 16.06.05 SP80 | Builds and passes required tests | Refused: unsupported charge-gate ABI |
| 16.06.11 / 16.06.12 / 16.06.13 | Builds and passes required tests | Builds and passes required tests |

The complete 16-input matrix includes fixed historical hard-stop/MAINT references: 32 runs per profile, 18 builds/14 expected refusals for light and 12 builds/20 expected refusals for full. Across both profiles, 11,313 grouped native checks passed. These are offline results for the retained inputs, not hardware compatibility guarantees for every board or future OEM image.

The current release reference is OEM 16.06.13. Both profiles additionally require proven history, calibration and saved-SOC/live-energy layouts; a matching older base profile alone is insufficient. The seven-OEM corpus explicitly checks acceptance or safe refusal for each image and hard-stop option. Unknown native roles, malformed shapes and unsupported gate/NVM/startup ABIs are refused. Existing MAINT images are refused as already modified bases. There is no double-patch or bypass option.

The current 1.5.4 release passed 214 mandatory actual-Thumb groups; 1.6.4 passed 293. The full profile includes all 256×256 Group0/Event6 combinations. Native tests cover serialization, validation, loading, CRC, UART ownership, addresses/modeled packs, malformed frames, IAP failures, permission/persistence, capacity effects, ABI and native hard-stop/GPIO paths. Remote read tests cover own/foreign addresses, calibration/SOC shape and CRC, signed active values, full-width live energy, history empty/oldest/next/wrap, read-failure cursor rollback, no mirror repair/writes and UART1 RX injection at the EEPROM transfer boundary. Both profiles keep the same hook count and persistent RAM. Full concurrent UART0 polling, timer and protection execution during history reads has not been tested. Peripheral models do not establish physical flash timing, electrical behavior, real interrupt latency, brownouts, bootloader failures or multi-board bus behavior. [Validation methods and limits](validation-methods-and-limits.md) distinguishes current release verification from historical image-bound probes.

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

Both require the pinned OEM source and actual release images. `--images DIR` selects their directory; `--metadata-dir DIR` explicitly selects another reviewed metadata set. A metadata field referring to a build report is never followed. Current MNT05 is 21 bytes with appended capability mask 000F; [remote diagnostics](remote-diagnostics.md) defines its offsets and read contracts. Current build IDs are `80112d861b8329c4` (light) and `a8676b52bae281ff` (full); the [capability matrix](uart-write-capabilities.md) lists EHEX hashes and each release JSON also supplies the application hash. The embedded MNT template reserves two OEM-family bytes for runtime; verification checks the template and reconstructs those bytes from pinned OEM facts. Outputs refuse existing directories.

The complete frozen builders, tests and laboratory arrangement are retained under ignored `local/history/snapshots/mod-before-current-cleanup-2026-10-26/project`. Use the [historical runner](../../tools/run_historical_tests.py) with `--list` or an explicit `--suite`; it checks the source inventory before running version-bound tests. This workspace is separate from the current fixture/test dependency boundary. Keep the fixture registry and complete source inventory with retained validation reports: a top-level entry-point fingerprint alone does not inventory nested fixture files.
