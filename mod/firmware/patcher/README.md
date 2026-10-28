# Offline OEM patcher

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Build MAINT1.5.3 or MAINT1.6.3 firmware with intrinsic positive permission polarity. The patcher requires Python3.11+, `unicorn==2.1.4` and LLVM's `llvm-mc`, `llvm-objcopy`, `llvm-objdump`, `llvm-nm`. Keep the venv outside the colon-containing project path at `~/.local/share/seplos-oem-patcher/venv`.

[Setup, builds and validation](../../docs/firmware/build-and-validation.md) gives complete commands, supported source contracts and output rules. The only profile choices are `--maint-version 1.5.3` and `--maint-version 1.6.3`. Select either profile explicitly; there is no default profile. Positive permission polarity is automatic. Firmware inputs live under project-relative `vendor/firmware`; generated builds and historical fixtures live under `local/builds` and `local/fixtures`. Output directories must be new.

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
cd /private/tmp
"$HOME/.local/share/seplos-oem-patcher/venv/bin/python" -I \
  "$SEPLOS_PROJECT/mod/firmware/patcher/seplos_patch.py" --help
```

`analyze` establishes structural compatibility; `patch` also runs the complete mandatory Thumb suite before publishing `firmware.ehex`. Unknown contracts and already patched inputs are refused. The tool neither opens devices nor flashes hardware. Its sources, assembler, signature contracts and emulator are self-contained in `seplos`; LLVM/Unicorn are external dependencies.

`seplos/payload.s` combines parameter, identity, maintenance and access-control logic. `cutoff.py/.s` supplies full-profile lock/gate behavior; `marker_uart0.py/.s` supplies UART0 marker/identity; `storage_diagnostics.py` supplies lightweight diagnostics; `service.py/.s` supplies full diagnostics and verified reset; `configurable_hardstop.py/.s` supplies parameter-selected hard stop. The common builders resolve version-specific addresses from native contracts. Signature/shape maintenance helpers under `tests` require independent analysis and review; rejected images are not automatically learned as trusted.

[Current contracts](../../docs/firmware/README.md) · [Release metadata](../releases/README.md) · [Changelog](../CHANGELOG.md)

## Test data and release verification

The maintained test suite uses two small, SHA-256-checked [metadata fixtures](tests/fixtures/README.md) extracted from preserved evidence. It never loads `local/builds/oem16.06.13` reports. [corpus.json](corpus.json) names the exact 16 binary prerequisites with size and SHA-256; originals and historical EHEX references stay in `vendor/` and ignored `local/`. Missing or changed inputs are errors. Additional files do not silently extend the corpus.

[verify_releases.py](verify_releases.py) checks the two current public release JSONs against their actual local images. Add `--rebuild` to invoke the bounded patcher worker and mandatory native tests and compare the complete regenerated EHEX. Metadata-only verification is separate from native execution. `--metadata-dir` can select reviewed metadata for either supported profile; retired versions are refused. No report path in metadata is followed. Both operations require a fresh `--out` directory. The [build guide](../../docs/firmware/build-and-validation.md#release-identity-checks) gives commands.
