# Building and validating EMU1101-EXT firmware

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The patcher analyzes an OEM EHEX, resolves code/RAM contracts, assembles a complete version-specific appendix and runs mandatory Cortex-M0 execution tests. It runs offline without an LLM, network connection, historical patch chain or device access. It does not flash hardware.

## Environment

Require Python 3.11+, `unicorn==2.1.4`, and LLVM programs `llvm-mc`, `llvm-objcopy`, `llvm-objdump`, `llvm-nm`. Tested environments include Python 3.11 and 3.14.7 with Homebrew LLVM 22.1.5. Unicorn is the patcher's only additional Python package. Retain the separate device-tools environment at `~/.local/share/seplos-firmware-tools/venv`, which requires `pyserial==3.5` and `unicorn==2.1.4`. Do not use `python -O`, which disables assertions and is refused.

Set the project root to the checkout, quote paths, and use a neutral working directory. Keep the virtual environment outside the checkout to support project paths with spaces or colons. Retain the established patcher location `~/.local/share/seplos-oem-patcher/venv` and the separate device-tools environment. Set the interpreter variables explicitly; reuse them if they already contain the pinned dependencies:

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

Output directories must be new and their parent must exist. Inputs are never overwritten. Use separate fresh directories for each invocation.

```sh
SEPLOS_OUTPUT_ROOT="$(mktemp -d /private/tmp/seplos-ext-builds.XXXXXX)"
SEPLOS_INPUT="$SEPLOS_PROJECT/vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" analyze "$SEPLOS_INPUT" \
  --ext-version 1.5.6 --base-revision 13 \
  --out "$SEPLOS_OUTPUT_ROOT/ext156-analysis-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --ext-version 1.5.6 --base-revision 13 \
  --out "$SEPLOS_OUTPUT_ROOT/ext156-build-new"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/seplos_patch.py" patch "$SEPLOS_INPUT" \
  --ext-version 1.6.7 --base-revision 13 \
  --out "$SEPLOS_OUTPUT_ROOT/ext167-build-new"
```

Current profiles are Light 1.5.6 and Full 1.6.7; explicit Light 1.5.4/1.5.5 and Full 1.6.4/1.6.5/1.6.6 reference builders remain available. `--ext-version` is required. Group0.bit3=1 permits UART1 power/RTC; 0 denies it. This rule applies throughout both versioned branches. `--hard-stop preserve` is default. Light releases from 1.5.3 use an immutable static hard-stop image option. Full releases from 1.6.3 provide runtime Group0 selection; `--hard-stop enable` selects only the inherited image default, and explicit Group0 selection still wins. Existing OEM-SP80 inputs retain their default. There is no operation to disable a previously static-hard-stop-patched input.

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

Existing SP80 inputs are recognized and their image default is preserved. The standalone hard-stop transformation is an internal component of current EMU1101-EXT builds. Failed runs retain a phase/reason report but no `firmware.ehex`.

## Regression and corpus checks

The complete repository regression suite and corpus matrix require the nine
historical regression images listed in the registry; these images are not
distributed. The mandatory native tests run by each `patch` invocation above
are independent of those additional inputs.

```sh
"$SEPLOS_PYTHON" -I -m unittest discover -s "$SEPLOS_PATCHER/tests"
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/run_tests.py" \
  --report /private/tmp/seplos-patcher-tests-new.json
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --ext-version 1.5.6 \
  --out /private/tmp/seplos-corpus156-new
"$SEPLOS_PYTHON" -I "$SEPLOS_PATCHER/verify_corpus.py" \
  --firmware-root "$SEPLOS_PROJECT" --ext-version 1.6.7 \
  --out /private/tmp/seplos-corpus167-new
```

The SHA-256/size registry in [corpus.json](../../firmware/patcher/corpus.json) names seven OEM inputs included under `vendor/firmware` and nine historical regression images that are not distributed. Building any supported profile and running its mandatory tests uses the selected OEM input; it does not require the historical corpus. The complete corpus commands above require all 16 registry inputs and cannot run from the public checkout alone. The registry excludes newly generated outputs and rejects missing or changed inputs. The two immutable [test metadata fixtures](../../firmware/patcher/tests/fixtures/README.md) remove the test suite's dependency on historical build reports. For each selected profile, the 16-input/32-run matrix exercises preserved and enabled hard-stop settings; intentional refusals are expected outcomes. Confirm exact accepted options with `--help` for the installed revision.

The .4/.5 reference profiles produce these retained corpus results with either hard-stop option:

| OEM input | EMU1101-EXT Light 1.5.5 | EMU1101-EXT Full 1.6.5 |
|---|---|---|
| 16.04.06 | Refused: UART1 buffers are too small | Refused: UART1 buffers are too small |
| 16.06.03 / 16.06.04 / 16.06.05 SP80 | Builds and passes required tests | Refused: unsupported charge-gate ABI |
| 16.06.11 / 16.06.12 / 16.06.13 | Builds and passes required tests | Builds and passes required tests |

The complete 16-input matrix includes fixed historical hard-stop/custom-firmware inputs: 32 runs per profile, 18 builds/14 expected refusals for light and 12 builds/20 expected refusals for full. Light 1.5.4/Full 1.6.4 reference matrices pass all 64 expected outcomes: 30 builds, 34 expected refusals and 12,459 grouped native checks. The retained Light 1.5.5/Full 1.6.5 matrices pass all 64 expected outcomes: 30 builds, 34 refusals and 12,639 grouped native checks. These are offline results for the retained inputs, not hardware compatibility guarantees for every board or future OEM image.

The .6 profiles additionally require the complete reviewed UART0 polling contracts:

| OEM input | Light 1.5.6 | Full 1.6.6 |
|---|---|---|
| 16.04.06 | Refused: UART1 buffers too small | Refused: UART1 buffers too small |
| 16.06.03 / 16.06.04 / 16.06.05 SP80 | Refused: unmatched polling contract | Refused: unsupported charge-gate ABI |
| 16.06.11 / 16.06.12, including retained hard-stop variants | Refused: unmatched polling contract | Refused: unmatched polling contract |
| 16.06.13, including the retained hard-stop variant | Builds and passes required tests | Builds and passes required tests |

The .6 corpus comprises 64 runs across both profiles: eight successful builds, 56 expected refusals and 3,532 grouped native checks. Preserved and enabled hard-stop defaults both pass on OEM .13 and its retained hard-stop variant. Refusal expectations are checked against the exact source/input hashes and reported contract failure. These corpus totals belong to Light 1.5.6 / Full 1.6.6. Full 1.6.7 adds source-bound CCL checks and has passed the mandatory build on the pinned OEM .13 source; the complete 32-run Full 1.6.7 corpus has not been rerun.

The current release reference is OEM 16.06.13. Both profiles additionally require proven history, calibration and saved-SOC/live-energy layouts; a matching older base profile alone is insufficient. The seven-OEM corpus explicitly checks acceptance or safe refusal for each image and hard-stop option. Unknown native roles, malformed shapes and unsupported gate/NVM/startup ABIs are refused. Existing EMU1101-EXT images are refused as already modified bases. There is no double-patch or bypass option.

Current EXT05 Light 1.5.4/Full 1.6.4 references pass strengthened 251/333-group suites; their new identities are bound by the reference metadata. The retained fixed Light 1.5.5/Full 1.6.5 releases pass 257/339 groups. Additional mandatory groups cover native hardware initialization, deterministic interrupt coexistence, UART timing and full-profile signed fast-current/Off boundaries. The full profile includes all 256×256 Group0/Event6 combinations. Native tests cover serialization, validation, loading, CRC, UART ownership, addresses/modeled packs, malformed frames, IAP failures, permission/persistence, capacity effects, ABI and native hard-stop/GPIO paths. Remote read tests cover own/foreign addresses, calibration/SOC shape and CRC, signed active values, full-width live energy, history empty/oldest/next/wrap, read-failure cursor rollback, no mirror repair/writes and UART1 RX injection at the EEPROM transfer boundary. The .5 profiles add one guarded scheduler hook each (six/22 total) and a guarded continuation branch; persistent RAM remains zero/four bytes. Deterministic preemption cases execute enabled timer/protection/CMP handlers and concurrent addressed UART0 reception during diagnostic/history work, followed by native deferred parsing and encoding through a modeled TX boundary. The .6 profiles additionally execute complete modeled UART0 polling rounds and native aggregation/CCL paths; physical multi-board timing remains untested. The OEM A8 negative control deliberately reproduces inherited behavior under synthetic call states. Fixed profiles additionally require preservation across all 13 instruction boundaries under both masks, complete byte/ABI cases and native slow-tick controls; passing them does not establish exhaustive race freedom. Peripheral models do not establish physical flash timing, electrical behavior, real interrupt latency, brownouts, bootloader failures or multi-board bus behavior. [Validation methods and limits](validation-methods-and-limits.md) distinguishes current release verification from historical image-bound probes.

Historical sources and research inputs are not distributed and do not extend the supported output profiles.

Publish only reviewed scalar identifiers/checksums in [release metadata](../../firmware/releases/README.md). Before device work compare the chosen image and report, back up parameters and both SNs, and use the [flash procedure](../tools/flashing.md).

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

Both require the pinned OEM source and actual release images. Prebuilt custom images are not distributed; provide the matching generated images in a directory selected with `--images DIR`. `--metadata-dir DIR` explicitly selects another reviewed metadata set, including the 1.5.4/1.6.4 references. A metadata field referring to a build report is never followed. Current EXT05 is 21 bytes with appended capability mask 000F for Light and 001F for Full 1.6.7; [remote diagnostics](remote-diagnostics.md) defines its offsets and read contracts. The [capability matrix](uart-write-capabilities.md) lists EHEX hashes and each release JSON also supplies the application hash. The embedded EXT template reserves two OEM-family bytes for runtime; verification checks the template and reconstructs those bytes from pinned OEM facts. Outputs refuse existing directories.

The historical builders, tests and laboratory dependencies are not included in the public checkout. Use the [historical runner](../../tools/run_historical_tests.py) with `--list` or an explicit `--suite`; it checks the source inventory before running version-bound tests. This workspace is separate from the current fixture/test dependency boundary. Keep the fixture registry and complete source inventory with retained validation reports: a top-level entry-point fingerprint alone does not inventory nested fixture files.

Full 1.6.7 passes 360 mandatory groups, including nine CCL configuration groups. Its parent publication gate re-derives the OEM facts and rebuilds the candidate before publication. The [CCL contract](configurable-ccl-ramp.md) defines persistence, input validation and limits.
