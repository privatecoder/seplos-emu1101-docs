# States and triggers (derived from the firmware code)

Which conditions must be met, for how long and under which prerequisites, for the BMS to do something? The basis is the disassembly of **16.06.13**; all functions described here are **identical in 16.06.12** (addresses in parentheses: 06.13 / 06.12). **Older versions** (comparison of all functions of the 1 s block): 06.11 differs only in the temperature hysteresis fix, the heating condition and system status bit 2; 06.03–06.05 additionally differ in SOC 0 % through UVP (only while discharging), the enable condition of the voltage calibration (only from 3.000 V instead of 2.000 V) and the source of the temperature bits for the charge/discharge lock. Details: [CHANGELOG](firmware-changelog.md). Everything else has been the same since 06.03 (much of it since 04.06).

Tagging as in the other files: *(confirmed)* = read directly in the code, *(probable)* = interpreted, *open* = not traced.

---

## 0. Basics

### Timing
- The **coulomb counter and energy counter** run in a timer ISR with a period of exactly **1 s** (`0x9044` / `0x8DD8`). *(confirmed)*
- The **main loop** (protection logic, SOC calibration, status) runs **exactly once per second**: timer 0 ticks every 5 ms, the measurement sequencer starts the main loop after 200 ticks (06.13 `0x5FC4`, `0x1ABA`). All "cycles" below are therefore seconds. *(confirmed)*
- Time-critical functions (short-term overcurrent, short circuit, soft start, switching to the current limiter from 10 A) run in the **5 ms** cycle. *(confirmed)*

### Units and notation
- `N` = parameter 65 "cells in series" (16 in the example configuration).
- `P<n>` = parameter n from BatteryMonitor (list: [Firmware analysis §7](firmware-analysis.md#7-parameters-and-function-switches)).
- SOC is kept twice internally: in 0.1 % (for calibration) and as whole percent (for alarms and idle drift). The remaining capacity is a charge counter in 0.01 A·s.
- "Charging"/"discharging"/"charge current ≥ 3 A" are system status bits 1/0/7 of the **individual pack** ([Firmware analysis §8.2c](firmware-analysis.md#82c-system-status-all-bits-from-the-code)).

### Parameters of the example configuration (export `1101-SP75`) that appear below

| Parameter | Value | | Parameter | Value |
|---|---|---|---|---|
| P0 Cell high voltage alarm | 3.450 V | | P10 Pack high voltage alarm | 55.20 V |
| P1 … recovery | 3.350 V | | P12 Pack undervoltage alarm | 46.40 V |
| P2 Cell undervoltage alarm | 2.900 V | | P14 Pack overvoltage protection | 56.00 V |
| P3 … recovery | 3.100 V | | P15 … recovery | 53.60 V |
| P4 Cell overvoltage protection | 3.650 V | | P50 Charge overcurrent alarm | 150 A |
| P5 … recovery | 3.450 V | | P52 Discharge overcurrent alarm | −155 A |
| P78 Remaining capacity alarm | 15 % | | P80 Interval charge capacity | 96 % |
| P79 Remaining capacity protection | 5 % | | P81 Cycle cumulative capacity | 80 % |

Function switches: BitGroup1 = `DF` (pack OVP protection disabled, *confirmed*), BitGroup5 = `9F` (Intermittent recharge **on**), BitGroup7 = `1F` (passive CCL).

---

## 1. SOC: counting (coulomb counter, 1 s)

`0x9044` / `0x8DD8`, every second *(confirmed)*:

| Pack state | What happens | Exception / lock |
|---|---|---|
| **Charging** | Remaining capacity += current | From **SOC ≥ 98.2 %** counting up stops **as long as the highest cell is < P0** (3.45 V). The SOC then stays at 98.2 % until a calibration (§2) occurs or the highest cell reaches P0. |
| **Discharging** | Remaining capacity −= \|current\| | Below **(P79 + 1) %** (6 % in the example configuration) counting down stops **as long as the lowest cell is > P2** (2.90 V). Below **0.9 %** counting down stops as long as no undervoltage protection (cell or pack) is active. |
| **Standby** (neither charging nor discharging) | Self-consumption: −0.03 A | No deduction if the highest cell ≥ P1 (3.35 V) or the pack voltage ≥ N × 3.40 V. No deduction if the lowest cell > P3 (3.10 V) **and** SOC < (P79 + 1) %. |
| Standby **and SOC > P80** (96 %) | Deduction of **−0.20 A** instead of −0.03 A | same exceptions (highest cell ≥ P1 or pack ≥ N × 3.40 V → no deduction) |

Afterwards the remaining capacity is clamped to 0 … full capacity.

**Consequences:**
- A "stuck" SOC of **98.2 %** while charging is normal: without P0 at a cell or without calibration the firmware does not count further.
- A full pack in standby at < 3.35 V per cell loses 0.2 A arithmetically, i.e. ≈ 0.26 %/h at 280 Ah, down to 96 %. This artificially creates room again for "Intermittent recharge" (§4) after a charge has ended.
- The discharge SOC holds at 6 % or 0.9 % respectively until the voltage confirms the value.

---

## 2. SOC: calibration (jumps to fixed values)

### 2.1 Prerequisite for all voltage rules

The rules in 2.2 only run if the following has been true **for 30 s** *(`0x8E0C` / `0x8BA0`, confirmed)*:
- lowest cell ≥ 2.000 V **and** highest cell ≤ 4.300 V (plausibility)
- current zero point is calibrated (event 8 bit 4 = 0)

In addition, a counter **T** counts the seconds since the pack last **charged with ≥ 3 A** (system status bit 7; off only below 2.81 A). Every charge current ≥ 3.01 A resets T to 0. *(confirmed)*

### 2.2 Voltage rules (`0x8C08` / `0x899C`, confirmed)

Each rule **only raises the SOC**, never lowers it. It only applies if the current SOC is below the column "only if SOC <".

| New SOC | Voltage condition | How long | Further prerequisite | Only if SOC < | With the example values |
|---|---|---|---|---|---|
| **23 %** | Pack ≥ N × 3.30 V **and** lowest cell ≥ 3.200 V | at the moment of the check | T > 30 min | 18.0 % | Pack ≥ 52.80 V |
| **70 %** | Pack ≥ N × 3.37 V **and** lowest cell ≥ 3.320 V | at the moment of the check | T > 30 min | 65.0 % | Pack ≥ 53.92 V |
| **90 %** | (Pack ≥ N × 3.40 V **and** lowest cell ≥ 3.340 V **continuously > 30 min**) **or** highest cell ≥ P0 | see left | T > 30 s | 85.0 % | Pack ≥ 54.40 V or cell ≥ 3.45 V |
| **98 %** | Pack ≥ N × V<sub>full</sub> **and** lowest cell ≥ 3.350 V | **continuously > 30 s** | T > 30 s | 95.0 % | Pack ≥ 55.20 V |
| **100 %** | the same condition | **continuously > 30 min** | T > 30 s | 99.0 % | Pack ≥ 55.20 V for 30 min |

- **V<sub>full</sub> = P0, clamped to 3.45 … 3.50 V.** With P0 = 3.45 V this gives N × 3.45 V = 55.20 V. Setting P0 to 3.40 V still yields 3.45 V; setting 3.60 V yields 3.50 V.
- "continuously": the counter is reset to 0 as soon as the condition is not met in one pass.
- The 100 % rule additionally sets the internal **"full" flag** (controls §4).
- T > 30 s means in practice: the pack must not have charged with ≥ 3 A in the last 30 s. A calibration to 98/100 % therefore only happens **once the charge current per pack has dropped below ~3 A** (or during a charging pause at high voltage). This is the only "tail current" condition there is.

### 2.3 Protection and alarm rules

| New SOC | Condition | Prerequisite | How often | Code |
|---|---|---|---|---|
| **100 %** | **Cell OVP or pack OVP** active (event 2 bit 1 / bit 5, after the function switch mask) | System status "charging" | once; again only after the full flag has been cleared (SOC ≤ P80 or highest cell ≤ P3) | `0x8F56` / `0x8CEA` |
| **0 %** | **Cell UVP or pack UVP** active (event 2 bit 3 / bit 7) | Current zero point calibrated | once; again only after charging ≥ 3 A, SOC ≥ P78 or lowest cell ≥ P1 | same |
| **(P78 + P79) / 2** (**10 %** in the example configuration) | lowest cell ≤ **P2** (2.90 V) | SOC ≥ P78 (15 %); prerequisite 2.1 | every time the condition holds | `0x8DC8` / `0x8B5C` |

The OVP/UVP rules act immediately (the delay lies in the respective protection detection).

---

## 3. Relearning the full capacity

`0x8E4C` / `0x8BE0`, counting in `0x9044` *(confirmed)*. The "Full Capacity" (280.00 Ah in the example configuration) changes only through this sequence:

1. **Full mark:** highest cell ≥ P0 (3.45 V) **and** lowest cell ≥ 3.350 V. It persists as long as the highest cell is ≥ 3.370 V **and** SOC ≥ 98 %.
2. **Start:** the pack starts to **discharge** while the full mark is set. From now on the removed charge is summed up.
3. **Abort** if
   - the pack **charges for 30 s in a row**, or
   - the pack **does not discharge for a total of 30 min** during the learning phase (pauses add up).
4. **Empty mark:** while discharging, the lowest cell reaches **≤ P2** (2.90 V).
5. **Completion:** the pack is no longer discharging, the empty mark is set, and discharging lasted **≥ 1 h** in total.
   - New full capacity = removed charge + remaining capacity left.
   - If the value lies between 80 % and 120 % of the old full capacity, it is adopted; otherwise it is clamped to 80 % or 120 % respectively. It is stored in the EEPROM.

**Consequence:** Without a complete discharge from ≥ 3.45 V to ≤ 2.90 V cell voltage in one go, the full capacity is **never** adjusted. The nominal capacity (P58) is independent of this.

---

## 4. "Intermittent recharge waiting" (event 6 bit 1)

`0x9190` / `0x8F24` *(confirmed)*

| | Condition |
|---|---|
| **set** | Full flag set (100 % via §2.2 or §2.3) **and** SOC > P80 (96 %) **and** function switch BitGroup5 bit 1 on |
| **cleared** | SOC ≤ P80, or highest cell ≤ P3 (3.10 V); with the switch disabled, the full flag is also cleared continuously (except during OVP) |
| **Effect** | The pack counts as **charge-locked**. If **all** packs are charge-locked, the master reports **CCL = 0** and "Charge enable" = 0 to the inverter ([CAN protocols §3](protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed)). The charge MOSFET stays on (only the special build SP80 switches it off). |

**Sequence in the example system:** pack reaches 100 % (e.g. 55.2 V for 30 min at < 3 A) → event 6 bit 1 → as soon as all 12 packs have reached this point, CCL = 0 → standby → SOC drops through consumption or the 0.2 A drift (§1) to 96 % → charging enabled again.

---

## 5. Remaining capacity alarms (event 6 bit 2/3)

`0x9190` *(confirmed)*, without hysteresis:
- **Bit 2 "remaining capacity alarm":** SOC < P78 (15 %). Suppressed as long as bit 3 is set.
- **Bit 3 "remaining capacity protection":** SOC < P79 (5 %).
- **Bit 3 opens the discharge MOSFET** ("Low SOC disconnect", discharge lock `0x7184`). Charging remains allowed. The pack then no longer counts as able to discharge, and the DCL to the inverter drops accordingly. *(confirmed)*
- After P73 hours the automatic charge activation (§16) can briefly lift the SOC protection.

---

## 6. Charging / discharging / standby / off (system status)

Complete table with all bits: [Firmware analysis §8.2c](firmware-analysis.md#82c-system-status-all-bits-from-the-code). In short *(confirmed)*:

| State | on | off |
|---|---|---|
| Discharging | I ≤ −0.50 A (with ambient temperature alarm −1.00 A) | I > −0.40 A (−0.80 A) |
| Charging | I ≥ +0.60 A (+1.20 A) | I < +0.50 A (+1.00 A) |
| Standby | neither charging nor discharging | – |
| Charge current ≥ 3 A (bit 7) | I ≥ +3.01 A | I < +2.81 A |
| Off (shutdown) | Button > 3 s, external switch, standby shutdown (P77) or control command (§14) | Charging detected, button, switch, control command |

The **master** decides for the system with its own deadband on the total current: discharging ≤ −0.8 A (off > −0.6 A), charging ≥ +1.0 A (off < +0.8 A).

---

## 7. Charging forbidden / charge MOSFET

Details: [Firmware analysis §8.1](firmware-analysis.md#81-charging-forbidden-and-charge-mosfet-0613-0x6ffa-0605-0x6516). In short *(confirmed)*:
- **Charging forbidden** (charge MOSFET off) as long as one of these protection states is active: cell/pack OVP, charge over-/undertemperature protection, ambient temperature protection, power stage overtemperature protection, charge overcurrent protection, charger overvoltage, cell too low to charge, reverse polarity, output connection fault.
- **OVP is lifted by discharging:** current < −10 A for 10 passes (~10 s) clears cell and pack OVP immediately, regardless of the recovery voltages P5/P15.
- Otherwise OVP only ends when the voltage falls below the recovery voltage (cell P5 = 3.45 V, pack P15 = 53.60 V).

---

### 7a. Discharging forbidden / discharge MOSFET

Details: [Firmware analysis §8.1a](firmware-analysis.md#81a-discharge-lock-and-discharge-mosfet-0613-0x7184-0612-0x6fb8-confirmed). The discharge MOSFET is off in the case of *(confirmed)*:
- cell or pack undervoltage protection (P6, P16)
- discharge over-/undertemperature protection (P32, P34), ambient protection (P42, P44), power stage protection (P48)
- discharge overcurrent protection (P55 after P67 s), short-term overcurrent (P56 after P68 ms), short circuit, locks (§15)
- **SOC < P79** (5 %), output connection fault
- SOC set to 0 % by UVP (empty flag), system status "off"

**Charging with ≥ 3 A lifts the undervoltage protection**, just as discharging > 10 A lifts the overvoltage protection.

---

## 8. Limits sent to the inverter (CVL/CCL/DCL)

Details: [CAN protocols §3](protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed). In short *(confirmed)*:

| Value | Formula | In the example system (12 packs) |
|---|---|---|
| **CVL** | P14 (pack OVP), **fixed**, no reduction | 56.0 V |
| **DVL** | P12 | 46.4 V |
| **DCL** | \|P52\|, above 20 A minus 10 A, × packs able to discharge | (155 − 10) × 12 = 1,740 A |
| **CCL** normal | BitGroup7 bit 7 = 0: P50 / 2; bit 7 = 1: P50 − 10 A (above 20 A); × packs able to charge | 150 / 2 × 12 = 900 A |
| **CCL** on warning | **all** packs able to charge have a charge-related warning (cell/pack high voltage alarm, charge temperature, ambient/MOS temperature, charge OC warning) → **10.0 A total** | 10 A total, i.e. ~0.8 A per pack |
| **CCL** = 0 | no pack may charge (MOSFET off or Intermittent recharge on all packs), or highest cell > P4 + 30 mV | – |
| **CCL** heating | BitGroup3 bit 6 on, highest cell temperature < 25 °C, lowest ≤ P36 → at least packs × 10 A | off in the example configuration |
| Ramp | CCL changes per cycle by at most packs × 1.0 A | ± 12 A per cycle |
| **Forced charge** | System SOC ≤ 5 % (off > 10 %) or ≤ 9 % (off > 13 %) | – |

There is **no SOC-dependent derating** and **no reduction of the CVL** when the pack is full.

---

## 9. Other states (references)

| State | Trigger | Source |
|---|---|---|
| **Balancing** | Cell ≥ P8 and ≥ P63 above the lowest cell; start only with spread > P62; not while discharging; neighboring cells locked | [Seplos ASCII protocol §7](protocols/seplos-ascii.md#7-passive-balancing-how-it-works-0613-0x653c0x205a) |
| **Cell heating** | lowest cell temperature ≤ P36 on, > P37 off (from 06.12 independent of the charge state) | [Firmware analysis §8.2](firmware-analysis.md#82-temperature-alarms-and-heater-0613-0x66c2-0612-0x64f6-0611-0x64fa) |
| **Cycle +1** | cumulative SOC decrease while discharging reaches P81 (80 %) | [Firmware analysis §8.2b](firmware-analysis.md#82b-energy-and-cycle-counters) |
| **Energy counter** | +100 Wh per 360,000 W·s in status charging or discharging | same |
| **Temperature alarms** | Parameters 20–35 with hysteresis, masked by charge/discharge state | [Firmware analysis §8.2](firmware-analysis.md#82-temperature-alarms-and-heater-0613-0x66c2-0612-0x64f6-0611-0x64fa) |
| **Cell difference fault** | Spread ≥ P60, off < P61 | [Seplos ASCII protocol §6.1](protocols/seplos-ascii.md#61-alarm-events-16-0x44-0x5a-history) |

---

## 10. Cross-check: BMS comparison table (Seplos column)

| Row | Table says | Code says |
|---|---|---|
| BMS Current Sensitivity | 0.5 A | ✔ Per pack: discharging from −0.50 A, charging from +0.60 A (with hysteresis, §6). System (master): −0.8 A / +1.0 A. |
| Current Limiter 10 A / Trigger | Over Current Warning or pack/cell high voltage alarm | ◐ Two different things: (1) The **hardware current limiter** in the pack is triggered by the **charge overcurrent warning** (P50) for P66/2 s, duration P71 min (BitGroup6 bit 7), or optionally immediately from **10 A charge current** (BitGroup6 bit 6), §13. High voltage warnings do **not** trigger it. The limiting current (10 A) is set by the hardware. (2) The **CCL to the inverter** drops to 10 A **total** if all packs able to charge have a charge warning, including cell/pack high voltage (§8). |
| CVL, CCL, DCL | CVL = pack OVP; CCL = charge OC warning / 2 × n; DCL = discharge OC warning − 10 A × n | ✔ exactly like that (CCL variant "−10 A" with BitGroup7 bit 7) |
| Full charge voltage trigger | Pack OVP or cell OVP | ✔, plus the voltage rule N × V<sub>full</sub> (§2.2) |
| Full charge tail current trigger | No | ◐ There is no configurable tail current. The voltage rules for 98/100 % do, however, require that no charging **with ≥ 3 A** took place in the last 30 s (§2.1). |
| Reset to 100 % trigger | Pack OVP ✔, cell OVP ✔, pack > cell high voltage alarm × 16 for 30 min ✔, "AND current under 0.5 A" ✘ | ✔ All three confirmed (§2.2/2.3). Clarification: the threshold is N × P0, but **P0 is clamped to 3.45–3.50 V**; additionally lowest cell ≥ 3.350 V and T > 30 s. There is no 0.5 A condition; the actual current limit is **3 A per pack**. OVP reset only in status "charging" and only if the protection is not masked by a function switch. |
| MPPT status when fully charged | MPPT off until OVP recovery | ✔ with OVP (charge MOSFET off until P5/P15 or discharging > 10 A for ~10 s). Without OVP: CCL = 0 through Intermittent recharge as soon as all packs are full (§4). |
| Charge MOSFET when fully charged | off or MPPT limited by CCL | ✔ MOSFET off only on protection; otherwise CCL (10 A on warning, 0 on Intermittent recharge). |
| Multiple protection levels | 1 level | ◐ Alarm + protection per quantity. For the charge voltage there are in practice three stages: high voltage alarm (CCL 10 A, if all packs), OVP (MOSFET off), highest cell > OVP + 30 mV (CCL 0). |
| Low SOC% disconnect | Yes | ✔ SOC < P79 opens the discharge MOSFET (§5, §7a). Can be disabled with BitGroup5 bit 3. |

---

## 11. Cross-check: forum post on reset to 100 %, Victron and CCL limiting

| Statement | Assessment |
|---|---|
| "The BMS sets 100 % when the battery voltage is greater than cell high voltage alarm × 16 for 30 min." | ✔ Confirmed (§2.2), with the restrictions: P0 is clamped to 3.45–3.50 V, the lowest cell must be ≥ 3.350 V, and no charging with ≥ 3 A may have taken place in the last 30 s. After 30 s there is already 98 %. |
| "Total Voltage Overvoltage Protection is also the CVL." | ✔ CVL = P14, fixed (§8). This applies to all CAN protocols with CVL, including Deye/Pylontech. |
| "Victron DVCC at 55.2 V: charge MOSFETs stay on, solar charger stays active." | ✔ plausible: if the voltage stays below P14 and the cells below P4, no OVP triggers and the MOSFET stays on. The 100 % reset then comes via the voltage rule (55.2 V for 30 min at < 3 A per pack). |
| "Total Voltage High Voltage Alarm at 56 V limits the CCL to 10 A **per BMS (× n)**." | ✘ partly wrong. According to the code, the CCL is set to **10 A in total**, and only once **all** packs able to charge have a charge-related warning (§8). The trigger is any charge warning, i.e. also the **cell** high voltage alarm P0. |
| "In off-grid operation this also limits the charging power." | ✔ Consequence of the CCL. |
| "If you don't want that, disable the function switch." | ✔ *confirmed*: BitGroup1 masks event 2. Bit 4 (pack high voltage alarm) and bit 0 (cell high voltage alarm) off → no warning → no 10 A limiting. The SOC logic is not affected by this; it reads P0 directly. |
| "Without Victron it does not work without the OVP trigger for the CVL." | ◐ The CVL is always P14. An inverter that follows the CVL therefore charges up to the OVP threshold. The 100 % reset, however, does not need OVP: the voltage rule applies at N × P0 (e.g. 55.2 V) when the current per pack is < 3 A. With sufficient margin between N × P0 and P14 and the 10 A limiting by the high voltage alarm, this also works without Victron (see §12). |

---

## 12. What this means in practice for the example system (12 packs, Deye, 06.12)

Sequence when fully charging with the example parameters *(derived from §1–8)*:

1. Deye charges with up to 900 A CCL up to the CVL of **56.0 V**.
2. From **55.20 V** pack voltage (P10) or 3.45 V at a cell (P0), a pack has a high voltage warning. As soon as **all 12** packs are warning, the CCL drops (with a ramp of 12 A per cycle) to **10 A total**, i.e. ~0.8 A per pack.
3. Per pack: charge current < 3 A → after 30 s **98 %**, after 30 min at ≥ 55.20 V and lowest cell ≥ 3.35 V **100 %**.
4. 100 % → **Intermittent recharge waiting** (BitGroup5 bit 1 is on in the example configuration). As soon as all packs have reached this point: **CCL = 0**.
5. Charging only resumes when the SOC of a pack drops to ≤ 96 % (consumption or 0.2 A standby drift).
6. Pack OVP (56.0 V) is **disabled** in the example configuration via BitGroup1 = `DF` *(confirmed, mask 06.12 `0x64BA`)*. A 100 % reset via pack OVP therefore does not take place; cell OVP (3.65 V) remains active.
7. The full capacity stays at 280.00 Ah as long as no pack is ever discharged in one go from ≥ 3.45 V to ≤ 2.90 V cell voltage (§3).

The captures in [Intra-pack protocol](protocols/intra-pack.md#real-captures-test-data) match this: several packs sit at **98.2 %** while charging with 2–3 A (counting lock §1), because no cell has reached 3.45 V yet and the 55.2 V rule has not yet been met for 30 s or 30 min respectively.

---

## 12a. Cross-check with the Seplos specification (51.2 V / 230 Ah, `specs/Mason 280 Specification.pdf`)

The specification describes the same BMS family, but lists **factory settings** that differ from those of the example configuration, and in some places a behavior different from firmware 06.12/06.13.

**Confirmed by the code:**

| Specification | Code |
|---|---|
| Short-term overcurrent: "Over current lock times 5, OFF", release "Connected with charger"; short circuit lock ON, 5 times | P70 = 5, BitGroup4 bit 6 (short-term) off, bit 7 (short circuit) on; the lock is released only by charging (§15) |
| Overcurrent protection: automatic recovery after 60 s or as soon as current flows in the opposite direction | P69 = 60 s, charging clears discharge protections, discharging clears the charge protection |
| "Active current limiting (OFF): charge current > 10 A → limiting"; "Passive current limiting (ON): charge current > charge overcurrent warning"; "Charging current limiting time delay 5 min" | **BitGroup6 bit 6 = Active**, **bit 7 = Passive**, P71 = 5 min (§13). These are the official names of these two bits. |
| Standby balancing ON, standby time 10 h; balancing while charging; start 30 mV, end 20 mV; no balancing at ambient > 50 °C / < 0 °C | BitGroup6 bit 0/1/2/3, P64, P62/P63, lock via ambient warnings P38/P40 |
| Remaining capacity protection: "Output current flow will be cut off" | SOC < P79 opens the discharge MOSFET (§5) |
| Button 1 s: wake up; 3 s: shut down, except while charging | "Off" after > 3 s, charging lifts "off" (§14) |
| Precharge 2000 ms (0–5000 ms) | P57 (§17) |
| "Longest standby time 48 h (no charger, no charge current)" | P77 + BitGroup7 bit 1 (§14) |
| Heating (factory setting OFF): only with charger, not in standby/discharging | BitGroup3 bit 6, heating output only while charging or with a detected charger |
| External switch (factory setting **OFF**): on/off via external switch in standby | BitGroup7 bit 0. **On in the example configuration** (`1F`). Without a connected switch, the idle level of the input decides; since the example packs are running, it is at "on". |
| "LCD screen ON" | BitGroup7 bit 3 (binary protocol). The device on the binary port is therefore the **LCD display**. |
| "Charging activating 1 minute … press the button for recovering from protection" | P72 = 1 min, manual charge activation after switching on (BitGroup6 bit 5) |
| Remaining capacity "calculated according to the cell voltage" | SOC voltage rules (§2) |
| Compensation 1 → 9, 2 → 13, "Battery connection line impedance compensation" | P83–P86: correction of the cell with this number, i.e. of the connector before it (e.g. between cell 8 and 9) |

**Deviations between specification and firmware 06.12/06.13** (the code applies):

| Specification | Firmware |
|---|---|
| Undervoltage protection: "BMS keeps communication with the inverter for 1 minute and shuts down"; shutdown also on undervoltage (chap. 5.4) | **No shutdown on undervoltage.** The discharge MOSFET opens, the BMS keeps running. Shutdown only happens via button, switch, command or after P77 hours of standby. The minute is the window duration of the charge activation (P72). |
| "Effective charging current" 1000 mA on / 700 mA off, discharging −1000 / −700 mA | Charging from **+0.60 A**, off below +0.50 A; discharging from **−0.50 A**, off above −0.40 A (doubled with ambient warning) (§6) |
| Charging mode when the charger voltage is **0.5 V** above the battery voltage | Charger detected at port ≥ pack **+ 1.00 V** (immediately) or ≥ pack − 0.20 V with open MOSFET (system status bit 2) |
| Undervoltage protection ends at charge current ≥ 1 A | Charging with **≥ 3 A** clears the undervoltage protection; otherwise recovery via P7/P17 |
| Overvoltage protection ends when the cell is below the recovery threshold **and** the SOC is below 96 %; "Output current ≥ 1 A" | The protection ends below P5/P15 (independent of SOC) or on **discharging > 10 A for 10 s**. The SOC condition is the separate Intermittent recharge lock (§4), which has the same effect. |
| CAN socket: pin 1/2/7/8 **NC**, pin 4 = **CAN-L**, pin 5 = **CAN-H** | The firmware has a second RS485 bus (UART1, 9600 baud), which in the example system's hardware is on pins 1/2 and 7/8, and the example Deye works with pin 4 = CAN-H, 5 = CAN-L. This table of the specification therefore does not match the hardware revision of the example system. *(The pinout itself cannot be derived from the code)* |
| RS485 sockets: pin 4/5 "Internal communication (NC)" | Note: this could be the pulse chain of the automatic address assignment (GPIO 7/8/9, firmware analysis §8.2d). Not verified. |
| Factory settings, e.g. pack OVP 57.6 V, cell warning 3.50 V, cycle cumulative capacity 20 %, nominal capacity 200 Ah | The values of the example configuration are in [Configuration parameters](configuration-parameters.md). |

## 13. Current limiter ("Current Limiter")

`0x69BA`, `0x6AB8` (5 ms), `0x6FFA`, `0x70F4` *(confirmed, 06.12 identical)*. The limiter is a hardware stage in parallel to the charge MOSFET (GPIO 10). When it is active, the charge MOSFET is off and the charge current flows through the limiter.

| Trigger | Prerequisite | Duration / end | In the example configuration |
|---|---|---|---|
| **Charge overcurrent warning** (I ≥ P50) present for **P66/2 seconds** (event 7 bit 7) | BitGroup6 bit 7 | **P71 minutes**, or 5 s without charging | on: from 150 A for 5 s → limited for 5 min |
| **Charge current ≥ 10.00 A** (5 ms measurement; event 7 bit 6) | BitGroup6 bit 6 | until no charging takes place for 5 s | off |

- Only active as long as the pack is not discharging and charging is not forbidden.
- GPIO 10 is only enabled once the feedback of the limiter stage (GPIO 14) has been present for 500 ms (until then event 6 bit 7).
- The limiting current itself (e.g. 10 A) is not configurable in the firmware; it is determined by the hardware *(probable)*.

## 14. On/off, standby shutdown and external switch

`0x8978`, `0x89E8`, `0x8A24`, `0x88D0` *(confirmed, 06.12 identical)*

| Trigger for "off" | Condition | Back on through |
|---|---|---|
| Button | pressed > 3 s (> 301 s → event 1 bit 3 button fault) | Button, charging |
| External switch | BitGroup7 bit 0, input GPIO `0x50001000` pin 0 high | Pin low, charging |
| Control command | ASCII 0x45 type 4, value ≠ 0x10 | Type 4 with 0x10, charging |
| **Standby shutdown** | BitGroup7 bit 1; **P77 hours** of continuous standby without external voltage at the port (system status bit 4 and not bit 2), highest cell < P5, no pending charge activation; 5 s outside standby reset the counter | Charger (port > P15), button, charging |

- Sequence of the standby shutdown: 60 s "charging forbidden", then "off". After 30 s "off" and without voltage at the port: save EEPROM, then GPIO `0x50001000` bit 1 = 0. That this switches off the BMS supply (self-holding circuit) is *probable*.
- "Off" opens the discharge MOSFET (§7a).
- **In the example configuration:** BitGroup7 = `1F` → bit 1 on, **shutdown after 48 h of standby** without a charger. In a system with an inverter that keeps the port permanently energized or charges regularly, this practically never happens.

## 15. Overcurrent: shutdown, reconnection, lock

`0x6AB8` (5 ms), `0x6D62`, `0x6CBC` *(confirmed)*

| Event | Trigger | Shutdown | Automatically back on |
|---|---|---|---|
| Charge overcurrent protection | I ≥ P54 for **P66 s** | Charge MOSFET | after **P69 s**; immediately on discharging |
| Discharge overcurrent protection | I ≤ P55 for **P67 s** | Discharge MOSFET | after **P69 s**; immediately on charging |
| Short-term overcurrent | I < P56 for **P68 ms** (BitGroup4 bit 4) | Discharge MOSFET immediately | after P69 s |
| Short circuit | Comparator or output voltage after precharge < ½ (BitGroup4 bit 5) | Discharge MOSFET immediately | after P69 s |
| **Lock** | **P70** short-term overcurrent or short circuit events without a 301 s pause (BitGroup4 bit 6/7) | Discharge MOSFET permanently | **only by charging** |

P70 only counts short-term overcurrent and short circuit, not the normal charge/discharge overcurrent. In the example configuration: BitGroup4 = `BF` → lock after short-term overcurrent **off**, after short circuit **on**.

## 16. Charge activation after undervoltage

`0x6DC4`, `0x6E30`, `0x6EC2` *(code confirmed, purpose probable)*

| Variant | Switch | When | Window |
|---|---|---|---|
| automatic (event 7 bit 4) | BitGroup6 bit 4 | as long as UVP, SOC 0 % (empty flag) or SOC protection persists: every **P73 hours**, at most **P74** times | **P72 minutes** |
| manual (event 7 bit 5) | BitGroup6 bit 5 | once after switching on, if one of these states persists and the port voltage is low | P72 minutes |

- Within the window, the latch of cell/pack UVP, empty flag and SOC protection is cleared every second. The MOSFETs close, and a charger can detect the battery.
- Abort after 5 s if a cell is ≤ P9, a discharge current ≥ 3 A flows or a MOSFET path is off.
- Success: charging ≥ 3 A for 5 s or lowest cell > P7 resets the attempt counter.
- Because the voltage evaluation immediately sets UVP again as long as a cell is ≤ P6, this only helps in the range P6 < cell ≤ P7.
- **Caution:** BitGroup6 bit 4 at the same time **disables** the charge lock "cell < P9" (event 6 bit 4). In the example configuration (`BF`), this deep discharge lock is therefore ineffective.

## 17. Soft start (precharge)

`0x725A` (5 ms) *(confirmed)*: When the discharge MOSFET is switched on, the precharge path runs first for at most **P57 ms** (2000 ms in the example configuration). If the output voltage stops rising (checked every 100 ms), the precharge ends earlier. If the output voltage is then below half of the target value → short circuit (with BitGroup4 bit 5); otherwise the discharge MOSFET switches on.

## 18. Open

- Whether GPIO `0x50001000` bit 1 actually switches off the BMS supply (hardware).
- The current enforced by the current limiter (hardware).
- Hardware meaning of the pulse addressing (GPIO 7/8/9).

## Code reference

| Function | 06.13 | 06.12 |
|---|---|---|
| Coulomb/energy counter, learning phase (1 s ISR) | `0x9044` | `0x8DD8` |
| Enable voltage calibration (30 s) | `0x8E0C` | `0x8BA0` |
| Voltage rules 23/70/90/98/100 % | `0x8C08` | `0x899C` |
| Rule 10 % at cell ≤ P2 | `0x8DC8` | `0x8B5C` |
| Learn full capacity | `0x8E4C` | `0x8BE0` |
| OVP → 100 %, UVP → 0 %, clamping | `0x8F56` | `0x8CEA` |
| Full/empty flag, event 6 bit 1–3 | `0x9190` | `0x8F24` |
| System status | `0x870C` | `0x84A0` |
| Discharge lock | `0x7184` | `0x6FB8` |
| Current limiter, short-term overcurrent (5 ms) | `0x6AB8`, `0x70F4` | – |
| Overcurrent reconnection / lock | `0x6D62` / `0x6CBC` | – |
| Charge activation | `0x6DC4`, `0x6E30`, `0x6EC2` | `0x6BF8`, `0x6C64`, `0x6CF6` |
| Standby shutdown | `0x88D0` | `0x8664` |
| Soft start | `0x725A` | `0x708E` |
| Cycle counter | `0x9250` | – |
