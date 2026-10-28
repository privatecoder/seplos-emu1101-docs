# Seplos BMS 2.0/10E/V16 (EMU1101): Unofficial Firmware Changelog

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

No vendor changelog is included in the seven retained OEM packages. This changelog was reconstructed by disassembling and comparing the images in `../../vendor/firmware/`. Shifted addresses, literal pools and compiler reorderings have been filtered out; only **functional** changes are listed.

Confidence: **confirmed** = code difference is unambiguous · **probable** = effect inferred from the code · **assumption** = interpretation.

Details: [CAN protocols](../protocols/can.md) · [Modbus RTU](../protocols/modbus-rtu.md) · [Pylontech RS485](../protocols/pylontech-rs485.md) · [Undocumented commands](../protocols/seplos-ascii.md) · [Intra-pack protocol](../protocols/intra-pack.md) · [Firmware analysis](firmware-analysis.md)

## Overview

| Version | Build | Image | Summary |
|---|---|---|---|
| 16.04.06 `_9600` | 2022-09-24 | 48,096 B | Baseline: ASCII/intra-pack protocol, binary protocol, Pylontech RS485, Modbus (6 blocks), CAN 1–6 |
| 16.06.03 | 2023-04-12 | 47,980 B | new line 16.06; Modbus `0x9000` and FC04 `0x3100` (EPEver style); CCL immediately 0 when charging is blocked |
| 16.06.04 | 2023-06-13 | 49,900 B | Pylontech 0x60 with "SH-EnergyTCH Co.,Ltd"; Modbus `0x0001`×35/40 (Growatt?) and `0x1000` |
| 16.06.05 `_SP80` | 2023-09-16 | 49,900 B | **Special build** = 06.04 + **1 byte**: charge MOSFET off during "Intermittent recharge waiting" |
| 16.06.11 | 2024-07-13 | 52,452 B | **CAN MUST** (100 kbit/s); new charge logic (Charge Enable = CCL ≠ 0, heater current, derating on overvoltage); many new Modbus blocks |
| 16.06.12 | 2024-12-09 | 52,472 B | Bugfix temperature hysteresis; heating request independent of charge state; **CCL "active" mode also for multi-pack**; Pylontech ADR 0x02 |
| 16.06.13 | 2025-06-07 | 53,092 B | Modbus `0x3100` current fix + power; `0x9000` 26 registers; `0x001F` new; ASCII/binary tunnel 0xAA/0xAB |

**General:**
- The image only contains the version identifier `0x10 0x06` (16.06), for 04.06 `0x10 0x04`. The firmware itself does not know the patch number. *(confirmed)*
- Header, MCU (SWM181), hardware identifier (HW16) and peripheral usage are the same in all versions. *(confirmed)*
- The only official statement about changes is in the update guide in the 06.11 ZIP: "16.6" fixes communication problems (BatteryMonitor does not connect / with two packs only one is online at the inverter). This refers to the 16.06 line compared to 16.04.

---

## 16.06.13 (Build 2025-06-07)

### Modbus RTU
- **FC04 `0x3100`: current overflow fixed, power added** *(confirmed)*
  - 0x3102 current: up to 06.12 unsigned 16 bit · 10, overflow from ±327 A. Now int32, **clamped to ±32700**.
  - 0x3103/0x3104: up to 06.12 both a copy of the current. Now **power U·|I|/10 as u32, low word first**.
  - New: 0x3128 = 0, 0x3129 voltage 0.1 V, 0x312A current 0.1 A, 0x312B = 0. Length **40 → 44** registers.
- **FC03 `0x9000`: 21 → 26 registers** (+0, DVL, CVL, CCL, DCL). ⚠ The validator now accepts **only a count of 26**: a master that still reads 21 registers gets **exception 03**. *(confirmed)*
- **FC03 `0x001F` × 9 new:** 4 cell temperatures, MOS temp., ambient temp. (0.1 °C), CVL, CCL, DCL. Together with the old `0x0025` it forms the map 0x1F–0x27. *(confirmed)*

### ASCII protocol (RS485) and binary protocol
- **New: tunnel 0xAA/0xAB** between the RS485 ASCII host and the device on the binary port (display/dongle). 6 bytes can be passed through in both directions. *(confirmed; purpose is an assumption)*
  - ASCII CID2 0xAA (read) and 0xAB (write)
  - Binary commands 0xAA/0xAB
  - State machine `0x200000E8`, response via the new function `0x128E`
  - no timeout
- **Binary 0x64:** The acknowledgement now correctly carries CMD 0x64. Up to 06.12 it was wrongly 0x63. *(confirmed)*
- The ASCII dispatcher now consists of two jump tables (0x42–0x51, 0xA0–0xAB). Functionally this is unchanged. *(confirmed)*
- The shadow byte for the off/on edge (binary 0xA2/0xA3) is now at `0x200000E9`, because `0x200000E8` becomes the tunnel status. *(confirmed)*

### CAN
- Protocol 1 (Deye/Pylontech): **unchanged**. *(confirmed)*
- Victron/SMA: 0x35F capacity now rounded as a 32-bit sum; 0x379 = Σ measured full capacity instead of packs × nominal capacity. *(confirmed)*

### System
- Main loop restructured, many RAM variables above `0x200000C0` shifted by +8 bytes. *(confirmed)*
- Unchanged: intra-pack 0x5A, ASCII 0x42/0x44/0x47/0x49/0x4B/0x4D/0x4E/0xA0–0xA6, Pylontech RS485, "charging forbidden" ("Laden verboten") logic. *(confirmed)*

---

## 16.06.12 (Build 2024-12-09)

### Battery logic
- **Bugfix: hysteresis of the cell temperature alarms** (event 3) *(confirmed, code and consequence)*
  - **Up to 06.11:** The hysteresis state was stored in the reported byte `0x20000032`, which was then masked depending on the charge/discharge state. On a change charge ↔ discharge, the state of the other half was lost.
  - **From 06.12:** The evaluation works on `0x200000BB`, and this byte is now masked with BitGroup2 (06.12 `0x677C`–`0x6786`, 06.13 `0x6946`–`0x6952`); a copy masked by current direction is reported in `0x20000032`. **06.11 only:** the charge/discharge locks read the unmasked copy `0x200000BB` (06.11 `0x6584`–`0x658A`, mask only applied to `0x32` at `0x678A`); a cell temperature protection disabled via BitGroup2 therefore still opened the MOSFET there (correct in 06.05 and from 06.12). *(confirmed)*
  - *Consequence up to 06.11* (with P24 = 55 °C, P25 = 50 °C): charging at 56 °C → charge overtemperature protection. Brief discharge → charge bits including their memory are cleared. Charging again at 52 °C → **charging allowed**, although the temperature did not drop below 50 °C. From 06.12 the protection stays active until below 50 °C. Mirror-symmetrically for the discharge temperature protection.
- **Heating request** (event 4 bit 6): is now set from the temperature alone (≤ parameter 36 on, > 37 off). Up to 06.11 only during active charging/float. The condition "charging or charger detected" is checked from 06.12 by the heater output itself instead; heating therefore still only happens with a charger present, but the request is always reported. *(confirmed)*
- **"Float" logic** (system status bit 2, per documentation "Floating charge", actually "charger/external voltage detected at the port"; internally on-off bit 6) *(confirmed)*:
  - At port voltage ≥ pack voltage + 1.00 V, bit 2 is set immediately only when at least one MOSFET is off; the separate debounced path tests port ≥ pack − 0.20 V with a MOSFET off ([system-status conditions](states-and-triggers.md#charging--discharging--standby--off-system-status)).
  - Debounce 5 s instead of 30 s.
  - When charging, bit 2 is set; when discharging, it is cleared.

### CAN (affects Deye/protocol 1)
- **CCL calculation:** The choice "active/passive charge current limiting" (function switch `0x2F` bit 7) now applies **to any pack count**. In 06.11, systems with more than one chargeable pack always got half the charge OC warning per pack. Example: 2 packs, warning 61 A, "active" → 06.11: 61.0 A, **06.12: 102.0 A**. *(confirmed)*
- **Heater minimum CCL:** 5 A → **10 A per pack**. *(confirmed)*

### Pylontech RS485 (inverter port)
- System commands 0x60–0x63 (and 0x4F) additionally accept **ADR 0x02** (previously only 0x12). *(confirmed)*
- Response ADR = **echo of the requested address**. Previously it was "12" or the own DIP address. For broadcasts to FF the BMS now responds with "FF". *(confirmed)*

### Unchanged
- All Modbus blocks and all ASCII handlers. *(confirmed)*

---

## 16.06.11 (Build 2024-07-13)

### CAN
- **Protocol 7 "CAN:MUST" activated:** 29-bit IDs 0x30100/0x30200/0x30400/0x30500, **100 kbit/s**. *(confirmed)*
  - The frame code already existed as dead code since 06.03. In 06.05, value 7 still sent the protocol 1 set.
  - When switching to or from 7, the CAN controller is re-initialized (`0x9808`/06.13 `0x9A88`), via ASCII 0xA6 and binary 0x63.
  - An unchanged value is no longer stored.
- **0x35C "Charge Enable" = CCL ≠ 0** (previously: highest cell ≤ OVP + 30 mV). *(confirmed)*
- **CCL becomes 0 immediately** when the highest cell is > cell OVP + 30 mV (previously only via the Charge Enable bit). *(confirmed)*
- **New: heater minimum CCL** *(confirmed)*: With cell heating enabled (switch `0x2B` bit 6), highest cell temp. < **25 °C** and lowest ≤ parameter 36, CCL ≥ packs × 5 A applies. This is the origin of the new constant 2981 (= 25.0 °C).

### Modbus RTU
- **Separate FC04 map** (previously FC03 and FC04 served the same map), with new blocks *(confirmed)*:
  - `0x0000` × 21: serial number, temperatures
  - `0x0015` × 19: capacities, current in mA, bit fields. ⚠ **shifted by 1 byte**
  - `0x0028` × 20: cell voltages, extreme values
- **FC03 new** *(confirmed)*:
  - `0x0000` × 28 (constants `0x0641`, `0x3EC4`, device name, status, U/I/T, CCL/DCL)
  - Single registers `0x0033` (SOC), `0x0034` (capacity), `0x0070` × 1 (CVL), `0x0071`–`0x0074` (DVL, CCL, DCL, flags in Pylontech 0x35C format)
  - ⚠ These single registers respond with a **non-standard 16-bit byte count**.

### Balancing
- Balancing lockout "lowest cell too low": threshold **3.000 V → 2.000 V**. *(confirmed)*

### SOC and protection (compared to 06.04/06.05) *(confirmed)*
- **SOC := 0 % on undervoltage protection:** up to 06.05 only if the pack is currently discharging; from 06.11 always.
- **Enabling of the SOC voltage calibration:** up to 06.05 only from lowest cell 3.000 V, from 06.11 from 2.000 V.
- **Charge and discharge lockout** read the temperature protection bits from an unfiltered copy (`0x200000BB`) from 06.11. Up to 06.05 from the event 3 byte masked by state: while discharging, the charge lockout did not see the charge temperature bits; while charging, the discharge lockout did not see the discharge bits.
- Unchanged since 04.06: capacity learning, event 6 / intermittent recharge, system status thresholds, standby shutdown, button/switch, event 2 mask. Since 06.03 only shifted RAM addresses: current limiter, overcurrent reconnect/lockout, charge activation. The discharge lockout is unchanged except for the temperature source (above).

### ASCII protocol
- CID2 0xA3/0xA5 (write serial number strings): The length now comes from LENGTH (max. 30), the rest is padded with spaces. Previously 30 bytes were always read. *(confirmed)*

---

## 16.06.05 `_SP80` (Build 2023-09-16): Special build

- **Based on 16.06.04, exactly 1 byte changed** (offset `0x658A`: `movs r4,#0x71` → `#0x73`). *(confirmed)*
- In the "charging forbidden" ("Laden verboten") function (`0x6516`), **alarm event 6** is now checked with `0x73` instead of `0x71`. So **bit 1 "Intermittent recharge waiting"** additionally counts. *(confirmed)*
- **Effect:**
  - If the "Intermittent power supply" function has stopped charging at 100 % (resumption below parameter 80, e.g. 96 %), SP80 additionally **opens the charge MOSFET**.
  - In all other versions the MOSFET stays closed. There, only the inverter communication (pack counts as charge-blocked → CCL = 0 / Charge Enable = 0 when all packs wait, except heating minimum) and the charge current request block charging.
  - This matches the name "MOS off and Intermittent charging enabled on power on". The "enabled on power on" part is not a code change, but presumably a factory configuration. *(probable)*
- **Not distinguishable from 06.04** via protocol (same version identifier).
- ⚠ **Not adopted into the main line:** 06.11 to 06.13 use `0x71` again. *(confirmed)*

---

## 16.06.04 (Build 2023-06-13)

- **Pylontech RS485: new command CID2 0x60** (system basic info) *(confirmed)*: device name, **"SH-EnergyTCH Co.,Ltd"**, version, pack count, up to 4 serial numbers.
  - Bug: all with the own serial number.
  - With this, the BMS identifies itself to the inverter with SH-Energy as the manufacturer.
- **Modbus FC03 new** *(confirmed)*:
  - `0x0001` × 35 and × 40: status, SOC, U, I, temperature, CCL, capacities, version `0x1006`, cycles, SOH, CVL, alarm bits, DCL; presumably **Growatt**
  - `0x1000` × 21: state, enables, alarm words, U/I/SOC/SOH, extreme values with pack number, CVL/CCL/DCL/DVL, capacity
- Four interrupt stub functions from 06.03 removed again (cleanup). *(confirmed)*

---

## 16.06.03 (Build 2023-04-12): new line 16.06

- **Version identifier `10 06`.** *(confirmed)*
- **Pack bus baud rate 9600 → 19200** (UART0, RS485-1/2). *(confirmed)*
- **Modbus** *(confirmed)*:
  - The dispatcher now evaluates the full start address (04.06: only the low byte).
  - **New FC03 `0x9000` × 21:** BMS limits, parameters in 0.01 V / 0.01 A / 0.01 °C.
  - **New FC04 `0x3100` × 40:** real-time data, temperatures in 0.01 °C.
  - This presumably corresponds to **EPEver** "BMS-Link".
- **CAN:** If all packs are charge-blocked, the **CCL is set to 0 immediately** (previously slowly via the ramp). MUST frames present as dead code. *(confirmed)*
- **Major restructuring:**
  - about 100 functions changed, about 20 removed, more than 20 new
  - removed, among others, a large response builder from 04.06 (`0x1474`) that rounded cell voltages to 0.1 V *(legacy UART0 FC03-like response path; register semantics incomplete)*
  - RAM usage increases (stack top `0x200017D8` → `0x20001A90`)
  - *(confirmed)*

---

## 16.04.06 `_9600` (Build 2022-09-24): Baseline

- **ASCII protocol** (pack port):
  - 0x42, 0x44, 0x45, 0x47, 0x49, 0x4B, 0x4D, 0x4E, 0x51, **0x5A** (intra-pack), 0xA0–0xA6
  - Core frame layouts persist; version-specific dispatcher, serial-string length and acknowledgement changes are listed above
- **Additional UART0 CRC read path:** FC03-like, response builder `0x1474`, two-byte count; native replay confirmed. Removed in06.03, register semantics incomplete.
- **Binary protocol:** 0x47, 0xA1, 0x63, 0x64 (0x64 acknowledgement bug).
- **Pylontech RS485** (inverter port): individual42/44/51 at own address or FF;4F at own address (master additionally0x12); system61–63 only master at0x12.
- **Modbus RTU** (FC03 only, dispatcher compares only the low byte of the start address):
  - `0x0000` × 12 (**PACE V1.3**)
  - `0x0001` × 15 (zeros)
  - `0x0010` × 19
  - `0x0013` × 17
  - `0x0025` × 3
  - `0x0070` × 17 (cell voltages)
- **CAN:** protocols 1–6.
- "Charging forbidden" ("Laden verboten") logic with mask `0x71`.
- **Suffix `_9600` = pack bus (UART0, RS485-1/2) at 9600 baud.** From 16.06.03 the firmware initializes UART0 at **19200 baud**. The inverter RS485 (UART1, CAN socket) runs at 9600 in all versions. *(confirmed)*

---

## What has never changed (since 04.06)

- Intra-pack protocol 0x5A (32 bytes), telemetry 0x42, alarms 0x44, parameter block 0x47/0xA1
- Calibration 0xA0, history 0x4B, RTC 0x4D/0x4E, set capacity 0x49
- Pylontech 0x61/0x62/0x63
- Modbus PACE block
- Function switch masks, NTC table, CAN bit rate 500 kbit/s for protocols 1–6
