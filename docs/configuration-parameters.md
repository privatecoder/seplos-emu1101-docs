# Configuration file (BatteryMonitor parameter export) explained

Guide to [`config/parameter-export-example.xml`](../config/parameter-export-example.xml) (annotated copy: [`config/parameter-export-example-annotated.xml`](../config/parameter-export-example-annotated.xml)): what each entry really means, what the firmware does with it, what follows from it, and where the English label is misleading. Based on firmware 16.06.12/16.06.13 (see [Firmware analysis §7](firmware-analysis.md#7-parameters-and-function-switches), [States and triggers](states-and-triggers.md)).

Labelling: all effects have been **verified in the code of 06.12 and 06.13** (as of Oct. 2026). Only where the firmware drives hardware whose purpose it does not reveal itself is the **interpretation** marked *(probable)*. "Cycle" = 1 s (main loop, confirmed).

---

## 1. File structure

```xml
<paraGroup>
  <filetype>Parameter</filetype>
  <modualName>1101-SPxx </modualName>      ← device name (10 characters, "modual" = typo for module)
  <parameter><Name>…</Name><Value>…</Value><Unit>…</Unit></parameter>   × 87
  <param_bit_group><Name>BitGroup0</Name><Value>FF</Value></param_bit_group>   × 8
</paraGroup>
```

- The **order** is exactly the order inside the BMS: 60 × u16 (parameters 0–59, RAM `0x20001300`, 06.13; up to 06.12 `0x200012F8`), then 27 × u8 (parameters 60–86, RAM `0x200013F0`, 06.13; up to 06.12 `0x200013E8`), then 8 function switch bytes (`0x20000028`–`2F`). This is how BatteryMonitor reads them with ASCII command 0x47. *(confirmed)*
- **The names are not evaluated**, only the position. An export from a different BatteryMonitor version with a different order therefore does not fit.
- The values in the file are already converted (V, A, °C, Ah). Internally the BMS stores mV, 10 mV, 0.1 K, 10 mA, 10 mAh. *(confirmed)*
- `N` below = parameter 65 (cells in series, 16 in the example configuration).

---

## 2. Translation guide

The English names were machine-translated from Chinese. The most common errors:

| label in the file | origin | meaning |
|---|---|---|
| **Monomer** | 单体 ("single body") | **single cell** |
| **pressure** / **high pressure** / **low pressure** | 压 = pressure **and** voltage (电压) | **voltage** / high voltage / undervoltage |
| **Total pressure** / Total_voltage | 总压 | **pack voltage** (sum of all cells) |
| **differential pressure** / pressure difference | 压差 | **voltage difference** between cells |
| **Equalization** / equilibrium | 均衡 | **balancing** |
| **invalidation** | 失效 | failure/fault |
| **Environmental** | 环境 | **ambient**, same sensors as "Ambient" |
| **Power** (temperature) | 功率 | **power stage / MOSFET** |
| **Harging** | typo | **Charging** |
| **Ompensation** | typo | **Compensation** |
| unit **When** | 时 = hour *and* "when" | **hours** |
| unit **String** | 串 = series | **number of cells** or **cell position** |
| **SOC** in Ah | – | **remaining capacity**, not a percentage |
| **Interval charge capacity** | 间歇充电 | **intermittent recharge**: charging resumes below … % |
| **warning** / **alarm** | 告警 | **warning** (report only, for CCL consequences see below) |
| **protection** | 保护 | **protection**: MOSFET opens |
| **recovery** | 恢复 | return threshold (hysteresis) |

**Warning vs. protection:** every quantity has two levels. A warning does not open a MOSFET by itself, but it can have control effects: if all packs have a charge-related warning, the master lowers the CCL to 10 A total, and the charge over-current warning can activate the hardware current limiter. The protection opens the MOSFET. *(confirmed, see [States and triggers §7/8](states-and-triggers.md#7-charging-forbidden--charge-mosfet))*

---

## 3. Parameters 0–59

### 3.1 Cell voltage

| # | Name in the file | correct meaning | Example value | what the firmware does with it |
|---|---|---|---|---|
| 0 | Monomer high voltage alarm | **cell high-voltage warning** | 3.450 V | Event 2 bit 0. Triggers (if all packs) CCL 10 A. **Central to the SOC:** above 98.2 % the SOC only counts up if a cell is ≥ P0; 90 % rule; **100 % threshold = N × P0, limited to 3.45–3.50 V/cell** (55.20 V in the example configuration); full mark for capacity learning. *(confirmed)* |
| 1 | Monomer high pressure recovery | return of cell high-voltage warning | 3.350 V | Hysteresis for P0. Also: no SOC drift in standby as long as a cell is ≥ P1. *(confirmed)* |
| 2 | Monomer low pressure alarm | **cell undervoltage warning** | 2.900 V | Event 2 bit 2. SOC jumps to (P78+P79)/2 = 10 % if a cell ≤ P2 and SOC ≥ P78. Discharge SOC holds at 6 % as long as all cells > P2. Empty mark for capacity learning. *(confirmed)* |
| 3 | Monomer low pressure recovery | return of cell undervoltage warning | 3.100 V | Hysteresis for P2. Also clears the full flag when the highest cell falls to ≤ P3. *(confirmed)* |
| 4 | Monomer overvoltage protection | **cell overvoltage protection** (OVP) | 3.650 V | Charge MOSFET off, SOC := 100 % (while charging). CCL = 0 if a cell > P4 + 30 mV. *(confirmed)* |
| 5 | Monomer overvoltage recovery | return of cell OVP | 3.450 V | Charging enabled again below this value. Discharging > 10 A for ~10 s lifts the OVP immediately. *(confirmed)* |
| 6 | Monomer undervoltage protection | **cell undervoltage protection** (UVP) | 2.700 V | Discharge MOSFET off, SOC := 0 %. |
| 7 | Monomer undervoltage recovery | return of cell UVP | 3.100 V | |
| 8 | Equalization opening voltage | **balancing start voltage** | 3.400 V | A cell is only balanced if it is ≥ P8. With 3.40 V the BMS practically only balances at the end of a charge. *(confirmed)* |
| 9 | Battery low voltage forbidden charging | **charging forbidden below (cell)** | 1.500 V | Event 6 bit 4 (charging forbidden) as long as a cell ≤ P9. **Only if BitGroup6 bit 4 = 0** – in the example configuration bit 4 is on, so the lock is **ineffective**. Also an abort condition for charge activation (P72). |

### 3.2 Pack voltage and charger

| # | Name | correct meaning | Example value | what the firmware does with it |
|---|---|---|---|---|
| 10 | Total pressure high pressure alarm | **pack high-voltage warning** | 55.20 V | Event 2 bit 4 → CCL 10 A total if all packs warn. **No** SOC influence (the SOC rules use N × P0). *(confirmed)* |
| 11 | Total pressure and high pressure recovery | return of pack high-voltage warning | 53.60 V | |
| 12 | Total pressure low pressure alarm | **pack undervoltage warning** | 46.40 V | **= DVL** sent to the inverter. *(confirmed)* |
| 13 | Total pressure and low pressure recovery | return | 48.00 V | |
| 14 | Total_voltage overvoltage protection | **pack overvoltage protection** | 56.00 V | **= CVL** sent to the inverter, fixed. As protection: charge MOSFET off, SOC := 100 %. **Disabled via function switch in the example configuration** (§5), so it only acts as CVL. *(confirmed)* |
| 15 | Total pressure overpressure recovery | return of pack OVP | 53.60 V | |
| 16 | Total_voltage undervoltage protection | **pack undervoltage protection** | 43.20 V | Discharge MOSFET off, SOC := 0 %. |
| 17 | Total pressure undervoltage recovery | return of pack UVP | 48.00 V | |
| 18 | Harging overvoltage protection | **charger overvoltage protection** (voltage at port P+/P−) | 63.00 V | Event 6 bit 0, charging forbidden. |
| 19 | Charging overvoltage recovery | return | 61.00 V | |

### 3.3 Temperatures (cell sensors)

The **reported** charge-temperature warnings and protections (event 3) are masked by the current direction: charge bits are reported while charging or with a detected charger (system status bit 1/2), discharge bits while discharging; in standby the charge bits stay reported if they were reported before, otherwise the discharge bits (`0x6756`–`0x6786`). The **MOSFET control** does not use that masked byte: from 16.06.11 the charge lock tests the raw charge-protection bits (`0x200000BB` & `0x0A`) and the discharge lock the raw discharge-protection bits (`& 0xA0`) regardless of the current direction (16.06.13 `0x7050`, `0x71DA`). "Raw" only means not masked by current direction; from 16.06.12 `0x200000BB` is masked with BitGroup2, in 16.06.11 it is not (see [firmware changelog](firmware-changelog.md)). *(confirmed)*

| # | Name | correct meaning | Example value |
|---|---|---|---|
| 20 / 21 | Charging high temperature warning / recovery | charging: over-temperature warning / return | 50.0 / 47.0 °C |
| 22 / 23 | Charging low temperature warning / recovery | charging: under-temperature warning / return | 2.0 / 5.0 °C |
| 24 / 25 | Charging over temperature protection / recovery | charging: over-temperature **protection** (charging forbidden) / return | 55.0 / 50.0 °C |
| 26 / 27 | Charging under-temperature protection / recovery | charging: under-temperature **protection** / return | −5.0 / 0.0 °C |
| 28 / 29 | Discharge high temperature warning / recovery | discharging: over-temperature warning / return | 52.0 / 47.0 °C |
| 30 / 31 | Discharge low temperature warning / recovery | discharging: under-temperature warning / return | −10.0 / 3.0 °C |
| 32 / 33 | Discharge over temperature protection / recovery | discharging: over-temperature protection / return | 55.0 / 50.0 °C |
| 34 / 35 | Discharge under-temperature protection / recovery | discharging: under-temperature protection / return | −15.0 / 0.0 °C |
| 36 | Cell low temperature heating | **cell heating on** (lowest cell ≤) | 0.0 °C |
| 37 | Cell heating recovery | **cell heating off** (lowest cell >) | 10.0 °C |

Notes:
- The heating (36/37) only acts if a heating element is fitted and BitGroup3 bit 6 is on. In the example configuration this bit is **off** (§5). *(confirmed)*
- Notable: the charging under-temperature **warning** (2 °C) is above the protection (−5 °C). This is correct: first the warning (CCL 10 A if all packs), then the lock. For LiFePO4, charging below 0 °C is critical; with −5 °C as the lock, the configuration relies on the inverter or the CCL reduction.

### 3.4 Ambient and power stage

| # | Name | correct meaning | Example value |
|---|---|---|---|
| 38 / 39 | Ambient high temperature alarm / recovery | ambient: over-temperature warning / return | 50.0 / 47.0 °C |
| 40 / 41 | Ambient low temperature alarm / recovery | ambient: under-temperature warning / return | 0.0 / 3.0 °C |
| 42 / 43 | Environmental over-temperature protection / recovery | ambient: over-temperature **protection** / return | 60.0 / 55.0 °C |
| 44 / 45 | Environmental under-temperature protection / recovery | ambient: under-temperature **protection** / return | −10.0 / 0.0 °C |
| 46 / 47 | Power high temperature alarm / recovery | power stage (MOSFET): warning / return | 90.0 / 85.0 °C |
| 48 / 49 | Power over temperature protection / recovery | power stage: **protection** / return | 100.0 / 85.0 °C |

"Ambient" and "Environmental" are **the same sensor** (ambient/BMS board), just translated differently. As long as an ambient warning or ambient protection is active, the current thresholds for "charging"/"discharging" double (±1.0 A instead of ±0.5 A). *(confirmed)*

### 3.5 Current

| # | Name | correct meaning | Example value | what the firmware does with it |
|---|---|---|---|---|
| 50 | Charging overcurrent warning | **charge overcurrent warning** | 100 A | **Basis of the CCL:** per pack P50 / 2 (BitGroup7 bit 7 = 0, as in the example configuration) or P50 − 10 A (bit 7 = 1). In a 4-pack example 50 A × 4 = **200 A**. Factor: packs able to charge without a charge-related warning; every warning pack drops out of the sum, only when none is left does 10 A total apply (`0x96CE`, `0x98D4`). *(confirmed)* |
| 51 | Charging overcurrent recovery | return | 95 A | |
| 52 | Discharge overcurrent warning | **discharge overcurrent warning** | −105 A | **Basis of the DCL:** \|P52\| − 10 A (above 20 A) per pack. In a 4-pack example 95 A × 4 = **380 A**. Factor: packs able to discharge without a discharge-related warning (P2/P12, P28/P30, P38/P40, P46, P52, P78); if all packs warn, DCL = 0, no 10 A floor (`0x96CE`, `0x98A8`/`0x99B0`). *(confirmed)* |
| 53 | Discharge overcurrent recovery | return | −103 A | |
| 54 | Charge overcurrent protection | **charge overcurrent protection** | 160 A | charge MOSFET off after P66 seconds |
| 55 | Discharge overcurrent protection | **discharge overcurrent protection** | −160 A | discharge MOSFET off after P67 seconds |
| 56 | Transient overcurrent protection | **short-term overcurrent protection** (discharging) | −300 A | off after P68 ms |
| 57 | Output soft start delay | **pre-charge (soft start)** of the output | 2000 ms | When the discharge MOSFET is switched on, a pre-charge path (GPIO 15) runs first for at most P57 ms; if the output voltage stops rising, it ends earlier. Then short-circuit check (output < ½ target → event 5 bit 5, with BitGroup4 bit 5), then discharge MOSFET on. |

### 3.6 Capacity

| # | Name | correct meaning | Example value | what the firmware does with it |
|---|---|---|---|---|
| 58 | Battery rated capacity | **rated capacity** | 280.00 Ah | Reported in 0x42 as "Rated capacity". **Caution:** writing P58 can also reset the **learned full capacity**: the single command 0x49 sets it directly to the new value (if the remaining capacity is not above it); writing the whole parameter block 0xA1 resets it only if P58 differs from the learned full capacity by **≥ 10 Ah**. *(confirmed)* |
| 59 | SOC | **remaining capacity (set value)**, not a percentage | 50.00 Ah | The value in the file is **not the current state of charge**, but the last stored set value. Writing it with single command 0x49 sets the remaining capacity to this value (only if ≤ full capacity). When the whole block is written, it is not applied to the counter. *(confirmed)* |

---

## 4. Parameters 60–86

| # | Name | correct meaning | Example value | what the firmware does with it |
|---|---|---|---|---|
| 60 | Cell invalidation differential pressure | **cell difference fault from** | 0.50 V | Event 1 bit 4 (fault) if highest − lowest cell ≥ P60. Blocks balancing (event 7 bit 1). |
| 61 | Cell invalidation recovery | cell difference fault off below | 0.30 V | |
| 62 | Equalization opening pressure difference | **balancing starts from spread** | 0.030 V | Balancing only starts when highest − lowest cell > P62. Cf. P8, P63. |
| 63 | Equalization closing pressure difference | **a cell is balanced as long as it is ≥ P63 above the lowest** | 0.020 V | stop threshold per cell |
| 64 | Static equilibrium time | **time limit for balancing without charging** (hours) | 10 h | With BitGroup6 bit 2: a counter runs as long as balancing is enabled and the pack is **not** charging; after P64 h balancing is blocked until the next charge (event 7 bit 2). Charging resets the counter. |
| 65 | Battery number in series | **cells in series (N)** | 16 | Cell count in 0x42/0x44; factor of all pack voltage rules of the SOC (N × 3.30/3.37/3.40/P0). With ≤ 8 cells, temperature sensors 3/4 take over the value of sensor 2. |
| 66 | Charge overcurrent delay | delay of charge overcurrent **protection** (P54) | 10 s | Also: current limiter after charge overcurrent **warning** (P50) already after **P66/2 s** (BitGroup6 bit 7) |
| 67 | Discharge overcurrent delay | delay of discharge overcurrent protection (P55) | 10 s | |
| 68 | Transient overcurrent delay | delay of short-term overcurrent (P56) | 30 ms | 5 ms tick |
| 69 | Overcurrent delay recovery | **automatic re-enable after overcurrent** after … s | 60 s | Charge/discharge overcurrent, short-term and short-circuit protection are cleared after P69 s. Charging clears the discharge protections immediately, discharging clears the charge protection. |
| 70 | Overcurrent recovery times | **lockout after … short-term or short-circuit events** | 5 | Only with BitGroup4 bit 6 (short-term) or bit 7 (short circuit). From P70 events without a 301 s pause: lockout (event 5 bit 6/7), discharge MOSFET stays off **until the pack detects charging**. Does not affect the normal charge/discharge overcurrent. |
| 71 | Charge current limit delay | **duration of current limiting** (minutes) | 5 min | After a charge overcurrent warning, charging runs for P71 minutes through the hardware current limiter instead of the charge MOSFET (BitGroup6 bit 7, event 7 bit 7); also ends after 5 s without charging. |
| 72 | Charge activation delay | **charge activation: window duration** (minutes) | 1 min | For this long after an undervoltage or SOC protection shutdown, the protection is cleared every second so that the MOSFETs close and a charger can charge (event 7 bit 4/5). |
| 73 | Charging activation interval | **charge activation: interval** (hours) | 10 h | Automatic activation every P73 h as long as UVP/SOC 0 %/SOC protection persists (BitGroup6 bit 4) |
| 74 | Charge activation times | **charge activation: max. attempts** | 10 | Counter is reset on charging ≥ 3 A (5 s) or lowest cell > P7 |
| 75 | Work record interval | history entry during operation every | 30 min | EEPROM history (max. 500 entries), readable with 0x4B. In addition an entry at once on every change of system status or messages; the counter then restarts (undocumented commands §1.6) |
| 76 | Standby recording interval | history entry in standby every | 240 min | |
| 77 | Standby shutdown delay | **self-shutdown after … hours of standby** | 48 h | Only with BitGroup7 bit 1 (**on** in the example configuration). Conditions: continuous standby **without external voltage at the port**, highest cell < P5. Then 60 s "charging forbidden", then "off" (discharge MOSFET off), save state to internal flash, switch off supply *(switching off the supply probable)*. A charger (port > P15) or the push button aborts. |
| 78 | Remaining capacity alarm | **SOC warning below** | 15 % | Event 6 bit 2. Part of the 10 % SOC rule ((P78+P79)/2) and reset of the empty flag (UVP → 0 %). Event 6 bit 2 removes the pack from the DCL sum. If all packs are below P78, the master reports DCL = 0; the inverter therefore stops discharging already at P78, not only at P79. |
| 79 | Remaining capacity protection | **SOC protection below** | 5 % | Event 6 bit 3 → **discharge MOSFET off** (charging remains allowed). Discharge SOC holds at (P79 + 1) % = 6 % until a cell is ≤ P2. Charge activation (P72–P74) briefly lifts the protection periodically. |
| 80 | Interval charge capacity | **intermittent recharge: charge again only below** | 96 % | After 100 % charging is locked (event 6 bit 1) until SOC ≤ P80; all packs locked → CCL = 0 (except heating minimum). Only with BitGroup5 bit 1. Above P80, 0.2 A SOC drift in standby. |
| 81 | Cycle cumulative capacity | **a cycle counts after cumulative … % discharge** | 80 % | |
| 82 | Connection fault impedance | "connection fault impedance" | 10.0 mΩ | **No function:** never read by the firmware. The output connection fault (event 6 bit 6) comes from a hardware input (GPIO `0x50001000` pin 10, ≥ 5 s low, only with BitGroup5 bit 6). |
| 83 / 84 | Compensation point 1 position / impedance | **connector compensation 1**: cell number / resistance (0.1 mΩ) | 9 / 0.0 mΩ | Current × P84 is subtracted from the voltage of **exactly cell no. P83** (correction in mV = I [A] × R [mΩ]; lower when charging, higher when discharging). For a connector with contact resistance that falls into the measurement of this cell. 0.0 = ineffective. |
| 85 / 86 | Ompensation point 2 position / impedance | connector compensation 2 | 13 / 0.0 mΩ | same for cell no. P85 |

Incidentally in the code: if a cell voltage jumps by ≥ 200 mV, the firmware only accepts the new value after 5 consecutive measurements (noise filter).

---

## 5. Function switches (BitGroup0–7)

**BitGroup1–5 are enable masks for alarm events 2–6:** immediately after an event byte is generated, it is bitwise ANDed with its BitGroup **before** charge lock, discharge lock, SOC logic, CCL or protocols read it. **Bit = 0 disables reporting and reaction completely.** **BitGroup0 is not a mask** (only bit 1 has an effect). BitGroup6/7 are function switches. Order and addresses: [Firmware analysis §7.3](firmware-analysis.md#73-function-switches-0x200000282f--bitgroup07).

### BitGroup0 (event 1, faults)

| Bit | Function | example config |
|---|---|---|
| 1 | **Plausibility check of the temperature sensors**: sensor < −45 °C or ≥ 100 °C (MOS sensor ≥ 130 °C), or spread ≥ 20 K → event 1 bit 1 (temperature sensor fault), heating off (`0x68F2`) | on |
| 0, 2–7 | **no function** (only stored and reported). Event 1 bit 3 (push button) and bit 4 (cell difference, P60/P61) are always evaluated | – |

### BitGroup1 (event 2, voltage)

| Bit | Function | example config |
|---|---|---|
| 0 | cell high-voltage warning (P0) | on |
| 1 | cell OVP (P4) | on |
| 2 | cell undervoltage warning (P2) | on |
| 3 | cell UVP (P6) | on |
| 4 | pack high-voltage warning (P10) | on |
| 5 | **pack OVP (P14)** | **off** |
| 6 | pack undervoltage warning (P12) | on |
| 7 | pack UVP (P16) | on |

**Consequence of bit 5 = 0** *(06.12 `0x64BA` / 06.13 `0x6686`)*: the pack overvoltage protection never triggers. P14 (56.0 V) only acts as CVL. Protection against overcharging is provided by the cell OVP (3.65 V). A SOC reset to 100 % via pack OVP does not take place; the reset comes via the voltage rule (55.20 V for 30 min).

### BitGroup2 (event 3, cell temperature): all on
Bit 0/1 charging high warning/protection (P20/P24), 2/3 charging low (P22/P26), 4/5 discharging high (P28/P32), 6/7 discharging low (P30/P34).

### BitGroup3 (event 4)

| Bit | Function | example config |
|---|---|---|
| 0–3 | ambient high/low warning/protection (P38–P45) | on |
| 4 / 5 | power stage protection (P48) / warning (P46) | on |
| 6 | **cell heating** (P36/P37): heating output only on demand **and** while charging or with a detected charger; also enables the minimum CCL packs × 10 A for heating | **off** |
| 7 | **severe fault report** (event 4 bit 7: sensor fault, cell ≥ P4 + 50 mV, cell ≤ P6 − 200 mV, overcurrent protection at current beyond P54/P55; persists until restart). If bit 6 is off, it switches the heating/relay output (GPIO 11) *(purpose "alarm contact" probable)* | **off** |

### BitGroup4 (event 5, current)

| Bit | Function | example config |
|---|---|---|
| 0 / 1 | charge overcurrent warning (P50) / protection (P54) | on |
| 2 / 3 | discharge overcurrent warning (P52) / protection (P55) | on |
| 4 | short-term overcurrent detection (P56/P68, 5 ms tick) | on |
| 5 | short-circuit detection (comparator, check after pre-charge) | on |
| 6 | **lockout** after P70 short-term overcurrent events | **off** |
| 7 | lockout after P70 short-circuit events | on |

### BitGroup5 (event 6, miscellaneous)

| Bit | Function | example config |
|---|---|---|
| 0 | charger overvoltage (port ≥ P18 for > 5 s) | on |
| 1 | **intermittent recharge** (P80) | **on** |
| 2 | SOC warning (P78) | on |
| 3 | **SOC protection (P79): discharge MOSFET off** | on |
| 4 | charging forbidden, cell ≤ P9 (additionally only effective if BitGroup6 bit 4 = 0) | on |
| 5 | reverse polarity: **no function**, no code sets this event bit | off |
| 6 | output connection fault: hardware input GPIO `0x50001000` pin 10 ≥ 5 s low → discharge MOSFET off (P82 is not used) | **off** |
| 7 | feedback of the current limiter stage (internal, masked out in 0x44/0x5A) | on |

**Consequence of bit 1 = 1:** after a SOC reset to 100 % the pack reports "Intermittent recharge waiting". Once all packs are in this state, **CCL = 0** is sent to the inverter (unless a heating request raises it to the heating minimum, see [can.md §3](protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed)) until a pack drops to ≤ 96 % (P80). If this is not wanted, switch bit 1 off.

### BitGroup6 (functions)

| Bit | Function | example config |
|---|---|---|
| 0 | **balancing on** | on |
| 1 | balancing also when idle (otherwise only while charging); never while discharging | on |
| 2 | time limit P64 for balancing without charging | on |
| 3 | balancing lock on ambient temperature warning/protection | on |
| 4 | **automatic charge activation** (P72–P74) **and** disabling of the charge lock "cell ≤ P9" | on |
| 5 | **manual charge activation** once after power-on | on |
| 6 | **"Active current limiting"**: current limiter as soon as charging is detected (from +0.60 A), from **10 A** immediately in the 5 ms path (event 7 bit 6); with bit 6 set it clears event 7 bit 7 every time, so passive limiting (bit 7) has no effect (`0x710A`–`0x711E`, `0x6B82`) | **off** |
| 7 | **"Passive current limiting"**: current limiter after charge overcurrent warning (P50 for P66/2 s), duration P71 (event 7 bit 7) | on |

### BitGroup7 (functions)

| Bit | Function | example config |
|---|---|---|
| 0 | **external on/off switch** (GPIO `0x50001000` pin 0: high = off, low = on). Factory default according to the Seplos specification: **off** | on |
| 1 | **standby self-shutdown** after P77 | **on** (48 h) |
| 2 | no function (no reader) | on |
| 3 | binary protocol on RS232/TTL, *probably* the **LCD display** port (Seplos specification: "LCD screen ON"; the code cannot identify the device) | on |
| 4 | binary protocol in extended format A | on |
| 5 | ignore DIP address, address assignment via pulse chain (GPIO 7/8/9), master adjusts slave count *(hardware interpretation probable)* | off |
| 6 | only with bit 5: an address 0 determined by pulse becomes 1, the pack never becomes master (`0x9466`) | off |
| 7 | **CCL mode:** 1 = P50 − 10 A, 0 = P50 / 2 | **off** (→ half the warning threshold) |

**Note on bit 0:** if no switch is connected to the input, the idle level of the pin decides. If the packs run without a switch connected, it is evidently low (= on).

---

## 6. What follows from the example configuration

| Quantity | Formula | Result (example: 4 packs) |
|---|---|---|
| CVL sent to the inverter | P14 | **56.0 V** |
| DVL | P12 | 46.4 V |
| CCL normal | P50 / 2 × packs without a charge-related warning (every warning pack drops out) | **200 A** |
| CCL when all packs have a charge warning (P0, P10, temperature, charge OC) | fixed | **10 A total** |
| DCL | (\|P52\| − 10 A) × packs without a discharge-related warning; all warning: 0 A | **380 A** |
| SOC 98 % | pack ≥ N × P0 (3.45–3.50 V), lowest cell ≥ 3.35 V, 30 s, < 3 A charge current | 55.20 V |
| SOC 100 % | same, 30 min | 55.20 V for 30 min |
| SOC 100 % via OVP | cell OVP P4 while charging (pack OVP masked in the example configuration) | 3.65 V on one cell |
| SOC counting lock while charging | SOC ≥ 98.2 % and no cell ≥ P0 | – |
| charging enabled again after 100 % | SOC ≤ P80 | 96 % |
| SOC 10 % | cell ≤ P2 and SOC ≥ P78 | 2.90 V |
| SOC 0 % | cell UVP (P6) or pack UVP (P16) | 2.70 V / 43.20 V |
| Balancing | cell ≥ P8, spread > P62, cell ≥ P63 above the lowest | from 3.40 V |
| Cycle | Σ SOC decrease ≥ P81 | every 80 % |

Detailed derivation: [States and triggers](states-and-triggers.md).

---

## 7. Notable points and remarks

1. **P58/P59 when writing back:** writing P58 with 0x49, or the whole block (0xA1) with P58 at least 10 Ah away from the learned full capacity, resets the learned full capacity to P58. If the packs are still at the rated 280.00 Ah anyway (never re-learned), this has no consequences. P59 (50 Ah) is an old set value, not a measured value.
2. **Pack OVP off, CVL = pack OVP value:** intended or not, the combination works: the inverter charges up to 56.0 V, the cells are protected by the cell OVP of 3.65 V. At 56.0 V / 16 = 3.50 V on average there is a margin to 3.65 V as long as the cells do not drift far apart.
3. **P10 = 16 × P0 (55.20 V):** from 55.20 V every pack warns; with each warning pack the CCL drops by P50 / 2 (50 A in the example), as soon as all packs warn, 10 A total applies. With 4 packs this is 2.5 A per pack. This is at the same time the condition (< 3 A per pack) under which the SOC reset to 100 % takes effect.
4. **Balancing from 3.40 V (P8)** with start from 30 mV spread (P62): with well-matched cells balancing is almost never active. This matches the behaviour observed in practice.
5. **Cell heating off (BitGroup3 bit 6):** P36/P37 have no effect. If no heating foil is fitted, this is correct.
6. **Reverse polarity and connection fault (BitGroup5 bit 5/6) off:** the reverse polarity report is not implemented in the firmware at all; the connection fault would be a hardware input (P82 has no effect).
7. **Deep discharge lock P9 ineffective:** BitGroup6 bit 4 (automatic charge activation) disables the charge lock "cell ≤ 1.5 V". Anyone who wants the lock must switch off bit 4 (and then loses automatic charge activation).
8. **Standby self-shutdown after 48 h active** (BitGroup7 bit 1): a pack that sits in standby for 48 h without a charger at the port and whose highest cell is < 3.45 V shuts itself down. In a system with an inverter this practically never happens; after a longer shutdown of the inverter, however, the packs have to be woken up with the push button.
9. **Current limiter after charge overcurrent warning** (BitGroup6 bit 7): if 100 A (P50) flow for 5 s, the pack charges for 5 min (P71) only through the hardware limiter. With 50 A CCL per pack this is not reached in normal operation.
