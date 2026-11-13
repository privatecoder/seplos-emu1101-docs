# Firmware validation: methods and limits

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The patcher validates firmware offline. It analyzes the original input, builds the selected profile and executes native Cortex-M0 Thumb instructions with modeled peripherals before publishing an image. Passing these checks is software evidence for the named image and model; it does not establish electrical behavior or operation in a real multi-pack installation.

## Current releases and evidence scope

The current profiles are **EMU1101-EXT Light 1.5.5** and **EMU1101-EXT Full 1.6.5**, based on OEM **16.06.13** for the published releases. The [release metadata](../../firmware/releases/README.md) binds each exact image to its EHEX/application hashes, build ID, flags and test count. Both actual current images passed their mandatory native suites and rebuilt byte-identically. Both profiles have **not been flashed or hardware-tested**; `hardware_tested` remains false.

The current releases pass **257 mandatory execution groups for Light 1.5.5** and
**339 for Full 1.6.5**. The full profile includes all 65,536 function-switch/Event6
combinations. Six atomic scheduler groups exercise every controlled instruction
boundary, exact mask restoration, all-byte semantics/ABI, slow ticks and an OEM
negative control. The EXT05 Light 1.5.4/Full 1.6.4 references pass
251/333-group suites, with exact identities bound by the reference metadata. Execution-group counts differ from Python unit tests.

Only `patch` success with the mandatory suite permits publication of `firmware.ehex`. `analyze` establishes structural/probe compatibility without running the entire patched-image suite. Hash/EXT verification of a retained image is another separate check and is not a fresh native test result.

## Checks and what they establish

| Area | Software evidence | Limit |
|---|---|---|
| Input and discovery | Complete EHEX validation; understood code/RAM/MMIO contracts; native call/shape/probe checks. Unknown contracts and already EMU1101-EXT-patched bases are refused; the examined static-hard-stop variants remain supported. | Similar names, strings or board photos alone do not establish compatibility. |
| Protocol and permissions | Addressed requests, exact frame layouts, parameter validation, protected switches, rejected/broadcast/foreign requests and modeled UART ownership. | No measured gateway latency, physical bus arbitration or multi-board collision rate. |
| Persistence and reset | Actual CRC, serializer/readers/writers where covered; modeled IAP failures and word-boundary interruptions; copy classification and planned-reset verification. | No brownout waveform, partially programmed bits within a word, flash timing or endurance proof. A valid primary is not a versioned transaction journal. |
| Power and charge paths | Native control flow, lock priorities, configurable charge-inhibit masks, modeled GPIO writes and recovery conditions. | A software GPIO state is not a measurement of MOSFET conduction, body-diode current or electrical isolation. |
| Hook ABI and memory | Native execution checks, retained registers/stack, guarded hook contracts and modeled boundary cases. | Observed stack depth is not a universal bound for every interrupt nesting or system state. |
| Remote diagnostic reads | Native history cursor/EEPROM mode/stride, UART1 RX injection, active/stored calibration and saved-SOC shape/CRC, full-width energy, no repair/write side effects and unchanged hook/RAM bounds. Deterministic cases also execute enabled timer/protection/CMP handlers and concurrent addressed UART0 reception with deferred native parsing/encoding. | Modeled UART0 TX boundary; no complete multi-pack polling system, physical timing, real I2C timeout, whole-ring atomic snapshot, physical calibration accuracy or future boot-SOC guarantee. |
| Hardware initialization | Native clock selection/readback, UART dividers and configuration, IRQ routes/priorities, timer loads, watchdog modes/feed guard and CAN selector bit timing. | Synthetic MMIO readback; no oscillator accuracy, electrical pin, physical watchdog deadline or full boot proof. |
| Fast charge handover | Full-profile signed current boundaries −1001/−1/0/999/1000/1001, individual state/interlock gates and persistent Off through native control paths, including intermediate GPIO writes. | Synthetic sensor inputs and modeled persistence; no current calibration or electrical isolation proof. |
| Host helpers | Synthetic transport/port tests, strict frame and image validation, no replay after uncertain writes, explicit target selection. | Fake-port success is not a hardware update or a guarantee about a particular gateway. |

[Storage and reset](storage-and-reset.md), [UART receive ownership](../../../analysis/protocols/uart1-receive-gap-and-buffer-ownership.md) and [original power behavior](../../../analysis/firmware/power-on-off.md) describe the corresponding firmware contracts and evidence limits.

## Deterministic interrupt and UART models

The opt-in models execute native instructions at controlled event boundaries;
the existing basic receive helper is unchanged. They derive native roles from
the original image's code, vectors and validated facts rather than a
version-to-address table or disposable build reports. Missing required group
names prevent publication for both profiles.

Interrupt cases check native priorities, PRIMASK deferral, equal-priority
waiting and four-level nesting. A modeled eight-word exception frame restores
only hardware-stacked registers; callee-saved registers, SP, frame contents,
PRIMASK and stack-envelope canaries are checked independently. Actual enabled
TIMR0 measurement/fast/protection calls, TIMR1 progress/feed logic and the
comparator discharge-trip path execute. History, RAM snapshots and full-profile
reset-checkpoint cases receive deterministic preemption. UART0 receives an
addressed frame during diagnostic work; the native deferred parser and encoder
complete through a modeled TX boundary. ADC inputs are synthetic. Event
schedules, sentinel exception returns and a bounded stack envelope establish
neither physical latency nor full NVIC/tail-chaining or complete system behavior.

UART1 timing uses exact synthetic clock counts, the native divider and timeout
configuration, an eight-byte FIFO and actual RX IRQ/parser execution. Cases
cover below/exact/above timeout boundaries, arrival-versus-timeout ordering,
silence reset, FIFO overflow and adjacent merged/separated frames. The manual
describes RX threshold assertion inconsistently (`>=` on p.101 versus `>` on
pp.104/107); both interpretations are exercised. In this model CTRL bit 3 is
RXNE and BAUD bit 16 is enabled RX/timeout interrupt status, not simply FIFO
nonempty. Nominal timing is not measured oscillator or bus timing. The separate
IRQ coexistence harness uses explicit chunked arrivals and a declared eight-byte
synthetic FIFO bound; it is not the eight-byte timing model.

The A8 characterization reproduces a native stale-write loss of the wake
measurement-enable bit under explicit synthetic call states. Ordered and
already-pending-bit controls distinguish that loss from ordinary coalescing.
[Scheduler flags and effects](../../../analysis/firmware/startup-clock-timers.md#backlog-flag-coalescing-and-a-controlled-lost-update)
explain which measurement/protection paths could be affected. Full-system
reachability and physical occurrence remain unproven. A passing characterization
records the inherited behavior; it does not certify absence of races or fix the
firmware. Light 1.5.5 / Full 1.6.5 additionally run the fixed cleanup at all 13
veneer/helper/continuation boundaries under both incoming masks, 2,048
flag/mask/carry/overflow combinations, and native coalesced/new-pending slow ticks.
The introduced masked interval contains six instructions, counted from the fresh
load through saved-mask restore. This is an instruction bound, not measured
hardware latency. The fix covers the reproduced main cleanup window for maskable
IRQs; it does not claim all firmware races are eliminated. Mutation regressions independently check that changed priorities,
missing progress/RX state, ABI/frame corruption, UART configuration changes and
a shifted signed-current threshold fail their intended assertions.

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

Historical research probes and reports remain under ignored `local/`, with their exact image hashes, source inventories, dependency bindings and model limits. They do not establish a current-release audit or hardware result. The [historical test runner](../../tools/run_historical_tests.py) lists prerequisites and executes only explicitly selected suites; [analysis tool prerequisites](../../tools/firmware-analysis/README.md) describe retained inputs and fresh-output requirements.

No emulator result establishes the cause of a particular historical communication failure, SOC change or display symptom without matching device evidence. Before actual updates, follow the separate [flash and application-verification procedure](../tools/flashing.md).
