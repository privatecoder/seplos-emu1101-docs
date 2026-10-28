# SOC, capacity and behavior after loss of power

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Historical comparison images: OEM 16.06.13 and the fixed MAINT 1.6 build
`18daf61d8a93671d`. SOC arithmetic and block6 routines are unchanged. The only
exception in the compared A1 region is the known call to the 1.6 parameter
serializer at `0x08F8`, which protects the individual pack lock.

Evidence: [79 executable counterexamples](../../local/research/soc/evidence/SOC-2026-10-21-final.json)
and the [persistent analysis tool](../../mod/tools/firmware-analysis/probe_soc.py).
No serial ports were opened and no real parameters or firmware were changed.
The CPU executes the actual routines; acceptance/storage of IAP block6 is
modeled. This is not a physical NVM dump or a complete bootloader/hardware test. The probe requires the retained fixed MAINT 1.6 release and its build report under ignored `local/`; a fresh checkout lacks these historical fixtures.

Evidence: [24 SOC cutoff counterexamples](../../local/research/soc/evidence/SOC-Abschaltung-2026-10-21-final.json).
The [reusable code profile](../../mod/tools/firmware-analysis/soc_profile_v16.py) records
addresses, units, formulas, threshold rules and persistence triggers.
[Tool usage and reuse](../../mod/docs/tools/README.md).
Raw evidence is retained locally and is not part of a fresh public checkout.

## 1. Formula and periodic updates

The BMS maintains a signed charge counter Q in **0.01 A·s**, a learned full
capacity C in **0.01 Ah**, and a separately stored rated capacity P58.
C and P58 need not be identical.

```text
Q := Q + I[0.01 A]                      each second while charging/discharging
remaining capacity[0.01 Ah] := Q / 3600 integer division
SOC[0.1%] := remaining capacity × 1000 / learned full capacity
```

Code: counter `0x9044`, evaluation/clamping `0x8F56`. SOC is prepared in the
one-second main cycle; telemetry reads this state. Some decisions additionally
use SOC rounded to whole percent. Q is clamped to 0…C×3600. The firmware does
not continuously convert pack voltage into SOC or match SOC to neighboring packs.

`0x9044` / `0x8DD8`, every second *(confirmed)*:

| Pack state | What happens | Exception / lock |
|---|---|---|
| **Charging** | Remaining capacity += current | From **SOC ≥ 98.2 %** counting up stops **as long as the highest cell is < P0** (3.45 V). The SOC then stays at 98.2 % until an [automatic correction](#2-automatic-corrections-without-ovp) occurs or the highest cell reaches P0. |
| **Discharging** | Remaining capacity −= \|current\| | When **rounded whole-percent SOC < P79+1** counting down stops **as long as the lowest cell is > P2** (2.90 V). Below **0.9 %** counting down stops as long as no undervoltage protection (cell or pack) is active. |
| **Standby** (neither charging nor discharging) | Self-consumption: −0.03 A | No deduction if the highest cell ≥ P1 (3.35 V) or the pack voltage ≥ N × 3.40 V. No deduction if the lowest cell > P3 (3.10 V) **and** rounded whole-percent SOC < P79+1. |
| Standby **and SOC > P80** (96 %) | Deduction of **−0.20 A** instead of −0.03 A | same exceptions (highest cell ≥ P1 or pack ≥ N × 3.40 V → no deduction) |

Afterwards the remaining capacity is clamped to 0 … full capacity.

**Consequences:**
- A "stuck" SOC of **98.2 %** while charging is normal: without P0 at a cell or without calibration the firmware does not count further.
- A full pack in standby at < 3.35 V per cell loses 0.2 A arithmetically, i.e. 0.2 Ah per hour: ≈ 0.071 %/h at 280 Ah, so roughly 56 h from 100 % to 96 % while no exception applies. The counter deducts 20 or 3 units of 0.01 A·s per second. This artificially creates room again for [intermittent recharge](intermittent-recharge-soft-vs-hard-stop.md) after a charge has ended.
- With P79=5, the whole-percent comparison can hold the displayed SOC around **5.4%**, depending on the previous charge and current step. The separate 0.9% hold and voltage exceptions remain; see [SOC cutoff](#6-cutoff-based-on-soc-rather-than-voltage).

---

## 2. Automatic corrections without OVP

Enable check `0x8E0C`: plausible cells, minimum at least 2.000 V and maximum
at most 4.300 V, and calibrated current zero point, for **more than 30 s**.
The voltage rules first run on the 31st consecutive one-second call.
A separate counter T counts seconds without active charging-current status
bit7. Bit7 turns on at at least 3.01 A and off only below 2.81 A.
While bit7 is active, T is reset to 0.

Voltage rules at `0x8C08`; N is the number of series cells:

| New SOC | Voltage condition | Time / additional conditions | Previous SOC must be |
|---|---|---|---|
| 23% | Pack ≥ N×3.30 V, lowest cell ≥3.200 V | T >1800 s | <18.0% |
| 70% | Pack ≥ N×3.37 V, lowest cell ≥3.320 V | T >1800 s | <65.0% |
| 90% | Pack ≥ N×3.40 V and lowest cell ≥3.340 V for >1800 s; **or** highest cell ≥P0 | T >30 s | <85.0% |
| 98% | Pack ≥ N×Vfull, lowest cell ≥3.350 V for >30 s | T >30 s | <95.0% |
| 100% | Same full-voltage condition for >1800 s | T >30 s; sets full flag | <99.0% |

Vfull is P0 **clamped to 3.450…3.500 V**, then quantized to 0.01 V in the code.
For 16S, the resulting pack threshold is 55.20…56.00 V depending on P0.
P0=3.550 V gives 56.00 V, not 56.80 V. Voltage hold time and T are independent
counters: each voltage hold counter resets when its condition fails; high voltage can already be present during higher charging current;
the SOC increase still waits for T.

These rules only increase SOC. The independent P2 rule at `0x8DC8` can reduce
it to (P78+P79)/2: minimum cell ≤P2 and internal whole-percent SOC at least P78, with the same plausible-cell/current-calibration eligibility gate active for more than30 s.
For P78=15 and P79=5, the result is 10%.

## 3. OVP and UVP

`0x8F56` processes event2 bits after function-switch masking:

- **OVP →100%:** cell OVP (bit1) or pack OVP (bit5), charging status active,
  full flag not yet set. **No additional SOC delay counter:** the first matching
  SOC evaluation sets Q to C×3600.
- **UVP →0%:** cell UVP (bit3) or pack UVP (bit7), empty flag not yet set.
  Q is cleared only if the current zero point is calibrated; the empty flag is
  set even without this calibration (`0x8F6A`–`0x8F7E`). In16.06.13, discharging is not an
  additional prerequisite for this UVP branch.

Protection detection runs first. A disabled protection bit cannot trigger this
SOC correction. The full/empty flags make these one-shot reactions until their
respective reset conditions occur. The full flag clears when rounded SOC ≤P80 or highest cell ≤P3; disabling Group5.Bit1 clears it continuously except while OVP is active. The empty flag clears on charging-current status bit7, SOC ≥P78 or lowest cell ≥P1. Reaching 100% therefore does not require OVP.

## 4. What returns after loss of power

[MAINT1.6.2/1.6.3 planned-reset handling](../../mod/docs/firmware/storage-and-reset.md)
saves the native SOC record to both flash copies and checks them before an
addressed UART0/UART1 `45/06` reset. Storage failure returns RTN08 and prevents that
reset. `64/04` reads mirror diagnostics without repair. This is not SOC
recalibration; P58/P59, `49` and automatic save triggers remain. 



The native CRC/mirror readers select a valid primary without comparing age; otherwise a valid backup repairs it. If neither CRC is valid, P59/P58 provide the fallback. Word-interruption checks cover the native routines and MAINT1.5.1/1.6.1 bindings (historical test scope; see [storage and reset behavior](../../mod/docs/firmware/storage-and-reset.md)). These checks do not identify the cause of any particular power failure.

**Block6** is at flash address `0x2B000`, mirrored at `0x2C000`.
It contains remaining capacity, learned full capacity, energy counters and cycles.
Save routine: `0x5564`; startup load: `0x55CE`.

There is **no periodic continuous SOC checkpoint**. Save triggers are:

1. Neither charging nor discharging, and SOC differs by **more than 5.0
   percentage points** from the last saved value (`0x903E`). Exactly 5.0 is
   insufficient. The branch checks bits0/1, not an asserted standby bit:
   logical off without charging/discharging can also take this path.
2. A new cycle (`0x92B2`).
3. Completion of learning a new full capacity (`0x8F26`).
4. Before firmware-controlled self-shutdown (`0x8ACA`).
5. A1 capacity correction, **only** if |P58 − learned full capacity| ≥10 Ah
   (`0x09A8`, UART2 `0x8092`). An ordinary parameter/display write without this
   difference does **not** save block6.
6. Clear history/counters, `45/type5` (`0x5DAC`).

A hard power failure or watchdog reset does not automatically save current Q.
Startup may therefore restore a much older but valid block6 record. Cycles
and learned full capacity can remain plausible while the charge counted since
that checkpoint is missing. Reflashing alone does not calculate a new SOC
from voltage.

If **no valid block6 exists**, remaining/full capacity is initialized from
P59/P58, while energy and cycles start at 0. A schematic example with
P59=100 Ah and P58=250 Ah gives **40.0%**. This differs from restoration of
an older valid checkpoint.

The full capacity can also change after the complete learning sequence,
altering the denominator. This requires a full marker, a discharge learning
phase down to the lower cell threshold, and at least one hour of discharge.
Adjustment is limited to 80…120% of the old value.
[Full learning conditions](#7-learning-full-capacity).

## 5. Deliberate overwrite

Over **UART0, RS485-1/2**, ASCII CID2 `49`, with four INFO bytes:

```text
00 | 3B | remaining capacity as u16 big-endian in 0.01 Ah
```

Remaining capacity must not exceed learned full capacity; otherwise RTN06.
Success returns RTN00. Q is set immediately; reported remaining capacity/SOC
is updated from it at the next normal one-second evaluation. Counting and
automatic corrections subsequently continue.

| Path | Actual effect |
|---|---|
| `49/3B` | Sets Q=value×3600; does **not** change stored parameter P59. |
| `49/3A` | Sets learned full capacity and coulomb maximum; does **not** change rated capacity P58 in the parameter block. |
| A1 with changed P59 | Saves only that parameter/fallback field; does **not** set running Q. |
| A1 with at least 10 Ah difference from P58 | Sets learned full capacity to P58 and saves block6; can therefore change SOC. |

`49` itself does not immediately save block6. The new state becomes persistent
at the next save trigger above. An immediate restart can therefore lose it
again. At idle, the >5-percentage-point branch can save it at the next SOC cycle.

Schematic arithmetic example: at 250 Ah full capacity, 40% corresponds to
100.00 Ah remaining, encoded as 10000. This is not a target that can be inferred
from neighboring pack voltages.

**The compared MAINT1.6 does not support `49` over UART1** (RTN04 in the
counterexample). UART1-A1 and UART2-A1 do not replace `49/3B`. A polling master
must first enter maintenance or otherwise stop its polling before UART0 host access.
This analysis performed no real SOC correction.

## 6. Cutoff based on SOC rather than voltage

`0x9190` uses the **rounded whole-percent value** from `0x8F56`:
`SOC_whole = (SOC_tenths + 5) // 10`. Displayed tenths of a percent are not
directly compared with P78/P79/P80. The examples below assume P78=15,
P79=5 and P80=96.

| Condition | Switch / event | Effect |
|---|---|---|
| SOC_whole <P78 | Group5.Bit2 / Event6.Bit2 | Remaining-capacity warning; alone no local MOSFET discharge lock, but affects reported DCL. |
| SOC_whole <P79 | Group5.Bit3 / Event6.Bit3 | Normal discharge/precharge lock at `0x7184`, even at unremarkable cell voltages; charging remains possible. |
| Full flag and SOC_whole >P80 | Group5.Bit1 / Event6.Bit1 | Intermittent recharge waiting; pack is excluded from normal charge permission. Without Hard-Stop this alone does not open the charge MOSFET. |

Active remaining-capacity protection suppresses its warning. There is no
hysteresis: 14.4% warns, 14.5% no longer does; 4.4% protects, 4.5% does not yet.
The protection is separately maskable. Disabling this SOC switch does not
disable cell undervoltage protection. This describes firmware behavior;
it is not a recommendation to change protection switches.

**The counting hold comes first:** during discharge `0x9044` stops reducing Q
when `SOC_whole <P79+1` **and** the lowest cell is **above P2**. With P79=5,
the counter may therefore stop around 5.4% instead of progressing to SOC
protection through continued discharge alone. At minimum ≤P2 it continues.
The counterexample holds Q at 5.4% and 3296 mV; at 3000 mV=P2, −1 A again deducts
100 units of 0.01 A·s. The exact hold value depends on the previous counter and
the one-second step.

**Exceptions and distinctions:** native charging-current status bit7, asserted
from 3.01 A, can bypass normal discharge locks including SOC protection.
Automatic charge activation can temporarily clear protection bits. The delayed
logical-off condition at `0x887C` requires UVP or the empty flag without
charging; `SOC_whole <P79` alone is not that trigger. Normal discharge lock,
logical off and later self-shutdown are different states.

An incorrectly low SOC above the configured warning/protection thresholds
does not trigger those two events. Nor does it reliably predict a later
voltage-independent cutoff: counting holds, voltage corrections, switches and
charge recovery also matter. Inverter reactions to reported SOC or DCL are
a separate behavior.


## 7. Learning full capacity

`0x8E4C` / `0x8BE0`, counting in `0x9044` *(confirmed)*. The learned full capacity is independent of rated capacity P58. Automatic learning uses this sequence. Separately, `49/3A` can set learned full capacity directly; `A1` adjusts it to P58 only at a difference of at least 10 Ah. Neither capacity-writing path should be confused with writing parameter P58 itself ([write semantics](#5-deliberate-overwrite)):

1. **Full mark:** highest cell ≥ P0 (3.45 V) **and** lowest cell ≥ 3.350 V. It persists as long as the highest cell is ≥ 3.370 V **and** SOC ≥ 98 %.
2. **Start:** the pack starts to **discharge** while the full mark is set. From now on the removed charge is summed up.
3. **Abort** if
   - the pack **charges for 30 s in a row**, or
   - the pack **does not discharge for a total of 30 min** during the learning phase (pauses add up).
4. **Empty mark:** while discharging, the lowest cell reaches **≤ P2** (2.90 V).
5. **Completion:** the pack is no longer discharging, the empty mark is set, and discharging lasted **≥ 1 h** in total.
   - New full capacity = removed charge + remaining capacity left.
   - If the value lies between 80 % and 120 % of the old full capacity, it is adopted; otherwise it is clamped to 80 % or 120 % respectively. It is stored in internal flash (persistence block 6).

For the illustrative P0=3.45 V and P2=2.90 V, automatic learning requires the marked full-to-low-cell discharge sequence above. Allowed pauses do not constitute a continuously uninterrupted discharge. Direct `49/3A` and qualifying `A1` writes are separate adjustment paths; rated capacity P58 remains independent.

---

## 8. Code reference and version boundaries

The counting, calibration and learning logic is identical in 16.06.12/16.06.13. In 16.06.03–16.06.05, UVP sets SOC to zero only while discharging, and voltage-rule eligibility requires minimum cell voltage at least 3.000 V rather than 2.000 V. See the [OEM changelog](firmware-changelog.md).

| Function | 16.06.13 | 16.06.12 |
|---|---|---|
| Coulomb/energy counter, learning phase (1 s ISR) | `0x9044` | `0x8DD8` |
| Enable voltage calibration (30 s) | `0x8E0C` | `0x8BA0` |
| Voltage rules 23/70/90/98/100 % | `0x8C08` | `0x899C` |
| Rule 10 % at cell ≤ P2 | `0x8DC8` | `0x8B5C` |
| Learn full capacity | `0x8E4C` | `0x8BE0` |
| OVP → 100 %, UVP → 0 %, clamping | `0x8F56` | `0x8CEA` |
| Full/empty flag, event 6 bit 1–3 | `0x9190` | `0x8F24` |

The full flag and rounded-SOC recharge threshold feed [intermittent recharge waiting](intermittent-recharge-soft-vs-hard-stop.md). Energy and cycle counter behavior is described in [states and triggers](states-and-triggers.md#energy-and-cycle-counters).
