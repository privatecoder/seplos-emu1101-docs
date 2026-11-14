# EMU1101-EXT firmware and patcher changelog

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT (EMU1101 Extended Firmware). Custom firmware for Seplos BMS 2.0 (EMU1101, hardware V16).

Versioned Light releases start at 1.5.3; versioned Full releases start at 1.6.3. Earlier builds use versionless development identifiers. Development builds have unique dated identifiers without semantic versions. These identifiers track functional development and evidence; they do not assert a new binary identity for archived images. Current EXT05 identities and checksums are bound by the [release metadata](releases/README.md). The published patcher supports only Light 1.5.4, Light 1.5.5, Full 1.6.4 and Full 1.6.5.

## Versioned functional-contract baselines, 2026-11-13

- Light 1.5.3 and Full 1.6.3 are the first versioned baselines. Their standard permission semantics use 1=enabled and 0=denied; the permission reversal belongs only to development entries.
- Functional descriptions and comparisons begin at those baselines. Shared history/calibration/persisted-capacity/live-energy reads are available from Light 1.5.4+ / Full 1.6.4+; atomic scheduler cleanup is available from Light 1.5.5+ / Full 1.6.5+.
- Group0.bit4 is an ordinary writable reserved bit in Light; extended-off meaning requires Full capability04. The integration contract distinguishes writability from capability.
- Exact four-profile EXT05 release identities and firmware execution paths remain unchanged. Development history, original image bindings and historical tool details remain separately preserved.

## development-build-2026-11-13-01: EXT identity and profile API

- The published family is EMU1101-EXT (EMU1101 Extended Firmware), with Light 1.5.x and Full 1.6.x names. The four supported profiles are Light 1.5.4, Light 1.5.5, Full 1.6.4 and Full 1.6.5; select one explicitly with `--ext-version` or API `ext_version`.
- Rebuilt profiles identify themselves with ASCII EXT (`45 58 54`) and format 05. The four existing semantic versions are unchanged. They retain the existing 21-byte layout, image flags and capability mask 000F. The current client rejects archived signatures/formats; the permission rule is fixed throughout the versioned releases.
- All four rebuilt images passed their mandatory native suites: 251/333/257/339 groups for Light 1.5.4/Full 1.6.4/Light 1.5.5/Full 1.6.5. [Release metadata](releases/README.md) binds their new build IDs and EHEX/application hashes. Archived raw identities and hardware evidence retain their exact original inputs in local history.
- Independent rebuilds reproduce all four complete images byte-identically. The four 16-input/32-run corpus matrices pass: 128 runs, 60 successful builds, 68 expected refusals and 25,098 grouped native checks. A byte comparison against each corresponding pre-rename custom image confirms that only the ASCII signature and derived build ID change.
- The complete patcher regression passes 154 tests with zero failures/errors. Device, analysis, knowledge and shared-tool suites pass 125/22/15/26 tests. No hardware access or flashing. Permissions, parameter layouts, persistence and the atomic .5 scheduler fix retain their documented behavior.

## EMU1101-EXT Light 1.5.5 / Full 1.6.5: atomic scheduler cleanup, 2026-11-12

- Fix the controlled native counterexample in which main-loop A8 cleanup overwrites measurement enable set by the timer wake path. The helper saves/restores the incoming PRIMASK and protects a fresh byte read/modify/write. Its masked interval contains six instructions and no peripheral or flash work; this is an instruction bound, not measured physical latency.
- Preserve the independent OEM skip path. Source-derived CFG/input proofs guard a BL plus a separate continuation branch and refuse alternative entry into displaced cleanup. One additional hook gives six Light/22 Full hooks. The helper adds 24 application bytes and temporarily uses eight stack bytes; persistent RAM remains zero/four bytes.
- Six mandatory groups cover 2,048 flag/mask/CV/ABI cases, 26 native wake injections at 13 boundaries, exact mask restoration, native coalesced/new-pending slow ticks and an OEM negative control. Mutations removing/reordering exclusion, changing mask restoration or altering skip/continuation fail their intended assertions. Maskable-IRQ model evidence does not establish physical occurrence, measured latency or absence of other races.
- Both 16-input/32-run corpus matrices passed: 30 builds, 34 expected refusals and 12,639 grouped native checks. Independent rebuilds reproduced the tested images. OEM .13-based builds pass 257/339 mandatory groups. Capability mask 000F, permissions, persistence and parameter layouts remain unchanged; no parameter migration is required. Light 1.5.4/Full 1.6.4 reference builders remain available.
- No current profile was flashed or hardware-tested. [Release metadata](releases/README.md) binds the exact current identities and hashes.

## Validation hardening for EMU1101-EXT Light 1.5.4 / Full 1.6.4, 2026-11-12

- Mandatory native tests cover clock selection/readback, UART configurations/dividers, IRQ routing/priorities, timer loads, watchdog modes/progress and CAN selector bit timing. Full additionally exercises signed fast-current thresholds/gates and persistent Off without rearming outputs, including intermediate GPIO writes.
- Opt-in interrupt tests execute timer/measurement/protection and comparator handlers during diagnostics/history/checkpoint work, with concurrent UART0 reception and deferred native parsing. They check PRIMASK deferral, nesting, exception frames and callee-saved registers. Synthetic ADC inputs, modeled TX boundaries and controlled schedules remain explicit limits.
- A UART1 time model checks divider-driven timeouts, FIFO limits and merged/separated frames under both conflicting manual interpretations of RX threshold assertion. Mutations and omission checks validate the assertions and publication guards.
- Native A8 characterization demonstrates stale-store wake measurement-enable loss under synthetic call states. Ordered/coalescing controls distinguish mechanisms. Complete runtime reachability and physical occurrence remain unproven. [Evidence limits](../../analysis/firmware/startup-clock-timers.md#backlog-flag-coalescing-and-a-controlled-lost-update).
- Strengthened suites passed 251/333 groups without payload changes. Both corpus matrices retained 30 builds/34 refusals and 12,459 grouped checks; final hardware/UART/IRQ models were replayed against successful outputs. The patcher regression passed 144 tests. No hardware access or flashing.

## EMU1101-EXT Light 1.5.4 / Full 1.6.4: addressed history and remote diagnostics, 2026-11-01

- Both profiles add addressed UART1 history 4B with the original 97-byte record layout. One request reads one entry; empty rings return RTN00 with no INFO and EEPROM read failures return RTN08. A failed read restores the shared cursor. UART0 history remains unchanged; downloads are not atomic ring snapshots.
- UART0/UART1 64/05 reads active calibration (72 bytes), stored primary (58) or backup (58), including signed current zeros, current samples and record validity. Calibration writes remain on their original interfaces.
- UART0/UART1 64/06 reads persisted capacity/SOC mirrors, native acceptance/boot preference and coherent live capacities/SOC plus u32 charged/discharged energy (68 bytes), without repair or saving. Existing 42 energy encoding is unchanged: threshold 65000 raw (6500.0 kWh), fallback 6500 raw (650.0 kWh).
- New reads require the own address 0–21; foreign/FF remain silent. No new permission or maintenance mode is needed. UART0 master-polling ownership still applies.
- Format 05 adds a big-endian capability word 000F to the identity/image-flag layout: 21 bytes, LENGTH 402A. Current releases use the EXT ASCII signature. Existing 64/02 and ten-byte 64/04 remain unchanged. Archived evidence retains the original raw signatures and identities.
- No additional OEM hook sites or static RAM: five Light/21 Full hooks, zero/four bytes. Permission rules, Full persistent lock, verified reset checkpoint and configurable hard stop remain. No parameter conversion.
- Original release validation passed 214/293 mandatory groups and reproduced complete images. The 64-run corpus had 30 builds/34 refusals and 11,313 grouped checks. Patcher/device/analysis regressions passed 118/85/20 tests. UART1 RX injection during modeled EEPROM transfer was checked; full polling/timer/protection coexistence, physical I2C and electrical behavior remained untested. No hardware access or flashing.

[Wire contract](../docs/firmware/remote-diagnostics.md) · [Capability matrix](../docs/firmware/uart-write-capabilities.md)

## Connection and topology documentation, 2026-10-26

- No firmware change. Distinguish manufacturer-specified PC/FSU banks without a master from conditional direct-UART0 inverter use; document bus ownership, CAN profiles, monitoring paths and maintenance prerequisites.
- UART1-4F responds locally on slaves; master alias 02 can collide with pack 2. System commands 60–63 are master-only at 02/12.
- Native replay identifies the legacy UART0 FC03-like CRC read in 16.04.06: two-byte byte count and response builder `0x1474`. It is absent from the next available build, 16.06.03; register semantics remain incomplete.
- UART0 initializes at 9600 only in 04.06 and at 19200 in later examined images; UART1 initializes at 9600 throughout. The 04.06 bootloader baud rate remains unverified. No hardware test or flashing.

[Connection guide](../../analysis/hardware/ports-and-topologies.md)

## EMU1101-EXT Light 1.5.3: first versioned Light release, 2026-10-24

- Establish the cumulative Light baseline: addressed UART1 parameter/serial access, maintenance services, UART0 marker status/clear and firmware identity, UART1 power/RTC access control, and ten-byte UART0/UART1 64/04 storage diagnostics.
- Group0.bit3=1 permits UART1 power/RTC; 0 denies it. This is the standard rule for every versioned Light and Full release. UART0 remains independent, UART1-4D remains unrestricted and UART1-A1 protects bit3.
- Five guarded OEM hook sites and zero additional persistent RAM. Bits4/5 remain reserved. There is no persistent pack lock, Full CCL clamp or SOC checkpoint before reset. Storage diagnostic reads require no permission.
- The identity layout has 19 bytes/LENGTH 8026, image flags 3A or 3B with static hard stop. Flag08 records the standard permission semantics and is set in every versioned release; lock capability04 is absent. Current clients require EXT05.
- Passed 194 mandatory groups, 105 patcher tests and 60 tool tests. Corpus: 28 passes, 20 expected refusals, 8,489 grouped checks. Publisher suite selection is bound to the requested profile. Validation was offline; no flashing or hardware test.

## development-build-2026-10-24-03: Light permission semantics

- Replace the earlier inverse UART1 power/RTC gate with Group0.bit3=1 permitting access and 0 denying it. This development step precedes the first versioned Light baseline; it is not a change between versioned releases.
- One condition byte and identity metadata change; the five OEM hook sites, hook bytes and persistent RAM allocation remain unchanged. UART0 behavior, unrestricted UART1 RTC reads and A1 protection of bit3 remain unchanged. Stored parameter bytes are not converted.
- Image flag08 records the 1=enabled semantics used throughout the subsequent versioned releases.

## EMU1101-EXT Full 1.6.3: first versioned Full release, 2026-10-24

- Establish the cumulative Full baseline: addressed access and maintenance services, UART1 power/RTC access control, UART0 marker services, storage diagnostics, persistent individual pack lock, verified SOC checkpoint before planned reset and configurable recharge-waiting hard stop.
- Group0.bits6/7 select soft stop (`00`), hard stop (`40`) or inherited image default (`80/C0`). Existing FF inherits soft in the published soft-default profile. Other older bit 7=0 values already select explicitly; no NVM migration.
- UI writes `(fresh_group0 & 0x3f) | (enabled ? 0x40 : 0)` through UART0/UART2 or permitted UART1-A1, retaining bits 0–5 and existing protections.
- One additional hook before native Event6 TST/BNE selects mask 71/73: 21 sites, 36 extra code bytes and the existing four-byte lock cache. Native temperature/OVP/recovery and persistent pack-lock priorities remain.
- Group5.bit1 must enable recharge waiting. Discharge above 10 A for about 10 s can still trigger native recovery. This is separate from general pack off.
- Image flag 80 identifies configurability; bit 0 then identifies the inherited default. Flags FE mean soft default, FF hard default. Read 47/Group0 and identity together for current state.
- Passed 273 mandatory groups including all 256×256 Group0/Event6 pairs, 94 patcher tests and 60 tool tests. Corpus: 22 passes/26 refusals, 7,484 grouped checks. The native .11 recovery-counter address is derived from accesses. Offline only; no flashing.

## development-build-2026-10-24-01: Light storage diagnostics

- Versionless Light development build adds addressed UART0/UART1 64/04 at addresses 0–21, including slaves; foreign/FF remain silent and no permission is required.
- Format 01 is ten bytes/LENGTH B014. It reads parameter/SOC record classes and comparisons directly from flash without repair or writes. FF/FF lock fields and cache 00 mean unavailable; bit 5 remains reserved.
- Five hooks, 472 additional code bytes, no extra persistent RAM. UART1 power still uses inverse bit 3=0 permission; no SOC checkpoint before reset or new parameters. Application 56,016 bytes, appendix 2,924 bytes, 220 update blocks.
- Passed 193 mandatory groups, 83 patcher tests, 55 tool tests and 8,471 grouped corpus checks with 28 passes/20 expected refusals. A hard-stop test condition was corrected with a failing/passing regression. Offline only; no hardware test.

## development-build-2026-10-24-02: Full storage diagnostics and verified reset

- Cumulative from development-build-2026-10-22-02 without new parameters. Addressed UART0/UART1 ten-byte 64/04 reads parameter/SOC classes, comparisons, stored locks and cache flags without repair/writes; foreign/FF remain silent.
- Targeted 45/06 serializes native SOC/capacity, writes primary, verifies before backup, then compares both against intended data. Success has no ACK. Save/verification failure returns RTN08 and prevents reset. UART1 requires bit 3=1; UART0 remains independent. FF neither checkpoints nor resets.
- Image flags 20/40 identify diagnostics/checkpoint capabilities. Reuses native serializer and IAP/UART buffers; no additional persistent RAM over development-build-2026-10-22-02. Automatic saves and other reset sources retain OEM behavior.
- Passed 257 mandatory groups, 72 patcher tests, 53 tool tests and 7,292 grouped corpus checks. Cases cover every storage stage, interrupted words in both mirrors, native startup restore, 22 addresses, ABI/IRQ and read-only diagnostics.
- The local updater uses one reset, bounded RFL probes, complete fragmented RFB collection and WFB-only write ACKs. The separate OpenBMS updater was unchanged. Offline only; physical flash timing/load remains unmeasured.

## Capability matrix for development-build-2026-10-22-01 and development-build-2026-10-22-02, 2026-10-24

- No firmware change. Compared all 87 parameters and 64 switch positions over UART0/UART1/UART2, inverse Light/positive Full bit 3 polarity, extended off, lock status and UART0 marker access. The catalogue bound exact archived inputs and audit evidence; no new hardware or emulation.

## Flash, startup, UART and hook audit, 2026-10-23

- No firmware change. Passed 321 persistence checks, 51 startup scenarios, 60 UART/interrupt scenarios, 178+237 mandatory groups with passive ABI/stack monitoring and four heater cases.
- Verified primary-first mirror selection, native SOC block 6 persistence, bounded I2C versus unbounded hardware waits, watchdog liveness gating, unchanged OEM UART0/UART2 ready-frame overwrite, protected UART1 reception and unconditional interrupt enable in OEM flash primitives. Observed stack depths are not universal bounds.

[Validation methods and image limits](../docs/firmware/validation-methods-and-limits.md)

## development-build-2026-10-22-02: Full UART0 maintenance marker and identity

- Adds addressed UART0 64/02 marker status, 64/00 with INFO C35A marker clear and 64/03 identity at 0–21, including slaves. No UART0 maintenance start or broadcast clear; foreign/FF remain silent. UART0 access requires quiet master polling.
- Only recognized marker 0 is erased and verified; erased FFFFFFFF is idempotent. Unknown marker content is preserved with RTN05; erase/verification failures also return RTN05. UART1 permissions do not gate UART0 reads/clear. The pack lock remains independent.
- Chains one UART0 parser wrapper with the Full power wrapper, retaining existing buffers/sender and 1=enabled semantics for bits3/4. The three-part identity layout has 19 bytes, ID offset 10 and flags offset 18; flag 10 identifies UART0 marker/identity. No parameter conversion or extra persistent RAM.
- Passed 237 mandatory groups; combined Light/Full regressions passed 59 patcher/45 tool tests. Full corpus counted 7,052 grouped checks. Additional cases cover UART0 FF-on, malformed hex, RTN08 and marker/lock independence. Offline only; no flashing.

## development-build-2026-10-22-01: Light UART0 marker and identity

- Versionless Light development build independently adds the addressed UART0 marker/status/clear/identity contract described above, retaining inverse UART1 power permission bit 3=0.
- Five hooks, no extra persistent RAM. Raw header/LENGTH/checksum hex characters are checked before OEM normalization. Unknown marker content remains unchanged. No UART0 maintenance start or pack lock.
- Passed 178 mandatory groups and 8,201 grouped corpus checks; shared patcher/tool regressions passed 59/45. Hard-stop combinations and both UART0/UART1 error paths were checked. Offline only; no flashing.

## UART1 receive-buffer evidence, 2026-10-21

- No new firmware build. Native replay covers development-build-2026-10-18-07, development-build-2026-10-18-08 and development-build-2026-10-21-01 against OEM.13.
- The custom receive guard preserves a completed query while dropping new bytes until processing finishes. OEM can overwrite that query. A completed foreign frame can conversely cause a later own query to be dropped; no second buffer or pipelining exists.
- Without timeout both OEM and custom firmware can concatenate frames. Nominal timeout is 104.17 ms at 9600 baud; use a provisional 200 ms host gap after the complete response. No worst-case scheduler or electrical guarantee. Passed 228 native counterexamples.

[Receive-gap evidence](../../analysis/protocols/uart1-receive-gap-and-buffer-ownership.md)

## development-build-2026-10-21-01: Full permission semantics

- Group0.bit3=1 permits UART1 power/RTC and bit 4=1 enables extended off. No stored-parameter conversion. Bit 5 lock-status semantics and bits 0/2 protections remain.
- Three conditional instruction bytes plus identity metadata change relative to development-build-2026-10-18-08; size and RAM remain unchanged. Image flag08 records the 1=enabled semantics; flags are0E without hard stop. These semantics are the baseline of the subsequent versioned Full releases.
- Mandatory polarity, soft-off, persistence, deactivation and older-image controls pass 223 groups. Offline verification only; no flashing.

## UART write capability matrix, 2026-10-21

- No firmware change. Compared OEM.13, development-build-2026-10-18-07 and development-build-2026-10-18-08 across 87 parameters, 64 switch positions, service/control gates and storage effects.
- UART1 lacks 49, calibration writes, serial writes and CAN selection. A1/P59 differs from 49/3B. Catalogue/code counterexamples preserve the exact input bindings.

## SOC and persistence analysis, 2026-10-21

- No firmware change. 79 native CPU counterexamples cover OEM.13/development-build-2026-10-18-08 coulomb counting, voltage rules, OVP/UVP, block 6 restore and 49 writes. 24 additional cases cover SOC-only discharge inhibition, whole-percent thresholds, healthy-cell counting floor and charging recovery.
- Ordinary A1 does not save block 6; capacity adjustment saves only when rated/learned full capacities differ by at least 10 Ah. 49/3A and 49/3B change live capacities without updating P58/P59; A1/P59 does not set SOC. No hardware/NVM dump evidence.

[SOC and persistence](../../analysis/firmware/soc-capacity-and-persistence.md)

## UART0 storage-error contract for development-build-2026-10-18-08, 2026-10-18

- No firmware change. Targeted 45 on/off reports RTN08 with LENGTH 0000 and no INFO for recognized save/verification failures on UART0 as well as UART1. 36 offline cases cover primary/backup programming failure, final CRC failure and addresses 0/1/11 through the original response encoder.
- A failed off may already clear RAM bit 5 while both flash copies remain unlocked; reset then loses the lock. Matching readback must not upgrade RTN08 to success. Foreign UART0 requests stay silent; internal probe RTN05 is not a transmitted response. No real flash fault was induced.

## Isolated-master hardware evidence for development-build-2026-10-18-08, 2026-10-18

- Explicitly authorized bench programming transferred 223 blocks in 452 checksum-valid packets matching the archived image. UART1 gates, RTC read/set, reset, persistent lock, FF/foreign protection, A1 protections and old-parameter import were checked.
- The lock survived 70 s, disabled bit 4 and reset; targeted on released it. CCL/DCL were 0 during/after lock but already 0 beforehand. No loaded electrical gate test, polling/slaves, 12-pack transition or supply-isolation proof. Original parameters/SNs were restored.
- A reset-helper partial-response defect received a 16-test regression. Hardware evidence applies only to this exact archived build and isolated-master 0 conditions; it does not identify a current EXT05 image.

## development-build-2026-10-18-08: inverse-polarity Full persistent pack lock

- Versionless Full development build retains cumulative Light functions. Bit 4=0 enables extended off; bit 5=0 reports the stored individual lock. Known FF means disabled/unlocked. Targeted 45-off sets/verifies the lock; on clears it. Reset, FF-on, disabled bit 4 and old parameter import do not release it; ordinary FF-off does not set it.
- Native charge/discharge MOSFET, limiter and precharge requests are off. Recovery/wakeup are suppressed while self-hold/diagnostics remain. No synthetic alarms. CCL is capped downward after native calculation, including heater/ramp/zero cases; DCL retains native counting.
- UART1-A1 atomically protects bits 2/3/5. UART0/UART2 and saves preserve bit 5 using a four-byte cache. Primary data is checked before backup erase. Damaged/inconsistent mirrors lock without automatic repair. On/off save failures return RTN08, including UART0; matching readback must not turn RTN08 into success.
- Targeted on repairs inconsistent unlocked data. CCL ignores poll-mask bits outside 0..SLAVES. Dedicated failing/passing counterexamples cover these cases.
- Native gate/NVM/startup contracts support OEM.11/.12/.13; earlier gate ABIs are refused. 18 hooks, four RAM bytes, 56,624 application bytes, 3,532 appendix bytes, 223 blocks. Passed 211 mandatory groups including 47 lock checks, 37 patcher tests, 14 tool tests and 6,740 corpus checks. 18 UART0 parser-chain cases and 36 UART0 error/encoder cases supplement them.

## development-build-2026-10-18-07: Light inverse power/RTC gate

- Adds addressed UART1 ASCII 45 on/off/local watchdog reset, 4D RTC read and 4E RTC write with 2000–2099 calendar validation. Uses original action/RTC paths and existing UART1 buffers/sender.
- Group0.bit3=0 permits writes; 1 denies them. Known FF remains denied. UART1-A1 changes to bits 2/3 cause atomic E3; UART0/UART2 configure permissions. RTC reading remains free. Master on/off broadcast remains; reset is local without ACK.
- Strict raw-address validation prevents OEM normalization from impersonating an own address. Existing receive ownership protects completed frames. Four hooks, no extra persistent RAM, eight temporary stack bytes.
- Passed 164 mandatory groups, 31 patcher tests, 14 tool tests and 7,949 named corpus checks. No hardware access or flashing at this stage.

## development-build-2026-10-18-06: Light addressed pack identity

- Identity 64/03 responds at the own address 0–21, including slaves. Marker/status/start/stop remain master 0-only. Foreign/FF and slave maintenance stay silent without IAP/parameter effects.
- Four hooks and existing buffers/parser/sender; no new RAM structure. Structural address guard and mandatory tests cover every generated development image. Passed 26 patcher tests, 103 reference tests, 14 tool tests and 6,941 corpus checks. No flashing.

## Standalone patcher Tool 1.0.0, 2026-10-18

- Builds cumulative functions directly from supported OEM inputs without a historical patch chain. Guarded role/code/RAM/serializer/DIP contracts, mandatory bounded native subprocess tests and atomic output refuse unknown structures and already modified inputs.
- Includes an offline CLI, pinned environment, sources, emulators and structured reports. Recognizes OEM SP80 hard stop. Standalone hard-stop was an early tool feature; it is absent from the current published CLI. Unknown declared OEM revision remains FF.
- The 16-input/three-development-profile corpus checks intended builds/refusals. No hardware access or flashing.

## Offline source layout and integrity checks, 2026-10-18

- No firmware change. Source/input relocation preserved firmware bytes. Corpus validation refuses absent/empty input groups; 25 patcher tests, 99 reference tests and 48 expected profile outcomes passed.
- Identity verification checks exact field offsets/flags and optional metadata rather than comparing only the original prefix. Monitor/helper lookup is independent of the current directory. Seven new offline integration tests passed.

## development-build-2026-10-18-05: Light master identity with image flags

- Adds a distinct immutable hard-stop image flag to the master-only identity response using existing padding. Identity contains 18 decoded bytes/LENGTH A024. Runtime marker remains in 64/02.
- Four-hook generated appendix uses 54,512 application bytes and 214 blocks. 99 retained identity/reference tests pass. No new hardware evidence.

## development-build-2026-10-18-04: Light independent access permissions

- Group0.bit0 permits UART1-A1 and bit 2 permits UART1 maintenance start. Reads remain free; stop remains possible after start permission is denied. UART1 cannot modify bit 2; unauthorized writes return atomic E3 before validation/IAP. UART0/UART2 configure permissions. Clearing bit 0 can self-lock UART1 writing.
- Two hooks plus 72 appendix bytes reuse existing buffers/state/storage. 54,512 application bytes, 214 blocks. Known FF permits both services without parameter migration.
- Passed 94 firmware/client/build checks plus four recovery injections; all 256 Group0 values and native UART0/UART2 serializers/loaders were checked. Prior 76/25 checks remain passing.
- One development board was flashed and checked as master, then as real slave 1 without another flash. Permission/self-lock/unlock, persistence, marker start/stop and 21 silent malformed/foreign cases passed. Original parameters/SNs were restored; marker off. UART2 was emulated; multi-board/gateway behavior remains unproven.

## development-build-2026-10-18-03: Light split maintenance and identity responses

- Separates firmware identity 64/03 from five-byte marker/slave-count 64/02 and start/stop ACKs. Unknown marker values are readable but cannot produce successful maintenance switching.
- Replaces only the reserved 336-byte maintenance block without growth: 54,440 application bytes, 214 blocks. Parameter, UART0/UART2, DIP, RX and sender paths remain unchanged. Passed 76 new checks plus 51 parameter, 56 identity and 25 maintenance checks. Not separately flashed.

## UART0 bus-ownership and UART1 service boundary, 2026-10-18

- No firmware change. Maintenance frees the shared UART0 update bus even when updating a slave. UART1 parameter/serial queries need no maintenance mode on the queried slave. The cumulative image provides its services together rather than requiring a chain of installed patches.

## development-build-2026-10-18-02: Light addressed serial identity reads

- Adds addressed UART1 binary A2/A4 with LEN 0 requests and 30 raw-byte String1/Battery_SN and String2/BMS_SN replies. Same image supports master/slaves. No serial writes or ASCII-A2/A4 extension; no identity is rewritten.
- One hook and 60 appendix bytes; no new persistent RAM/IAP. 54,440 application bytes, 214 blocks. Passed 56 identity, 51 parameter and 25 maintenance checks.
- Single-board master/slave bench checks cover reads and unchanged parameters/serials. Maintenance remains necessary for shared UART0 update ownership, not UART1 parameter/serial queries. No complete multi-board/gateway proof.

## Parameter-service identity boundary, 2026-10-18

- No firmware change. The parameter read service does not read String1/String2. The OEM Modbus path exposes only the master's 22-byte String1 prefix. Separate addressed serial services are introduced by development-build-2026-10-18-02.

## development-build-2026-10-18-01: Light addressed parameter read/write

- Adds UART1 `55 ADR CMD LEN DATA CRC AA`: 47 reads and A1 writes the local parameter block, at 9600 8N1. Strict unicast 0–21; foreign/FF stay silent. Master mode and UART0 polling need not change.
- Reuses UART1 buffers/sender/direction control. Validates complete framing/CRC/length before processing, preserves receive ownership and discards overflow until a frame boundary. Switches update only after native validation. P58/full-capacity and possible SOC effects remain OEM.
- Adds 696 application bytes, 214 blocks. Passed 50 new offline tests plus 25 maintenance tests with actual Cortex-M0 execution and modeled peripherals.
- One board was flashed and tested as master with UART0 polling and as slave 1: reads, writes, negative frames, readback and reset persistence passed. Original parameters restored, marker off. No gateway, real second slave, CAN-during-IAP, power-loss or interrupted-flash proof.

## development-build-2026-10-13-01: Light maintenance identity and marker validation

- Adds a master-only firmware identity query 64/03 with native OEM version, development identity and build identifier. Marker/status/start/stop remain available. Device identity and serials remain unchanged.
- Start/stop accept only erased FFFFFFFF or active 00000000 markers; unknown/partial values return RTN05 without erase. DIP still treats every non-erased marker as active.
- 592 appendix bytes, 211 blocks. Builder guards aligned hooks after metadata, absent relocations and image-derived identity. Single-board bench verified identity, status, start/stop, wrong token and reset persistence. Unknown marker content was not physically tested.

## development-build-2026-10-12-01: Light persistent maintenance service

- Adds master 0-only UART1 ASCII 64 status(INFO 02), start(01 C3 5A) and stop(00 C3 5A).
- Persistent marker at 0x23000: erased FFFFFFFF is off; DIP treats every other word as active. Native IAP sets/erases it. The DIP hook forces effective slave count 0, permitting ordinary UART0 parameter/update access without physical DIP changes; stop restores configured slave count on the next DIP tick.
- 488 appendix bytes, 211 blocks. One-board bench checks cover startup, status, start/stop, UART0 responses, polling stop/resume with DIP 5 and marker persistence through reset. Next-day checks cover reflash/power interruption. No original semantic firmware version was queryable; no fabricated 1.0 release is assigned. Multi-pack/gateway behavior remained unproven.

## OEM on/off analysis, 2026-10-18

- No firmware change. Logical off does not guarantee both power paths are disconnected. Precharge and charging recovery matter; detected charging/eligible port-voltage wake can clear off. On clears only the off bit, while protection/shutdown causes still govern outputs. Off alone does not determine CCL/DCL.

[Original on/off behavior](../../analysis/firmware/power-on-off.md)
