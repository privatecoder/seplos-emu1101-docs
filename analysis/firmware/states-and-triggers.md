# States and triggers (derived from the firmware code)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Which conditions must be met, for how long and under which prerequisites, for the BMS to do something? The basis is the disassembly of **16.06.13**; all functions described here are **identical in 16.06.12** (addresses in parentheses: 06.13 / 06.12). **Older versions** (comparison of all functions of the 1 s block): 06.11 differs only in the temperature hysteresis fix, the BitGroup2 mask for the MOSFET locks, the heating condition and system status bit 2; 06.03–06.05 additionally differ in SOC 0 % through UVP (only while discharging), the enable condition of the voltage calibration (only from 3.000 V instead of 2.000 V) and the source of the temperature bits for the charge/discharge lock. Details: [CHANGELOG](firmware-changelog.md). Everything else has been the same since 06.03 (much of it since 04.06).

Confidence: *(confirmed)* = read directly in the code, *(probable)* = interpreted, *open* = not traced.

---

## Basics

### Timing
- The **coulomb counter and energy counter** run in a timer ISR with a period of exactly **1 s** (`0x9044` / `0x8DD8`). *(confirmed)*
- The **main loop** (protection logic, SOC calibration, status) runs **nominally once per second**: timer 0 ticks every 5 ms, the measurement sequencer starts the main loop after 200 ticks (06.13 `0x5FC4`, `0x1ABA`). All "cycles" below are therefore seconds. *(confirmed)*
- Time-critical functions (short-term overcurrent, short circuit, soft start, switching to the current limiter from 10 A) run in the **5 ms** cycle. *(confirmed)*

### Units and notation
- `N` = parameter 65 "cells in series" (16 in the example configuration).
- `P<n>` = parameter n from BatteryMonitor (list: [Configuration parameters](configuration-parameters.md)).
- SOC is kept twice internally: in 0.1 % (for calibration) and as whole percent (for alarms and idle drift). The remaining capacity is a charge counter in 0.01 A·s.
- "Charging"/"discharging"/"charge current ≥ 3 A" are system status bits 1/0/7 of the **individual pack** ([Charging / discharging / standby / off (system status)](states-and-triggers.md#charging--discharging--standby--off-system-status)).

### Parameters of the example configuration that appear below

| Parameter | Value | | Parameter | Value |
|---|---|---|---|---|
| P0 Cell high voltage alarm | 3.450 V | | P10 Pack high voltage alarm | 55.20 V |
| P1 … recovery | 3.350 V | | P12 Pack undervoltage alarm | 46.40 V |
| P2 Cell undervoltage alarm | 2.900 V | | P14 Pack overvoltage protection | 56.00 V |
| P3 … recovery | 3.100 V | | P15 … recovery | 53.60 V |
| P4 Cell overvoltage protection | 3.650 V | | P50 Charge overcurrent alarm | 100 A |
| P5 … recovery | 3.450 V | | P52 Discharge overcurrent alarm | −105 A |
| P78 Remaining capacity alarm | 15 % | | P80 Interval charge capacity | 96 % |
| P79 Remaining capacity protection | 5 % | | P81 Cycle cumulative capacity | 80 % |

Function switches: BitGroup1 bit 5 off (pack OVP protection disabled, *confirmed*), BitGroup5 bit 1 on (Intermittent recharge **on**), BitGroup7 bit 7 off (passive CCL).

---

## SOC and recharge transitions

SOC counting, voltage calibration, full-capacity learning, persistence and low-SOC discharge inhibition are defined in [SOC, capacity and persistence](soc-capacity-and-persistence.md). Those rules use both tenths of a percent and rounded whole-percent comparisons; displayed SOC alone does not determine the output state.

[Intermittent recharge waiting](intermittent-recharge-soft-vs-hard-stop.md) starts from the full flag, Group5.Bit1 and the rounded-SOC threshold P80. It excludes the pack from normal charge capability. Opening the local charge MOSFET additionally depends on soft/hard-stop selection and recovery priority.

## Charging / discharging / standby / off (system status)

Byte `0x200000AC`, checked in 06.12 and 06.13 (logic identical). All current thresholds refer to the reported pack current in 0.01 A (06.12 `0x20000CC8`, 06.13 `0x20000CD0`), + = charging. *(all confirmed)*

| Bit | Meaning | set | cleared | Code (06.12 / 06.13) |
|---|---|---|---|---|
| 0 | **Discharging** | I ≤ −0.50 A; with ambient temperature alarm/protection (event 4 bits 0–3) only at ≤ −1.00 A | I > −0.40 A or > −0.80 A; also on "off" | `0x84A0` / `0x870C` |
| 1 | **Charging** | I ≥ +0.60 A; with event 4 bits 0–3 only at ≥ +1.20 A | I < +0.50 A or < +1.00 A | same |
| 2 | **"Float"** = charger/external voltage detected at the port | immediately with bit 1 (charging); the separate port voltage ≥ pack voltage + 1.00 V path requires at least one MOSFET off (`0x87E4`–`0x880A`); otherwise after 5 s if at least one MOSFET is off and port ≥ pack − 0.20 V (on-off bit 6). Difference port − pack: 06.12 `0x20000D0E`, 06.13 `0x20000D16` (`cc8+0x4E`, 0.01 V) | after 5 s without this condition | `0x856E` / `0x87DA` |
| 3 | – | **never** (no write access sets it) | – | – |
| 4 | **Standby** | neither bit 0 nor bit 1 | bit 0 or 1 set; on "off" | `0x84A0` / `0x870C` |
| 5 | **Off (shutdown)** | button > 3 s, external switch (BitGroup7 bit 0), standby shutdown (parameter 77, BitGroup7 bit 1), control command 0x45 type 4 or 60 s of undervoltage/empty flag without charging (`0x887C`–`0x88C2`); normal discharge inhibit with charging-recovery exception ([power reference](power-on-off.md#discharge-permission-and-recovery-priority)), no general charge inhibit | charging detected (bit 1), button, switch low, control command type 4 with value 0x10; port > P15 if internal cause bits permit wakeup | `0x870C`, `0x87B8`, `0x0A3C` / `0x8978`, `0x8A24`, `0x0A3C` |
| 6 | **Discharge current ≥ 3 A** | I ≤ −3.00 A | I > −2.80 A | `0x84A0` / `0x870C` |
| 7 | **Charge current ≥ 3 A** | I ≥ +3.01 A | I < +2.81 A | same |

- Bit 7 is evaluated by the SOC calibration: the voltage rules for 98/100 % only take effect after current-status Bit7 has remained inactive for **more than30 s** (see [SOC correction prerequisites](soc-capacity-and-persistence.md#2-automatic-corrections-without-ovp)). No reader was found for bit 6. Both are only visible in the intra-pack response 0x5A. In 0x44 the firmware only reports `& 0x33` (bits 0, 1, 4, 5).
- Bits 0/1 are the basis for everything that requires "charging"/"discharging", e.g. the [energy counters](#energy-and-cycle-counters) and the charge/discharge temperature limits.
- The thresholds here apply to the individual pack. The master decides for the whole system separately with its own dead band (see [Modbus aggregate](../protocols/modbus-rtu.md#2-data-source-system-aggregate-0x2000164c), total current: discharging ≤ −0.8 A, charging ≥ +1.0 A).
- Confirmed with 24 real 0x5A captures (see [Intra-pack protocol](../protocols/intra-pack.md), real captures/test data).

System aggregation uses a separate deadband: discharging ≤−0.8 A, clearing above −0.6 A; charging ≥+1.0 A, clearing below +0.8 A. These are not per-pack detection thresholds.

Bit2 denotes external voltage/charger detection, not a float-charging phase. From16.06.12 its immediate and five-second paths follow the table above; through16.06.11 it was set only after30 s (`0x856E` / `0x87DA`, voltage difference from `0x1CFA`). It affects heating and standby shutdown. ASCII44 masks it out, whereas5A byte31 carries it. The interpretation is consistent with24 historical5A captures. Neither CVL nor SOC logic creates a float-voltage stage.

## Charge and discharge output decisions

[Charge permission and discharge recovery](power-on-off.md#charge-permission-and-output-masks) determine MOSFET outputs from protection masks, off and the full/empty state. Logical off normally inhibits discharge/precharge but does not generally inhibit charging. Native recovery has priority over some inhibits; the [power reference](power-on-off.md) specifies the exact order.

## Limits sent to the inverter (CVL/CCL/DCL)

Details: [CAN aggregate limits](../protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed). In short *(confirmed)*:

| Value | Formula | Example (4 packs) |
|---|---|---|
| **CVL** | P14 (pack OVP), **fixed**, no reduction | 56.0 V |
| **DVL** | P12 | 46.4 V |
| **DCL** | \|P52\|, above 20 A minus 10 A, × packs able to discharge **without a discharge-related warning** (cell/pack undervoltage P2/P12, discharge temperature P28/P30, ambient P38/P40, MOS P46, discharge OC P52, SOC P78); if all packs warn, DCL = 0 (no 10 A floor as with the CCL) (`0x96CE`, `0x98A8`/`0x99B0`) | (105 − 10) × 4 = 380 A |
| **CCL** normal | BitGroup7 bit 7 = 0: P50 / 2; bit 7 = 1: P50 − 10 A (above 20 A); × packs able to charge **without a charge-related warning** | 100 / 2 × 4 = 200 A |
| **CCL** on warning | every pack able to charge that has a charge-related warning (cell/pack high voltage alarm, charge temperature, ambient/MOS temperature, charge OC warning) drops out of the sum; only when none is left → **10.0 A total** (`0x96CE`, `0x98D4`) | −50 A per warning pack; all warning: 10 A total, i.e. 2.5 A per pack |
| **CCL** = 0 | no pack may charge (MOSFET off or Intermittent recharge on all packs) unless a heating request sets the heating minimum, or highest cell > P4 + 30 mV | – |
| **CCL** heating | BitGroup3 bit 6 on, highest cell temperature < 25 °C, lowest ≤ P36 → at least packs × 10 A | off in the example configuration |
| Ramp | Normal CCL adjustment is limited to packs × 1.0 A per cycle; the highest-cell >P4+30 mV zero branch and the no-chargeable-pack zero branch (subject to the heating minimum) bypass it | ± 4 A per cycle |
| **Forced charge** | System SOC ≤ 5 % (off > 10 %) or ≤ 9 % (off > 13 %) | – |

There is **no continuous SOC-based current curve** and **no reduction of CVL at full SOC**. Low-SOC warning P78 discretely excludes a pack from normal DCL contribution, and full/recharge waiting excludes it from normal CCL contribution; these flag-based exclusions remain.

---

## Other states (references)

| State | Trigger | Source |
|---|---|---|
| **Balancing** | Cell ≥ P8 and ≥ P63 above the lowest cell; start only with spread > P62; not while discharging; neighboring cells locked | [Passive balancing](states-and-triggers.md#passive-balancing) |
| **Cell heating** | lowest cell temperature ≤ P36 on, > P37 off (from 06.12 independent of the charge state) | [Temperature alarms and heating](states-and-triggers.md#temperature-alarms-heating-and-severe-faults) |
| **Cycle +1** | cumulative SOC decrease while discharging reaches P81 (80 %) | [Energy and cycle counters](states-and-triggers.md#energy-and-cycle-counters) |
| **Energy counter** | +100 Wh per 360,000 W·s in status charging or discharging | same |
| **Temperature alarms** | Parameters 20–35 with hysteresis, masked by charge/discharge state | [Temperature alarms and heating](states-and-triggers.md#temperature-alarms-heating-and-severe-faults) |
| **Cell difference fault** | Spread ≥ P60, off < P61 | [Alarm events 1–6 (0x44, 0x5A, history)](../protocols/seplos-ascii.md#61-alarm-events-16-0x44-0x5a-history) |

---

## Inverter behavior and configuration

CVL is fixed by P14. High-voltage warnings can reduce the system CCL; they do not directly select the local hardware current limiter. The warning fallback is **10 A for the whole bank**, not 10 A per pack. An inverter that follows this current request can also limit charger production; how it handles export or other DC loads is inverter-specific.

Reaching 100% does not require OVP. The [SOC voltage rules](soc-capacity-and-persistence.md#2-automatic-corrections-without-ovp) require their voltage, minimum-cell, current-status and strict duration conditions. The firmware has no configurable tail-current setting, absorption stage or float-voltage stage. Inverter-side charge-voltage limits can prevent OVP if configured below the applicable protection thresholds; actual behavior depends on the inverter's implementation.

Manufacturer thresholds, pinout variants and documentation inconsistencies are listed under [hardware specifications](../hardware/hardware-specifications.md). The [configuration reference](configuration-parameters.md) labels all illustrative values separately from factory defaults.

## Current limiter ("Current Limiter")

`0x69BA`, `0x6AB8` (5 ms), `0x6FFA`, `0x70F4` *(confirmed, 06.12 identical)*. The limiter is a hardware stage in parallel to the charge MOSFET (GPIO 10). When it is active, the charge MOSFET is off and the charge current flows through the limiter.

| Trigger | Prerequisite | Duration / end | In the example configuration |
|---|---|---|---|
| **Charge overcurrent warning** (I ≥ P50) present for **P66/2 seconds** (event 7 bit 7) | BitGroup6 bit 7 | **P71 minutes**, or 5 s without charging | on: from 100 A for 5 s → limited for 5 min |
| **Charging detected** (system status bit 1, 1 s cycle) or immediately at **≥ 10.00 A** (5 ms measurement); event 7 bit 6 | BitGroup6 bit 6 (switches bit 7 off) | until no charging takes place for 5 s | off |

- Only active as long as the pack is not discharging and charging is not forbidden.
- GPIO 10 is only enabled once the feedback of the limiter stage (GPIO 14) has been present for 500 ms (until then event 6 bit 7).
- The limiting current itself (e.g. 10 A) is not configurable in the firmware; it is determined by the hardware *(probable)*.

## On/off, standby shutdown and external switch

Button, external-switch and command control, the UVP/empty timeout, standby shutdown, wakeup causes, master broadcasts and supply self-hold are defined in [original on/off behavior](power-on-off.md). These mechanisms act on logical off; actual power-path decisions also depend on protection and recovery.

## Overcurrent: shutdown, reconnection, lock

`0x6AB8` (5 ms), `0x6D62`, `0x6CBC` *(confirmed)*

| Event | Trigger | Shutdown | Automatically back on |
|---|---|---|---|
| Charge overcurrent protection | I ≥ P54 for **P66 s** | Charge MOSFET | after **P69 s**; immediately on discharging |
| Discharge overcurrent protection | I ≤ P55 for **P67 s** | Discharge MOSFET | after **P69 s**; immediately on charging |
| Short-term overcurrent | I < P56 for **P68 ms** (BitGroup4 bit 4) | Discharge MOSFET immediately | after P69 s |
| Short circuit | Comparator or output voltage after precharge < ½ (BitGroup4 bit 5) | Discharge MOSFET immediately | after P69 s |
| **Lock** | **P70** short-term overcurrent or short circuit events without a 301 s pause (BitGroup4 bit 6/7) | Discharge MOSFET permanently | **only by charging** |

Native reconnection clears event5 & `0x3A`; charging clears event5.Bits3–7 and discharging clears Bit1. Locks are excluded from timed reconnection.

P70 only counts short-term overcurrent and short circuit, not the normal charge/discharge overcurrent. In the example configuration: BitGroup4 bit 6 off, bit 7 on → lock after short-term overcurrent **off**, after short circuit **on**.

## Charge activation after undervoltage

`0x6DC4`, `0x6E30`, `0x6EC2` *(code confirmed, purpose probable)*

| Variant | Switch | When | Window |
|---|---|---|---|
| automatic (event 7 bit 4) | BitGroup6 bit 4 | as long as UVP, SOC 0 % (empty flag) or SOC protection persists: every **P73 hours**, at most **P74** times | **P72 minutes** |
| manual (event 7 bit 5) | BitGroup6 bit 5 | once after switching on, if one of these states persists and the port voltage is low | P72 minutes |

- Within the window, the latch of cell/pack UVP, empty flag and SOC protection is cleared every second. The MOSFETs close, and a charger can detect the battery.
- Abort after 5 s if a cell is ≤ P9, a discharge current ≥ 3 A flows or a MOSFET path is off.
- Success: charging-current status Bit7 (set at3.01 A, cleared below2.81 A) for more than5 s or lowest cell > P7 resets the attempt counter.
- Because the voltage evaluation immediately sets UVP again as long as a cell is ≤ P6, this only helps in the range P6 < cell ≤ P7.
- **Caution:** BitGroup6 bit 4 at the same time **disables** the charge lock "cell < P9" (event 6 bit 4). In the example configuration (bit 4 on), this deep discharge lock is therefore ineffective.

## Soft start (precharge)

`0x725A` (5 ms) *(confirmed)*: When the discharge MOSFET is switched on, the precharge path runs first for at most **P57 ms** (2000 ms in the example configuration). If the output voltage stops rising (checked every 100 ms), the precharge ends earlier. If the output voltage is then below half of the target value → short circuit (event5.Bit5, with BitGroup4.Bit5); otherwise GPIO13 switches on and on-off Bit5 marks a 100 ms transition. Precharge uses GPIO15 / on-off Bit4.

## Temperature alarms, heating and severe faults

Temperature evaluator:16.06.13 `0x66C2`,16.06.12 `0x64F6`,16.06.11 `0x64FA`.

- For each cell sensor, the byte alarms (0x44) are determined with hysteresis.
- Event 3 (cell temperature) is calculated with parameters 20–35 and then masked according to state:
  - Charging or float active → only charge bits 0–3
  - Discharging → only discharge bits 4–7
  - Idle → depending on the previous state
- **06.12 fix:** up to 06.11, the unfiltered hysteresis state was stored directly in the reported byte `0x20000032`, and this byte was then masked. When switching charging ↔ discharging, the stored protection states of the respective other half were therefore lost. A charge overtemperature protection, for example, disappeared after a short discharge phase without the recovery temperature having been reached (example in the [CHANGELOG](firmware-changelog.md)). From 06.12, the raw state is stored in `0x200000BB`. *(confirmed, code and consequence)*
- Ambient (event 4 bits 0–3) and power stage (bits 4/5) are evaluated with parameters 38–49.
- **Heater (event 4 bit 6):** on when the lowest cell temperature is ≤ parameter 36; off when it is > parameter 37.
  - **Up to 06.11**, the bit was only set if charging or float was also active (system status bit 1/2).
  - **From 06.12**, it is set independently of the charge state. *(confirmed)*
  - **Heater output** (on-off bit 3, GPIO 11, `0x7350`): only with BitGroup3 bit 6 and only while charging or while a charger is detected at the port (system status bit 1/2). From 06.12 the request (event 4 bit 6) therefore comes independently of the charge state, but heating only happens with a charger. Control command 0x45 type 3 forces the heater for 3600 s. *(confirmed)*
- **Severe fault (event 4 bit 7)** (06.13 `0x6816`): set if one of these conditions holds for 5 s: temperature sensor fault (event 1 bit 1), highest cell ≥ **P4 + 50 mV**, lowest cell ≤ **P6 − 200 mV**, discharge protection active at current ≤ P55, charge overcurrent protection at current ≥ P54. No code clears it except the mask BitGroup3 bit 7 = 0; with bit 7 = 1 it remains until restart and switches (if bit 6 is off) the output GPIO 11. Neither the heater nor the charge lock evaluate it otherwise. *(confirmed; purpose "alarm relay" probable)*

## Energy and cycle counters

- **Energy counter** (`0x9044`, timer ISR with period `SystemCoreClock` = 1 s): every second, with system status "charging", `I(0.01 A) × U_Pack(0.01 V) / 10000` (= watts) is added to an accumulator; with "discharging", the absolute value. From 360,000 W·s (100 Wh), `cc8+0x58` (charged) or `cc8+0x5C` (discharged) is incremented by 1. **Unit 0.1 kWh.** *(confirmed)*
  - Output: ASCII 0x42 "Reserved 3/4" (u16, fixed 6500 from 65,000), Victron CAN 0x378 (u32).
  - Reset: ASCII 0x45 type 5 ("clear history").
- **Cycle counter** (`0x9250`): during discharging, the SOC decrease since the start of discharge is summed up. When the sum reaches **parameter 81 "Cycle cumulative capacity"** (e.g. 80 %), `cc8+0x60` is incremented by 1 and saved. A cycle is therefore a cumulative SOC decrease of e.g. 80 %, not a full charge/discharge. *(confirmed)*

## Passive balancing

**Enable** (event 7 bit 0) applies only if **all** conditions are met:
1. BitGroup6 bit 0 = 1 (balancing switched on).
2. Operating mode:
   - Bit 1 = 1: when charging and when idle, **not when discharging**
   - Bit 1 = 0: **only when charging** (system status bit 1)
3. No lock in event 7 bits 1–3:
   - **Bit 1** is set if
     - highest cell > **4.300 V**, or
     - lowest cell < **2.000 V** (up to 06.05: **3.000 V**), or
     - cell difference fault (event 1 bit 4), or
     - **no cell meets the selection criteria**
   - Bit 1 is **only cleared** if at least one cell is selected **and** the cell difference (max − min) is **> parameter 62 "Equalization opening difference"** (e.g. 30 mV).
     Once balancing has started, it continues until no cell meets the selection criteria any more (hysteresis down to parameter 63).
   - **Bit 2:** time limit (BitGroup6 bit 2). The balancing duration while idle reaches **parameter 64** hours. The counter only runs while not charging and is reset when charging.
   - **Bit 3:** temperature lock (BitGroup6 bit 3) on ambient temperature alarm/protection (event 4 bits 0–3).

**Cell selection** (mask `0x20000006`):
- The cells are checked **from the highest downwards**. A cell is selected if
  - its voltage is **≥ parameter 8 "Equalization opening voltage"** (e.g. 3.400 V) **and**
  - it is **≥ parameter 63 "Equalization closing difference"** (e.g. 20 mV) above the lowest cell.
- The search ends at the first cell that does not meet one of the criteria.
- **Neighbor lock:** two balanced cells must be at least three positions apart. For cell n, n±1 and n±2 are locked, a limitation of the balancing IC.
- The measurement IC receives the mask only in part of each measurement cycle (phase 17–38 of 40) and is otherwise off (measurement). The mask is reported continuously.

**Why balancing is rarely seen** (example configuration: start 3.400 V, opening 30 mV, closing 20 mV, BitGroup6 bits 0/1 = on, also when idle):
- LiFePO4 reaches 3.40 V only in the topmost SOC range at the end of charging.
- Balancing only starts if the spread is **at the same time** above 30 mV. With well-balanced packs this is never the case.
- After the end of charging (charge stop or "Intermittent recharge waiting"), the cells drop below 3.40 V within minutes. After that, no cell is selectable any more.
- **Verifiable:** In the 0x5A frames, event 7 = `02` (bit 1) shows that balancing is locked or not needed. This is exactly what the example frames show: event 7 = `02`.

The logic has been unchanged since 04.06, except for the minimum cell voltage (3.0 V → 2.0 V in 06.11).

---

With P65 ≤8, cell temperature channels3/4 copy channel2 (`0x2162`, OEM16.06.13). This is a measurement-channel rule rather than evidence of extra physical probes.

## Additional event conditions

Conditions *(confirmed,16.06.12 =16.06.13)*:
- **Event 1:** Bit1 (temperature sensor) is controlled by Group0.Bit1. Bit4 (cell difference ≥P60×10 mV, off <P61×10 mV) is always evaluated; Event1 has no whole-byte mask. Bit3 "button" means the button has been pressed for >301 s.
- **Event 6 bit 0:** port voltage ≥ P18 for > 5 s, off < P19. **Bit 4:** lowest cell ≤ P9, but only if BitGroup6 bit 4 = 0. **Bit 5 (reverse polarity):** no code sets it. **Bit 6:** GPIO `0x50001000` pin 10 low for ≥ 5 s, only with BitGroup5 bit 6; parameter 82 is not read. **Bit 7:** feedback of the current limiter stage (GPIO `0x50002000` pin 14).

For event4.Bit4/Bit5, Bit4 is power-stage protection (P48) and Bit5 is its warning (P46). Decode each event's defined bits rather than assuming every alarm/protection pair uses the same order. Event2 warning bits are cleared when their associated protections are active; see the [event masking rules](configuration-parameters.md#evaluation-order-and-mask-effects).


## Open

- Whether GPIO `0x50001000` bit 1 actually switches off the BMS supply (hardware).
- The measured current enforced by the fitted limiter; manufacturer documents advertise a nominal 10 A option ([hardware specifications](../hardware/hardware-specifications.md#sh-energy-catalogue-emu1101-product-family)).
- Exact RJ45-to-GPIO wiring and electrical characteristics of the pulse chain; the [native addressing mechanism](../hardware/internal-address-chain.md) is established in code.

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
