# Patcher changelog

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

## Connection and topology documentation, 2026-10-26

- No firmware change. The connection guide distinguishes manufacturer-specified PC/FSU banks without a Seplos master from conditional direct-UART0 inverter use. It documents bus ownership, CAN profiles, monitoring paths and maintenance requirements.
- UART1-4F also responds locally on slaves; the master alias 02 can collide with pack 2. System commands 60–63 are master-only at 02/12, rather than 00.
- The legacy UART0 FC03-like CRC read path was identified and natively replayed in 16.04.06: two-byte byte count, response builder `0x1474`. It is absent from the next available build, 16.06.03; register semantics remain incomplete.
- Initialization confirms UART0 at 9600 baud only in 04.06, UART0 at 19200 in later examined images, and UART1 at 9600 throughout. The 04.06-9600 bootloader rate remains unverified.
- No new hardware or inverter test, image modification or flashing.

[Connection guide](../../analysis/hardware/ports-and-topologies.md).

## MAINT 1.5.3: positive power/RTC permission, 2026-10-24

- Group0.bit3=1 permits UART1 power/RTC; 0 denies it. UART0 remains independent, UART1-4D remains unrestricted, and UART1-A1 bit3 protection is unchanged. No parameter conversion.
- Reuses the existing `POSITIVE_FLAGS` branch without assembler source changes: five unchanged OEM hook sites and zero extra RAM. Exactly 11 application bytes change: one condition byte plus version, flags and build ID. The OEM prefix, including hook bytes, is identical to the lightweight baseline.
- Bits4/5 remain reserved. No Cutoff, persistent pack lock or SOC checkpoint before reset. Unrestricted addressed UART0/UART1 64/04 storage diagnostics and the other existing functions remain available.
- MNT04: 19 bytes, LENGTH8026, patch `01 05 03`, build ID `2b89286ed6c14604`, flags `3A` (`3B` with static Hard-Stop). Image flag `08` identifies the polarity of existing functions; Cutoff capability flag `04` is absent.
- Passed 194 mandatory Thumb groups, 105 patcher tests and 60 tool tests. The 16-image/48-profile corpus produced 28 passes, 20 expected refusals and 8,489 grouped Thumb checks. A regression exposed the publisher trust boundary; the positive-1.6 suite gate now depends on the requested profile rather than the worker's claim.
- The main matrix was regenerated for OEM.13/1.5.3/1.6.3 only, with file SHA256s. Sources and checks are retained locally; older images were reproduced byte-for-byte.
- Not flashed or hardware-tested; no commit or push.

[Contract](../docs/firmware/maint153-positive-power.md).

## MAINT 1.6.3: configurable hard stop, 2026-10-24

- New stored Hard-Stop selection for intermittent recharge waiting, using Group0.bits6/7 together: `00` explicitly selects soft stop, `40` explicitly selects hard stop, and `80/C0` inherits the build default. Old FF retains soft-stop behavior in the published image. Arbitrary older values with bit7=0 already mean an explicit selection; no NVM migration.
- A UI switch writes `(fresh_group0 & 0x3f) | (enabled ? 0x40 : 0)`. UART0/UART2 and permitted UART1-A1 update the live value, preserving bits0–5 and existing protection rules.
- One additional verified OEM hook before the native Event6 TST/BNE selects mask `71/73` from the parameter: 21 hook sites and 36 additional code bytes. The existing four-byte lock cache remains; no additional permanent RAM.
- Native temperature, OVP and recovery priorities and the persistent pack lock remain. Group5.bit1 must enable intermittent recharge waiting. Discharge above 10 A for about 10 s can still trigger native charge recovery; this feature does not replace general pack off.
- MNT04 remains 19 bytes/LENGTH8026; patch `01 06 03`, build ID `baa01ecd5af4eb28`. New image flag `80` identifies configurability; bit0 then represents only the build default, rather than the current state. Published flags are FE, or FF with a hard-stop build default. Determine the current state from 47/Group0 and 64/03 together.
- Passed 273 mandatory Thumb groups, including all 256×256 Group0/Event6 combinations, 94 patcher tests and 60 tool tests. Final 16-image/48-profile corpus: 22 passes, 26 expected refusals and 7,484 grouped Thumb checks. Independent review was performed. The native .11 recovery-counter address is derived from its accesses rather than assumed.
- MAINT1.5.2 is unchanged. The main matrix was regenerated for OEM.13/1.5.2/1.6.3 only, with complete EHEX SHA256s. Sources, emulators and checkers are retained locally.
- Validation was entirely offline; no flashing, commit or push.

[Contract](../docs/firmware/maint163-configurable-hard-stop.md).

## MAINT 1.5.2: lightweight firmware with storage diagnostics, 2026-10-24

- New cumulative 1.5 alternative with addressed 64/04 on UART0/UART1 for master and slaves 0–21. Foreign addresses and FF remain silent; no permission is required.
- Format01 has 10 bytes/LENGTH B014: parameter/SOC record classes and comparisons, read directly from flash without repair or NVM writes. Lock fields FF/FF and cache flags00 mean unavailable; bit5 remains reserved. The client displays the absent runtime cache as null.
- The same five OEM hook sites, 472 additional code bytes and no new permanent RAM. No new MOSFET, CCL, parameter-NVM or reset hooks. Bit3=0 remains UART1 power permission; no SOC checkpoint before reset or new parameters.
- MNT04 remains 19 bytes; patch `01 05 02`, flags `32` (`33` with Hard-Stop), build ID `89d85c61b40e03da`. Application size 56,016 bytes, appendage 2,924 bytes and 220 update blocks.
- Passed 193 mandatory Thumb groups, 83 patcher tests and 55 tool tests. The 16-image/48-profile corpus produced 28 passes, 20 expected refusals and 8,471 grouped Thumb checks. Independent review included a RED/GREEN correction to an overly narrow Hard-Stop test condition.
- Previous release hashes, including 1.6.2, were reproduced exactly. All sources, tests, assembler and evidence remain local.
- The new main matrix covers OEM.13/1.5.2/1.6.2 only, with EHEX SHA256s for all three images. Read, action and Group0 tables compare those same images.
- Not flashed or hardware-tested; no commit or push.

[Contract](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/en/maint152-storage-diagnostics.md) · [Manifest](../../local/releases/MAINT1.5.2-Diagnose.json).

## MAINT 1.6.2: storage diagnostics and verified reset, 2026-10-24

- Cumulative release from positive 1.6.1; no new configuration parameters.
- Addressed UART0/UART1 64/04 storage diagnostics for master and slaves 0–21; FF and foreign addresses remain silent. Ten bytes, format01, LENGTH B014: parameter/SOC copy classes and comparison, stored lock values and cache flags. Direct flash reading without repair or writes.
- Targeted UART0/UART1 45/06 saves the original SOC/capacity record before reset: primary first, readback before writing backup, then a final comparison of both copies against the intended record. Success has no ACK; storage or verification failure returns RTN08 and prevents reset. UART1 still requires bit3=1; UART0 remains independent. FF neither saves nor resets. Original master on/off broadcasts remain.
- MNT04 remains 19 bytes; patch `01 06 02`, flags7E with new capability bits20/40, build ID `d17402111512af7c`. Older releases remain byte reproducible.
- Reuses the native serializer and existing IAP/UART buffers; no additional permanent RAM over 1.6.1. Automatic SOC save triggers and other reset sources retain OEM behavior.
- Passed 257 mandatory actual-Thumb groups, 72 patcher unit regressions, 53 tool regressions and the 16-input/48-profile corpus with expected outcomes and 7,292 Thumb checks. Checks cover failures at each storage stage, word interruptions in both SOC mirrors, native startup restore, all 22 addresses, stack/register/IRQ behavior and diagnostics without NVM writes. Independent code review and fragmented-ACK regressions were included.
- The local laboratory updater now uses one reset with bounded RFL probes instead of assuming a single 50 ms delay. It collects fragmented RFB responses completely and strictly requires WFB write acknowledgements. The separate OpenBMS updater was unchanged and still needs the documented host adaptation.
- Only offline verification: no flash, hardware timing/load evidence or measured flash-time guarantee.

[Contract and evidence limits](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/en/maint162-service-diagnostics.md) · [Manifest](../../local/releases/MAINT1.6.2-Service.json).

## MAINT 1.5.1/1.6.1 capability matrix, 2026-10-24

- No firmware change. The main capability matrix at this revision covered only the current 1.5.1/1.6.1 builds, across UART0/UART1/UART2, different bit3 polarity, positive-1.6.1 extended off and lock status, UART0 marker access and MNT04.
- Included all 87 parameters and 64 switch positions. The previous matrix was retained byte-for-byte as a historical reference. The local standard-library catalogue/renderer verifies exact release hashes and existing audit bindings; no new emulation or hardware access.

[Capability matrix and historical revisions](../docs/firmware/uart-write-capabilities.md).

## Flash, startup, UART and MAINT hook audit, 2026-10-23

- No firmware change. Passed 321 persistence checks, 51 startup scenarios, 60 UART/interrupt scenarios, 178+237 mandatory checks with passive hook ABI/stack monitoring, and four additional heater cases.
- Recorded primary-first mirror selection and native SOC block6 persistence; bounded I2C and unbounded hardware-status waits; watchdog liveness gating; unchanged UART0/UART2 ready-frame overwrite; protected MAINT UART1 reception; and unconditional interrupt enable in OEM flash primitives.
- No new hook ABI violation was found. Observed stack depths are not universal bounds.

[Validation methods and historical image limits](../docs/firmware/validation-methods-and-limits.md).

## MAINT 1.5.1/1.6.1: maintenance marker and identity over UART0, 2026-10-22

- New separate OEM16.06.13-based releases: 1.5.1-Power/RTC and 1.6.1-CUTOFF_POSITIVE. Older images are unchanged. 1.5.1 retains inverse bit3; 1.6.1 uses positive bits3/4.
- UART0 adds addressed 64/02 marker status, 64/00 with INFO C35A to clear the marker, and 64/03 firmware identity, at the local address 0–21, including slaves. FF and foreign addresses remain silent. No UART0 maintenance start or broadcast clear. UART0 host access still requires quiet master polling.
- Erases only the recognized active marker0; FFFFFFFF is idempotent. Readback precedes RTN00. Unknown marker values are left unchanged and return RTN05 without INFO; recognized erase or verification failures also return RTN05. UART1 permissions do not block UART0 reads or clearing. The individual pack lock is unchanged.
- MNT04: 19 bytes, three-part patch version, build ID at10, flags at18, LENGTH8026, identical on UART0/UART1. New image flag0x10 means UART0 marker/identity; flags12 for 1.5.1 and1E for 1.6.1 without Hard-Stop. MNT02/03 remain unchanged. Client and patcher support the new profiles.
- One additional UART0 parser wrapper; 1.6.1 chains the existing Cutoff wrapper. Reuses UART0 buffers, encoders and send paths, with no additional RAM bytes. Raw header, LENGTH and checksum hex characters are checked before OEM normalization.
- Structural UART0 recognition handles existing compiler arrangements of shared send tails; unknown code shapes remain rejected.
- Build IDs: 1.5.1 `96cb4859ef3c3f3b`, 1.6.1 `cecca6889e95d5c8`. Passed 178/237 mandatory checks, 59 patcher tests and 45 tool tests. Each 16-input/48-profile corpus matrix matched expectations: 8,201/7,052 Thumb checks. Hard-Stop combinations were checked.
- Additionally checked full UART0 45 chains, FF-on, nonhex input, RTN08 and marker/pack-lock independence. No parameter conversion or flashing.
- The existing OEM receive-buffer fix remains; UART1 still requires an inter-frame gap.

[Contract, operation and MNT04](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/en/maint-revision1-uart0-marker.md) · [Releases and hashes](releases/README.md) · [Evidence](../../local/builds/runs/patcher/Checks-UART0-Marker-2026-10-22/README.md).

## MAINT 1.5/1.6: included OEM UART1 receive-buffer fix verified, 2026-10-21

- The included fix protects a completely received UART1 frame against subsequent byte overwrites. OEM16.06.13 can replace a completed own-address query with foreign data before processing it; MAINT preserves and answers the completed query.
- Verified for MAINT1.5 Power/RTC build `d75a7b24cb6e8590`. This evidence does not automatically cover older 1.5 files.
- The protection is already present in that tested 1.5 build and inherited by both 1.6 variants, including CUTOFF_POSITIVE. This entry records existing behavior; no new build or version change.
- MAINT discards new bytes while its single receive buffer is occupied. An own-address query arriving after an unprocessed foreign frame can therefore be lost. No second receive buffer or pipelining.
- Adequate frame spacing remains necessary. Without the RX timeout, OEM and MAINT can concatenate a foreign response and an own-address query. UART1 timeout is nominally 104.17 ms at 9600 baud; a provisional 200 ms host gap after the complete response is suggested. No guaranteed main-loop latency bound or new electrical hardware evidence.
- Passed 228 counterexamples for OEM.13, the selected MAINT1.5 and both 1.6 builds, executing actual Thumb routines with modeled FIFO/timeout events.

[Operational effects, reproducible script and evidence](../../analysis/protocols/uart1-receive-gap-and-buffer-ownership.md).

## MAINT 1.6: additional positive permissions, 2026-10-21

- Separate image `CAN1101[V16.06.13_PN01_250607_MAINT_V1_6_CUTOFF_POSITIVE].ehex`.
- Bit3=1 permits UART1 power/RTC; bit4=1 enables extended off. No migration or conversion of stored parameters. Bits0/2/5 and bit5 lock-status semantics are unchanged.
- Opt-in `--positive-flags`, for 1.6 only. New image flag bit3/0x08; flags0E without Hard-Stop. MNT03/version1.6 remains unchanged; build ID `39e0c5d9ccf13396`.
- Three condition bytes plus build metadata change; size and RAM are unchanged. Original images remain available.
- Added mandatory checks for polarity, soft off without a latch, persistence, mode deactivation and unchanged older images. Clients and laboratory helpers were adapted. Passed 223 mandatory checks.
- The new image was verified offline only and was not flashed.

[Contract, hashes and reproducible build](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/en/maint16-positive-flags.md).

## UART write capability matrix, 2026-10-21

- No firmware change. The comparison covered OEM16.06.13, selected MAINT1.5 Power/RTC and MAINT1.6: all 87 parameters, 64 switch positions, service/control commands, gates and storage side effects. Older 1.5 builds without Power/RTC were excluded.
- UART1 still lacked 49, calibration, serial-number writes and CAN protocol selection. A1/P59 is distinct from 49/3B.
- A reusable local code catalogue and actual Thumb counterexamples preserved the mapping. Remaining short descriptions of 49 and the rounded-SOC counting floor were corrected.

[Matrix and historical revisions](../docs/firmware/uart-write-capabilities.md).

## SOC and persistence analysis, 2026-10-21

- No firmware change. Seventy-nine executed OEM16.06.13/MAINT1.6 CPU counterexamples covered coulomb counting, voltage rules, OVP/UVP, block6 restore and 49 capacity writes. No physical hardware or NVM dump was used.
- Ordinary A1 does not save block6; its capacity-adjustment branch saves only when rated and learned full capacities differ by at least 10 Ah. 49/3A and49/3B change live capacities without updating parameter fields P58/P59; A1/P59 does not set SOC.
- Another 24 CPU counterexamples established SOC-only normal discharge inhibition, rounded whole-percent thresholds, the counting floor at healthy minimum cell voltage and native charging recovery. Falsely low SOC alone does not imply inevitable later shutdown. Intermittent recharge waiting alone leaves the charge MOSFET closed without Hard-Stop.
- A local SHA-bound code profile preserves the function/RAM mapping, units, rules and reusable emulator fixtures.

[SOC, capacity and persistence](../../analysis/firmware/soc-capacity-and-persistence.md).

## OEM on/off analysis, 2026-10-18

- No vendor-firmware change. Logical off does not guarantee that both power paths are disconnected. Normal discharge inhibition includes precharge; charging recovery from 3 A can bypass it.
- Detected charging and eligible port-voltage wakeup clear off. On only clears the off bit; protection and shutdown causes still determine the outputs. Off alone does not determine CCL/DCL.
- Earlier blanket statements about precharge and undervoltage were corrected using 16.06.13 code and repeated synthetic OEM counterexamples. No new electrical measurements.

[Original on/off behavior](../../analysis/firmware/power-on-off.md).

## MAINT 1.6: UART0 error contract clarified, 2026-10-18

- Targeted 45 on/off returns explicit RTN08/LENGTH0000 without INFO for recognized storage or verification failures over UART0 too. Previous documentation mentioned UART1 only.
- Added 36 offline cases through the original ASCII response encoder, including primary/backup programming failure and final CRC errors at addresses0/1/11.
- A counterexample shows that failed off can already clear bit5 in RAM while both flash copies remain unlocked; the lock is absent after reset. Matching readback must not upgrade RTN08 to success.
- Internal foreign-address RTN05 in the old probe is not a wire response: UART0 remains silent.
- Added the persistent counterexample `tools/Analyse/probe_cutoff_uart0_errors.py`. No firmware change or flashing, and no real flash failures were induced.

[Evidence](../../local/builds/runs/patcher/Checks-UART0-Power-Errors-2026-10-18/README.md).

## MAINT 1.6: flash and hardware as master0, 2026-10-18

- The selected build `18daf61d8a93671d` was explicitly authorized for flashing to one development board: 223 blocks, 452 checksum-valid bootloader packets, and a data stream matching the image exactly.
- Hardware confirmed UART1 power/RTC gating, RTC set/read, reset, persistent pack lock, FF/foreign-address protection, A1 bit protection and old-parameter import.
- The lock survives disabling bit4 and reset; diagnostics and paths remained off for 70 s. Targeted on releases it persistently. CCL/DCL were0 during the lock and after reset, but already0 beforehand in this laboratory setup. No positive load path or 12-pack transition was demonstrated.
- All original parameters and both serial numbers were restored and compared at the end. Group0 FF: power/RTC denied, extended function disabled, individual lock released and marker off.
- Corrected the host helper: a 0.7 s reset read without RX synchronization had produced partial responses. Regression first RED, then GREEN; 16 tool tests. No firmware change.
- Added persistent `cutoff_lab.py` and `cutoff_audit.py` tools with baselines and raw data.
- Hardware scope: master0 without polling or slaves. Electrical gate measurements, real slave/master-broadcast/12-pack counterexamples and supply isolation remain open.

[Laboratory report](../../local/devices/lab/Patchtests/Packsperre-1.6/Labor-2026-10-18/README.md).

## MAINT 1.6: persistent pack lock, 2026-10-18

- Retains cumulative 1.5 functions; new explicit patcher selection `--maint-version 1.6`. CLI default remains1.5; the frozen Power/RTC build was reproduced byte-for-byte.
- Group0.bit4=0 enables extended off; bit5=0 reports the stored individual lock as read-only status. Known old FF parameters mean disabled/unlocked.
- Targeted 45-off sets and verifies the lock; targeted on clears it. Reset, master FF-on, disabling bit4 and old-parameter imports do not release it. Normal FF-off does not set an individual persistent lock. Master0 retains OEM broadcasting.
- Actual native charge/discharge MOSFET, limiter and precharge outputs are off. Recovery/wakeup are suppressed, while self-hold and diagnostics remain. No fake alarms.
- After native calculation, CCL is capped downward to remaining charge capability, including heater minimum, ramp and zero cases. DCL retains native counting.
- UART1-A1 now atomically protects bits2/3/5 with E3. UART0/UART2 and all save paths retain bit5 from an additional four-byte cache. No extra UART buffer; the existing sender is reused.
- Reuses the native parameter block, CRC and flash primitives. Raw primary is checked before erasing backup. Both copies load independently; damaged or inconsistent mirrors lock the pack without automatic default repair. On/off failures return RTN08.
- Targeted on also repairs inconsistent unlocked data. CCL ignores stale poll-mask bits outside0..SLAVES. Both review findings were demonstrated with RED/GREEN checks.
- MNT03 remains18 bytes, patch `01 06`; image flag bit2 identifies the pack lock. Flags06 without Hard-Stop,07 with it. No new runtime fields in64/03.
- Additional gate/NVM/startup ABIs currently support OEM16.06.11/.12/.13. 06.03/.04/.05 are intentionally rejected for1.6; existing1.5/Hard-Stop support remains.
- Release ID `18daf61d8a93671d`: 56,624 application bytes, 3,532 appendage bytes, 18 hooks, four RAM bytes and223 update blocks. Passed211 mandatory image checks, including47 pack-lock checks,37 patcher tests and14 tool tests.
- Full16-image/48-profile corpus:22 passes,26 expected refusals and6,740 Thumb checks. Additionally18 UART0 parser-chain cases at0/1/11 cover unicast,FF,foreign and invalid ADR.
- At this release-validation stage no ports were opened, no flash was performed, and no hardware/12-pack evidence was yet available. The separate same-day hardware entry records the later authorized bench test.

[Details](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/patcher/Packsperre-1.6.md) · [Releases](releases/README.md) · [Corpus matrix](../../local/builds/runs/patcher/Validation-Cutoff-Final-2026-10-18/README.md).

## Power/RTC with a shared gate, still MAINT 1.5, 2026-10-18

- UART1 ASCII45 supports on/off and local watchdog reset only. 4D/4E read/set RTC through the native driver, with strict calendar validation for2000..2099.
- Group0.bit3=1 denies power/RTC writes;0 permits them. Known FF old parameters remain denied; no migration. UART1-A1 may change neither bit2 nor bit3: atomic E3 rejection. Permission is granted through OEM UART0/UART2.
- The explicitly requested master on/off broadcast remains. Reset stays local without an ACK. Physical charge-path inhibition and suppressing charging wakeup are separate1.6 features.
- MNT03 remains18 bytes/patch1.5. Image flag bit1 signals Power/RTC support; bit0 remains Hard-Stop. Unicast only to the own address0–21; FF and foreign addresses remain silent.
- Strictly checks raw ADR before the OEM parser, preventing invalid hex characters from impersonating valid destination addresses through normalization. Reproduction and regression are retained.
- New structural role detection, original action/RTC-BCD probes and56 additional mandatory checks per MAINT output. Still four OEM hooks and existing UART1 buffers/sender; UART0 buffer unchanged, with eight bytes of temporary stack.
- Passed31 patcher tests,14 tool tests,48 expected corpus profiles and7,949 named Thumb checks. Selected build `d75a7b24cb6e8590` passed164 mandatory checks. No flashing.

[Release and manifest](releases/README.md) · [Implementation and contract](../../local/history/snapshots/mod-before-rebuild-2026-10-26/mod/docs/patcher/Power-RTC-1.5.md) · [Test matrix](../../local/builds/runs/patcher/Validation-Power-RTC-2026-10-18/README.md).

## Addressed pack identity, still MAINT 1.5, 2026-10-18

- 64/03 is available at the own address0–21, including slaves; MNT03/18 bytes is unchanged.
- 64/02 and maintenance start/stop remain master0-only. Foreign addresses, FF and slave maintenance remain silent, without IAP or parameter side effects.
- Extended the parameterized payload and mandatory self-tests of every MAINT image. Still four OEM hooks and existing buffers/parser/sender; no extra RAM structure.
- Report includes `build.addressed_info=true`; Hard-Stop-only remains without MAINT.
- Fixed reference build1.5 ID `297f9f2aa8402e9f`, with a separate minimal address gate. Client, laboratory tools, audit and complete monitor contract were updated.
- Passed26 patcher tests,103 reference tests,14 tool tests,48 expected corpus profiles and6,941 named Thumb checks. No hardware access or flashing.

## Directory structure and paths, 2026-10-18

- Original images were kept under `Original Firmware` and selected current images under `Patched Firmware`; firmware bytes and MAINT version1.5 were unchanged.
- No historical runtime dependency under the patcher; required project components remained in `seplos`. Nine old images were explicitly retained under `tests/fixtures/legacy`.
- Independent clients, analysis/laboratory tools, fixed emulator and reference regressions were placed in the sibling `../Tools` directory. Existing analysis/laboratory entry points remained usable through relative links; no duplicate tool sources.
- Technical knowledge and version texts were placed under `Analyse/Patches`, complete hardware evidence under `Labor-Platine/Patchtests`, and the current monitor contract directly under the patcher.
- A complete SHA-verified pre-change backup covered622 files, including all seven ZIPs. The manufacturer update instructions were additionally extracted; no unpacked archive of old patch directories was required.
- Corpus checker rejects missing or empty input groups. Post-move checks passed25 patcher tests,99 reference tests and48 expected profile results.
- Final review corrected existing MNT03 gaps in laboratory helpers: identity comparison includes extra fields; audit checks18 bytes, ID at9 and image flags. MNT02 remains readable. Monitor/wait scripts find their helper independently of the working directory. Seven new offline integration tests passed.
- No hardware access or flashing.

## Tool 1.0.0, 2026-10-18

- Standalone offline CLI, virtual-environment setup, pinned packages, persistent sources, emulators, structured evidence and instructions.
- Automatic role recognition, complete code/call/ROM contracts, and actual OEM RAM/version/serializer/UART/DIP probes. No version-address lookup table.
- Builds cumulative MAINT1.5 functions directly as an appendage; no patch chain is needed.
- Optionally adds Hard-Stop or applies only the one-byte Hard-Stop change. Detects and retains existing OEM SP80 behavior.
- Retains version1.5 as explicitly requested, now MNT03/18 bytes with a Hard-Stop image flag in64/03. Unknown OEM revision is marked FF.
- Mandatory bounded subprocess/Thumb tests before output. Does not overwrite the input or existing target directories. Publishes EHEX atomically.
- Conservatively rejects unknown structures and already modified MAINT bases. 04.06 is suitable only for Hard-Stop-only because TX170<175.
- Matrix covers all16 available images in three profiles, including intended refusals. Evidence under `Validation-2026-10-18-Final`.
- No flashing, commit or push.
