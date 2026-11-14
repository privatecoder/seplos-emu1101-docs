# EMU1101-EXT Light and Full version comparison

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Custom firmware for Seplos BMS 2.0 (EMU1101, hardware V16).

Function availability starts at **Light 1.5.3+** and **Full 1.6.3+**. Both
branches use Group0.bit3=1 to permit UART1 power/RTC and 0 to deny it.
Differences within the versioned releases add remote reads in `.4` and atomic
scheduler cleanup in `.5`, early master polling in `.6`, and configurable downward CCL in Full `.7`; the Full baseline already includes persistent lock,
verified reset checkpointing and configurable hard stop.

The patcher builds Light 1.5.4/1.5.5/1.5.6 and Full 1.6.4/1.6.5/1.6.6/1.6.7. The
[input manifest](ext-version-comparison-inputs.json) and
[release metadata](../../firmware/releases/README.md) bind those seven exact
EXT05 images. Tables compare the versioned contracts, using the published soft
static/inherited hard-stop defaults. “Own” means the local address 0–21,
including slaves; ordinary DIP addresses are 0–15. “Master” means address 0.
Requests are valid complete frames, and `64/05` denotes command 64 with INFO 05.

`Group0` is writable configuration/status. Immutable image flags in `64/03`
and the EXT05 capability mask are separate fields; equal bit numbers do
not imply equal meanings.

## Full: available from 1.6.3

| Same feature/request/state | Full 1.6.3 | Full 1.6.4 | Full 1.6.5 | Full 1.6.6 | Full 1.6.7 |
|---|---|---|---|---|---|
| UART1 power/RTC permission, Group0.bit3 | 1 allows, 0 denies | Same | Same | Same | Same |
| Extended off, bit4; lock status, bit5 | 1 enables; 0 means locked | Same | Same | Same | Same |
| Targeted off can persist an individual lock | Yes | Same | Same | Same | Same |
| Group0.bits6/7 select hard stop | Yes | Same | Same | Same | Same |
| UART0 identity/status/clear, own address | Supported | Same | Same | Same | Same |
| UART1 status/start/clear | Master only | Same | Same | Same | Same |
| Both ports `64/04`, own address | 10 bytes, lock/cache fields | Same | Same | Same | Same |
| Targeted `45/06` saves and verifies SOC before reset | Yes | Same | Same | Same | Same |
| `64/03` identity layout | 19-byte layout | **EXT05 / 21 bytes** | Same layout | Same | Same |
| Both ports `64/05`, own address | Absent | **Calibration pages** | Same | Same | Same |
| Both ports `64/06`, own address | Absent | **68-byte SOC/energy read** | Same | Same | Same |
| UART1 `4B`, own address | RTN04 | **History read** | Same | Same | Same |
| Capability mask in `64/03` | Not present | **`000F`** | Same | Same | **`001F`** |
| Reproduced scheduler wake-enable loss prevented | No | No | **Yes** | Same | Same |
| Validated early poll completion | No | No | No | **Yes** | Same |
| Downward CCL step, A per online pack/update | 1 | 1 | 1 | 1 | **1–20, default 1** |
| Separate EXT read/set, `64/07` / `64/08` | Absent | Absent | Absent | Absent | **Present; effective on master** |

## Light: available from 1.5.3

| Same feature/request/state | Light 1.5.3 | Light 1.5.4 | Light 1.5.5 | Light 1.5.6 |
|---|---|---|---|---|
| UART1 power/RTC permission, Group0.bit3 | 1 allows, 0 denies | Same | Same | Same |
| Bits4/5 provide extended off / persistent lock | No; reserved | Same | Same | Same |
| Bits6/7 configure hard stop | No; static image choice | Same | Same | Same |
| Targeted off | OEM soft off | Same | Same | Same |
| Targeted reset checkpoint | None | Same | Same | Same |
| UART0 identity/status/clear, own address | Supported | Same | Same | Same |
| UART1 status/start/clear | Master only | Same | Same | Same |
| Both ports `64/04`, own address | 10 bytes | Same | Same | Same |
| Diagnostic lock/cache bytes 7–9 | `FF FF 00`: unavailable | Same | Same | Same |
| `64/03` identity layout | 19-byte layout | **EXT05 / 21 bytes** | Same layout | Same |
| Both ports `64/05`, own address | Absent | **Calibration pages** | Same | Same |
| Both ports `64/06`, own address | Absent | **68-byte SOC/energy read** | Same | Same |
| UART1 `4B`, own address | RTN04 | **History read** | Same | Same |
| Read-capability mask | Not present | **`000F`** | Same | Same |
| Reproduced scheduler wake-enable loss prevented | No | No | **Yes** | Same |
| Validated early poll completion | No | No | No | **Yes** |
| Downward / upward CCL step, A per online pack/update | 1 / 1 | Same | Same | Same |
| Separate EXT CCL configuration | Absent | Absent | Absent | Absent |

The `.3` identity layouts identify the release baselines in this comparison.
The seven buildable profiles use EXT05; current clients accept only that layout.
Light diagnostic bytes `FF FF 00` mean unavailable lock/cache capability,
not confirmed unlocked. A Light `64/06` read does not imply a reset checkpoint.

## Identical flag bytes

The gate comparison assumes an own-address UART1 request and otherwise valid
parameters. Permission passing does not guarantee downstream storage or RTC
success.

| Identical input | Light 1.5.3+ | Full 1.6.3+ |
|---|---|---|
| Group0=`FF`; `45` power/reset or `4E` RTC write | Allowed | Same |
| Group0=`00`; same request | RTN05 | Same |
| Group0=`7F`; same request | Allowed | Same |
| UART1 `4D` RTC read | No bit3 gate | Same |
| UART1 `A1` with bit0=0 | E3 | Same |
| UART1 `A1` changes bit2 or bit3 | Whole block rejected, E3 | Same |
| UART1 `A1` changes bit5 with bit0=1 | Ordinary reserved bit | **Whole block rejected, E3** |

Bit0 permits UART1 parameter writes; bit2 permits maintenance start. These
permissions are independent of bit3. A1 may disable its own bit0 from 1 to 0,
but cannot re-enable it while denied. The protected A1 difference mask is `0C`
in Light and `2C` in Full. UART0/UART2 retain their configuration paths.
Bit1 retains the OEM temperature-sensor plausibility check. Group1–7 have no
additional EXT configuration fields; existing Group5/Group7 prerequisites apply.

Full bit5 reports cache-owned lock status. Directly placing `00` in RAM does
not persist a lock. Disabling bit4 does not release a lock; targeted on is
required. Light soft off may permit charging or charging wakeup. Full extended
off can persistently inhibit the controlled power paths.
[Full contract](ext-full.md) defines the priorities and limits.

### Hard-stop selection from Full 1.6.3

| Stored Group0 upper pair | Group0 example | Full 1.6.3+ | Light 1.5.3+ |
|---|---|---|---|
| `00` | `3F` | Explicit soft stop | No parameter selection |
| `40` | `7F` | Explicit hard stop | No parameter selection |
| `80` | `BF` | Inherit image default | No parameter selection |
| `C0` | `FF` | Inherit image default | No parameter selection |

The selected images default to soft stop. For Group0=`7F`, Group5.bit1 enabled
and recharge-wait Event6.bit1 set, Full applies hard-stop charge inhibition.
Other protections and recovery paths can dominate; these bits do not provide
general pack off. Light image flag bit0 states its fixed hard-stop choice.
With Full capability `80`, it states the inherited build default; read fresh
Group0.bits6/7 to determine the active choice.

## Identical requests

| Request and fixed state | Light 1.5.3+ | Full 1.6.3+ |
|---|---|---|
| UART0 own `64/03` | RTN00 with identity | Same |
| Both ports own `64/04` | RTN00, 10 INFO bytes; no lock/cache | RTN00, 10 INFO bytes with lock/cache |
| Targeted `45/06`, gate permits it | Native reset without a new SOC checkpoint | Verified primary/backup checkpoint, then reset |
| Same reset with checkpoint program/readback failure | No new checkpoint path | RTN08; reset aborted |

| Request and fixed state | Light 1.5.3 / Full 1.6.3 | Light 1.5.4+ / Full 1.6.4+ |
|---|---|---|
| UART1 master own `64/05` | RTN05 | RTN00, 72 active-calibration bytes |
| UART1 slave own `64/05` | Silent | RTN00, 72 active-calibration bytes |
| UART0 own `64/05` | RTN05 | RTN00, 72 active-calibration bytes |
| UART1 own `4B 0000`, empty history ring | RTN04 | RTN00 with empty INFO |

An empty RTN00 history reply means a supported empty ring. Unsupported
canonical 64 subcommands return RTN05 on UART0; on UART1 they return RTN05 on
master 0 and remain silent on nonzero packs. Foreign/FF extension requests
remain silent. UART1 maintenance status/start/clear are master-only. UART0
status/clear are addressed, while canonical `64/01 C35A` start returns RTN05.
Starting maintenance on UART1 additionally requires Group0.bit2=1, the exact
token and Group7.bit5=0. Clearing the marker needs no write/start/power permission.

## Identity and energy decoding

EXT05 has 21 decoded INFO bytes, LENGTH `402A`, and 60 total ASCII frame bytes.
Version bytes are at 7–9, build ID at 10–17, image flags at 18 and the big-endian
capability mask at 19–20. Mask `000F` denotes UART1 history, calibration
pages, persisted SOC contents and full-width energy. Full 1.6.7 adds `0010` for CCL configuration, giving `001F`.

All versioned profiles preserve OEM `42` energy encoding: below raw 65000 the
value is emitted normally; at 65000 or above the u16 field emits fallback 6500.
Both use 0.1 kWh units. From Light 1.5.4 / Full 1.6.4, `64/06` reports full u32
totals. For native total 65000, `42` reports 650.0 kWh while `64/06` reports 6500.0 kWh.
This is a difference between queries; the `42` encoding remains unchanged.

## Atomic cleanup from Light 1.5.5 / Full 1.6.5

Within each branch, `.4` and `.5` share permissions, parameter/persistence
semantics and query layouts. Identity changes in version bytes and build ID.
The scheduler fix prevents the controlled lost wake measurement-enable update,
restores the incoming interrupt mask and retains newly deferred slow-work
notifications. This can affect future measurements if that instruction window
is encountered. Whole-system reachability and physical occurrence of the
original loss remain unproven. The
[source analysis](../../../analysis/firmware/startup-clock-timers.md#atomic-cleanup-from-emu1101-ext-light-155--full-165)
defines the code path and native counterexample.

## Evidence and limits

The input manifest binds the seven buildable EXT images. Their mandatory native
tests verify identity, permissions, remote reads, reset paths and scheduler
behavior. Exact `.3` baseline identities and source-bound directed comparisons
remain in local evidence. [Release history](../../firmware/CHANGELOG.md)
records the release baselines and development steps separately.

UART, RTC, flash and EEPROM boundaries are modeled. Directed RAM values, empty
rings and fault injection are synthetic. The tests do not establish physical
timing, physical multi-pack execution or hardware validation. See the
[current access matrix](uart-write-capabilities.md) and
[validation limits](validation-methods-and-limits.md).

## Early polling from Light 1.5.6 / Full 1.6.6

Both branches retain their .5 behavior and add validated early completion of
master UART0 polls. A matching valid response releases the next sequential
request before the nominal 150 ms timeout; invalid or missing responses retain
the original deadline. The aggregate remains gated by the one-second slow pass,
so faster polling can increase aggregate/CCL update frequency without changing
the per-update CCL step. No new command, permission bit or NVM migration is
introduced. See [early polling](early-polling.md) and [release metadata](../../firmware/releases/README.md).

## Configurable downward CCL from Full 1.6.7

Full 1.6.7 retains the Full 1.6.6 polling and safety behavior. A separate stored value selects 1–20 A downward per online pack per update; upward remains 1 A. Default 1 reproduces the ordinary prior ramp. The same OEM flags and parameters therefore retain their meaning, but an explicitly changed new setting alters the rate of ordinary CCL reduction. Native target saturation and immediate overrides remain unchanged.

New addressed services are 64/07 read and 64/08 set, with UART1 writes gated by Group0.bit0. EXT05 remains 21 bytes and gains capability 0010 (Full mask 001F). Light remains 000F with the fixed ramp. The field is absent from OEM 47/A1 and XML exports. [Complete contract](configurable-ccl-ramp.md).


## Polling and CCL matrix through Full 1.6.7

These are ordinary-ramp examples with twelve continuously online packs, a fixed 10 A target, initial CCL 1560 A and no direct zero/heating/Full override. The timing model is based on OEM .13; older OEM inputs and unversioned development images are not assigned these seconds estimates without source-specific evidence. `P` is the aggregate-update interval, not the CAN send interval.

| Master firmware | Downward factor d | Bank step per update | Updates until ≤840 A / exactly 10 A | Calculated seconds at stated P |
|---|---:|---:|---:|---|
| OEM 16.06.13 | 1 | 12 A | 60 / 130 | ≈120 / 260 at nominal P=2 s |
| Light 1.5.3, 1.5.4, 1.5.5 | 1 | 12 A | 60 / 130 | Same fixed-window model |
| Full 1.6.3, 1.6.4, 1.6.5 | 1 | 12 A | 60 / 130 | Same when Full override is inactive |
| Light 1.5.6 / Full 1.6.6 | 1 | 12 A | 60 / 130 | ≈60 / 130 if P=1 s; ≈120 / 260 if P=2 s |
| Full 1.6.7, default | 1 | 12 A | 60 / 130 | Same as `.6` |
| Full 1.6.7 | 2 | 24 A | 30 / 65 | ≈30 / 65 if P=1 s; ≈60 / 130 if P=2 s |
| Full 1.6.7 | 3 | 36 A | 20 / 44 | ≈20 / 44 if P=1 s; ≈40 / 88 if P=2 s |
| Full 1.6.7 | 5 | 60 A | 12 / 26 | ≈12 / 26 if P=1 s; ≈24 / 52 if P=2 s |
| Full 1.6.7 | 10 | 120 A | 6 / 13 | ≈6 / 13 if P=1 s; ≈12 / 26 if P=2 s |
| Full 1.6.7 | 20 | 240 A | 3 / 7 | ≈3 / 7 if P=1 s; ≈6 / 14 if P=2 s |

The P=1 s case requires the entire poll round to complete before the next slow pass; it is not guaranteed by `.6`/`.7`. These budgets count `K × P`; warning-to-first-update delay and electrical inverter response are not established. Upward steps remain N × 1 A per update in every row. The Full 1.6.7 factor is a **separate persistent EXT setting on the addressed BMS**, effective in the master role, outside the 87-value OEM block and its replication/export workflow.

[Timing derivation, more starting values, pack counts and operational effects](early-polling.md#calculated-timing-across-firmware-versions) · [OpenBMS setting workflow](openbms-monitor.md#full-167-ccl-configuration)
