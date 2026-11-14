# Offline OEM patcher

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT (EMU1101 Extended Firmware) is custom firmware for Seplos BMS 2.0 (EMU1101, hardware V16). The 1.5.x branch is Light; the 1.6.x branch is Full. Both profiles use the standard permission rule: 1 enables access and 0 denies it. The patcher requires Python3.11+, `unicorn==2.1.4` and LLVM's `llvm-mc`, `llvm-objcopy`, `llvm-objdump`, `llvm-nm`. Keep the venv outside the colon-containing project path at `~/.local/share/seplos-oem-patcher/venv`.

[Setup, builds and validation](../../docs/firmware/build-and-validation.md) gives complete commands, supported source contracts and output rules. Current profile choices are `--ext-version 1.5.6` (Light) and `--ext-version 1.6.7` (Full); 1.5.4/1.5.5 (Light) and 1.6.4/1.6.5/1.6.6 (Full) remain explicit reference builders. Select either profile explicitly; there is no default profile. Group0.bit3=1 permits UART1 power/RTC; 0 denies it. OEM inputs are included under `vendor/firmware`. Output directories are chosen with `--out` and must be new.

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
cd /private/tmp
"$HOME/.local/share/seplos-oem-patcher/venv/bin/python" -I \
  "$SEPLOS_PROJECT/mod/firmware/patcher/seplos_patch.py" --help
```

`analyze` establishes structural compatibility; `patch` also runs the complete mandatory Thumb suite before publishing `firmware.ehex`. Unknown contracts and already patched inputs are refused. The tool neither opens devices nor flashes hardware. Its sources, assembler, signature contracts and emulator are self-contained in `seplos`; LLVM/Unicorn are external dependencies.

Addressed parameter/identity access, maintenance services, UART1 power/RTC access control, UART0 marker access and storage diagnostics are available in Light 1.5.3+ and Full 1.6.3+. `seplos/payload.s` combines parameter, identity, maintenance and access-control logic; `marker_uart0.py/.s` supplies UART0 marker/identity; `storage_diagnostics.py` supplies Light storage diagnostics.

Full 1.6.3+ provides persistent individual lock/gate behavior through `cutoff.py/.s`, storage diagnostics and verified SOC saving before planned reset through `service.py/.s`, and parameter-selected hard stop through `configurable_hardstop.py/.s`. Light 1.5.4+ and Full 1.6.4+ provide addressed UART1 history and UART0/UART1 calibration and persisted-capacity/live-energy reads through `remote_diagnostics.py/.s`; the seven buildable profiles advertise these reads through EXT05 capability discovery. The common builders resolve version-specific addresses from native contracts. Signature/shape maintenance helpers under `tests` require independent analysis and review; rejected images are not automatically learned as trusted.

[Read-only wire layouts](../../docs/firmware/remote-diagnostics.md) · [Current contracts](../../docs/firmware/README.md) · [Release metadata](../releases/README.md) · [Changelog](../CHANGELOG.md)

## Test data and release verification

The maintained test suite uses two small, SHA-256-checked [metadata fixtures](tests/fixtures/README.md) extracted from preserved evidence. Historical build reports are not required for fixture loading. [corpus.json](corpus.json) names the exact 16 binary prerequisites with size and SHA-256. Seven OEM images are included in `vendor/firmware`; nine historical regression images are not distributed. Building a supported profile does not require those historical images, but the complete corpus check does. Missing or changed corpus inputs are errors. Additional files do not silently extend the corpus.

[verify_releases.py](verify_releases.py) checks the two current public release JSONs against their actual local images. Add `--rebuild` to invoke the bounded patcher worker and mandatory native tests and compare the complete regenerated EHEX. Metadata-only verification is separate from native execution. `--metadata-dir` can select reviewed metadata for any of the seven supported versions; retired versions are refused. No report path in metadata is followed. Both operations require a fresh `--out` directory. The [build guide](../../docs/firmware/build-and-validation.md#release-identity-checks) gives commands.

## Mandatory hardware and concurrency regressions

`hardware_tests.py` executes source-derived clock, UART, IRQMUX, timer,
watchdog and CAN initialization with explicit register assertions.
`uart_timing_tests.py` adds an opt-in divider/FIFO/timeout clock and native
UART1 RX/parser cases. `interrupt_tests.py` executes native vector handlers
with deterministic priorities, PRIMASK deferral, nesting and checked exception
frames during diagnostics/history and full-profile reset checkpointing.
`cutoff_tests.py` also checks the signed fast-current threshold and persistent
Off through every observed GPIO write. Each required group name is checked
before publication; omission and targeted mutation regressions exercise these
guards.

The A8 characterization intentionally reproduces a stale-write loss of wake
measurement enable under synthetic call states. Full-system reachability and
physical occurrence remain unproven. These are bounded peripheral/event models,
not physical timing or complete multi-pack tests. See
[validation methods and limits](../../docs/firmware/validation-methods-and-limits.md#deterministic-interrupt-and-uart-models).
Reference 1.5.4 (Light) and 1.6.4 (Full) retain their behavior with the EXT identity. Atomic scheduler cleanup is available in Light 1.5.5+ and Full 1.6.5+ through `scheduler_atomic.py/.s`. The Light 1.5.5 and Full 1.6.5 reference builds add six mandatory regression groups and one guarded OEM hook per profile (six/22 total). A separate guarded branch bypasses the displaced store. No additional persistent RAM is allocated.

Light 1.5.6 / Full 1.6.6 and later additionally use `polling.py/.s` for two guarded main-loop calls and twelve mandatory polling groups. Valid matching responses finish early; missing/invalid responses retain native expiry. The .6 totals are eight/24 hooks and zero/four persistent RAM bytes. The complete UART0 source contracts must match the reviewed OEM .13 implementation. See [polling behavior and limits](../../docs/firmware/early-polling.md).

Full 1.6.7 adds `ccl_ramp.py/.s`, one guarded downward-comparison hook (25 total), and nine mandatory groups for configurable CCL descent. Capability 0010 identifies addressed read/set services. Parent publication independently re-derives guarded OEM roles and rebuilds the whole candidate. No extra RAM; the field uses the existing mirrored-record tail. [Configuration contract](../../docs/firmware/configurable-ccl-ramp.md).
