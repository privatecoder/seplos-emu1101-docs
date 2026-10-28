# Firmware validation: methods and limits

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The patcher validates firmware offline. It analyzes the original input, builds the selected profile and executes native Cortex-M0 Thumb instructions with modeled peripherals before publishing an image. Passing these checks is software evidence for the named image and model; it does not establish electrical behavior or operation in a real multi-pack installation.

## Current releases and evidence scope

The current profiles are **MAINT 1.5.3** and **MAINT 1.6.3**, based on OEM **16.06.13** for the published releases. The [release metadata](../../firmware/releases/README.md) binds each exact image to its EHEX/application hashes, build ID, flags and test count. Both published profiles have offline execution evidence and have **not been flashed or hardware-tested**.

The metadata records 194 mandatory execution groups for 1.5.3 and 273 for 1.6.3. The full profile includes all 65,536 combinations of the function-switch byte and Event6 for configurable hard stop. These counts describe the published profile suites; they are different from the number of Python unit tests in the patcher's test runner.

Only `patch` success with the mandatory suite permits publication of `firmware.ehex`. `analyze` establishes structural/probe compatibility without running the entire patched-image suite. Hash/MNT verification of a retained image is another separate check and is not a fresh native test result.

## Checks and what they establish

| Area | Software evidence | Limit |
|---|---|---|
| Input and discovery | Complete EHEX validation; understood code/RAM/MMIO contracts; native call/shape/probe checks. Unknown contracts and already MAINT-patched bases are refused; the examined static-hard-stop variants remain supported. | Similar names, strings or board photos alone do not establish compatibility. |
| Protocol and permissions | Addressed requests, exact frame layouts, parameter validation, protected switches, rejected/broadcast/foreign requests and modeled UART ownership. | No measured gateway latency, physical bus arbitration or multi-board collision rate. |
| Persistence and reset | Actual CRC, serializer/readers/writers where covered; modeled IAP failures and word-boundary interruptions; copy classification and planned-reset verification. | No brownout waveform, partially programmed bits within a word, flash timing or endurance proof. A valid primary is not a versioned transaction journal. |
| Power and charge paths | Native control flow, lock priorities, configurable charge-inhibit masks, modeled GPIO writes and recovery conditions. | A software GPIO state is not a measurement of MOSFET conduction, body-diode current or electrical isolation. |
| Hook ABI and memory | Native execution checks, retained registers/stack, guarded hook contracts and modeled boundary cases. | Observed stack depth is not a universal bound for every interrupt nesting or system state. |
| Host helpers | Synthetic transport/port tests, strict frame and image validation, no replay after uncertain writes, explicit target selection. | Fake-port success is not a hardware update or a guarantee about a particular gateway. |

[Storage and reset](storage-and-reset.md), [UART receive ownership](../../../analysis/protocols/uart1-receive-gap-and-buffer-ownership.md) and [original power behavior](../../../analysis/firmware/power-on-off.md) describe the corresponding firmware contracts and evidence limits.

## Reproduce current validation

Use the prepared environment and exact source inputs from the [build guide](build-and-validation.md). From a neutral directory, with `SEPLOS_PROJECT` and `SEPLOS_PYTHON` set as described there:

```sh
SEPLOS_PATCHER="$SEPLOS_PROJECT/mod/firmware/patcher"
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PATCHER/run_tests.py" \
  --report /private/tmp/seplos-unit-tests-new.json
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PATCHER/verify_releases.py" \
  --out /private/tmp/seplos-release-identities-new
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PATCHER/verify_releases.py" --rebuild \
  --out /private/tmp/seplos-release-rebuilds-new
```

Output paths must be fresh. The first runs the maintained Python regressions; the second verifies retained current images and metadata; the third additionally rebuilds through the real worker and mandatory native suites and requires byte-identical EHEX. LLVM and Unicorn are required for native execution. Missing pinned binary prerequisites must be restored, not skipped or replaced by another image. No command opens a device.

The [metadata fixture registry](../../firmware/patcher/tests/fixtures/registry.json) records extracted facts and provenance; [corpus.json](../../firmware/patcher/corpus.json) records the exact binary prerequisites. Current patcher tests do not load disposable historical build reports. Keep these registries and a full source inventory alongside validation reports; the current test runner's bundle fingerprint does not inventory every nested test/fixture file.

## Version-bound research tools and historical evidence

Research probes under `mod/tools/firmware-analysis` can deliberately bind older exact images and their saved facts. That scope is distinct from current release validation. For example, `audit_firmware_v16.py` covers OEM .13 and fixed **1.5.1/1.6.1** images; its four phases examine persistence, startup/watchdog, UART interrupts and hooks. It must not be relabelled as a full audit of 1.5.3/1.6.3. [Analysis tool prerequisites](../../tools/firmware-analysis/README.md) describe the retained inputs and fresh-output requirements.

The complete dated report and raw results remain under ignored `local/research/validation/evidence/Vierfachpruefung-2026-10-23/`, including `validation-audit-2026-10-23.md`. It records exact image hashes, per-phase checks, observed stack depths and model exclusions. Fixed historical tools and their dependencies are preserved separately; the [historical test runner](../../tools/run_historical_tests.py) lists prerequisites and executes only explicitly selected suites.

No emulator result establishes the cause of a particular historical communication failure, SOC change or display symptom without matching device evidence. Before actual updates, follow the separate [flash and application-verification procedure](../tools/flashing.md).
