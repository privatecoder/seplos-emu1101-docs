# Seplos 10E / EMU1101: Pylontech RS485 (ASCII) on the inverter port

On the inverter-side RS485 interface (UART1), the firmware answers, in addition to **Modbus RTU**, also **Pylontech-style ASCII frames** (`~20 ADR 46 CID2 …`, same frame as the Seplos protocol). This is not documented. The basis is the disassembly of 04.06 to 06.13; addresses apply to 06.13.

Confidence: **confirmed** = code · **probable** · **assumption** (among other things, Pylontech semantics from memory, not checked against a Pylontech PDF).

---

## 1. Reception, checking, addressing *(confirmed)*

- The main loop (`0x628E`) passes every received frame first to the ASCII dispatcher `0x2AF2` (only if the first character is `~`), then to Modbus `0x45AC`. Both share buffer and UART.
- Frame check (`0x28F0`):

| Check | Reaction |
|---|---|
| ADR does not match | **no response** |
| CR missing | RTN 0x05 |
| LCHKSUM wrong | RTN 0x03 |
| CHKSUM wrong | RTN 0x02 |
| CID2 unknown | RTN 0x04 |
| VER, CID1, LENID = actual length | are **not** checked |

- **Accepted addresses:**

| CID2 | 04.06 – 06.11 | from 06.12 |
|---|---|---|
| **0x60–0x63** (system commands) | only ADR **0x12**, only on the **master** (DIP 0, `0x200000F7.7`) | ADR **0x02 or 0x12**, master only |
| 0x4F | own DIP address, on the master additionally 0x12 | additionally 0x02 |
| 0x42 / 0x44 / 0x51 | own DIP address or 0xFF | = |

- **The INFO of the request is never evaluated.** Command group or pack number are ignored.
- **Response header** (`0x2A40`): `~ 20 ADR 46 RTN LENGTH INFO CHKSUM CR`
  - **up to 06.11:** ADR = `"12"` if the request was sent to 0x12, otherwise the own DIP address
  - **from 06.12:** ADR = **echo of the requested address** (i.e. also "02" or "FF"). Became necessary due to the new address 0x02. *(reason: probable)*

---

## 2. Commands

| CID2 | Handler | Content | Since |
|---|---|---|---|
| 0x42 | `0x03A4` | **Seplos v2.0 telemetry of the own pack** (same function as on the pack port). Not the Pylontech format, only the frame is the same | 04.06 |
| 0x44 | `0x05B4` | Seplos v2.0 alarms of the own pack | 04.06 |
| 0x4F | – | RTN 0, empty INFO | 04.06 |
| 0x51 | `0x0ACA` | device name (10), version `10 06`, **name of the active CAN protocol** (20) in the manufacturer field | 04.06 |
| **0x60** | `0x2600` | system basic info, see 2.1 | **06.04** |
| **0x61** | `0x26A8` | system analog values, see 2.2 | 04.06 |
| **0x62** | `0x278C` | system alarms, see 2.3 | 04.06 |
| **0x63** | `0x2882` | charge/discharge management, see 2.4 | 04.06 |

Source abbreviations:
- **S** = system values `0x2000164C`
- **R** = extreme values `0x20001634`
- **P** = pack numbers `0x20001627`
- **A** = OR of the alarm events of all packs `0x2000161E`
- **M** = own measured values `0x20000CC8`

The structures are described in [modbus-rtu.md, section 2](modbus-rtu.md#2-data-source-system-aggregate-0x2000164c). All values are big-endian.

### 2.1 CID2 0x60: System basic info *(confirmed)*

| INFO byte | Content |
|---|---|
| 0–9 | device name (`EMU110110E`) |
| 10–29 | **"SH-EnergyTCH Co.,Ltd"** |
| 30–31 | version `10 06` |
| 32 | pack count (configured, **not limited to 4**) |
| from 33 | max. 4 entries of 16 bytes each: `'0'+i` + 15 characters serial number |

⚠ **Bugs:**
- All entries contain **the same (own) serial number** (`0x2000004C`).
- With more than 4 packs, the count byte is greater than the number of entries.

### 2.2 CID2 0x61: System analog values (49 bytes) *(fields confirmed; Pylon names assumption)*

| Byte | Field | Source | Unit |
|---|---|---|---|
| 0–1 | system voltage | S+0x10 ×10 (average) | mV |
| 2–3 | system current | S+0x0C ×10, limited to ±32700, + = charging | s16, 10 mA |
| 4 | SOC | system | % |
| 5–6 / 7–8 | cycles average / max | **own pack only** (both identical) | |
| 9 / 10 | SOH average / min | **fixed 100** | % |
| 11–12 / 13–14 | highest cell voltage / location (0x00, pack no.) | R+0 / P[0] | mV |
| 15–16 / 17–18 | lowest cell voltage / location | R+2 / P[1] | mV |
| 19–20 | average cell temperature = **(max+min)/2** | R+4, R+6 | 0.1 K |
| 21–22 / 23–24 | highest cell temperature / location | R+4 / P[2] | 0.1 K |
| 25–26 / 27–28 | lowest cell temperature / location | R+6 / P[3] | 0.1 K |
| 29–38 | MOSFET temp. average/max/location/min/location | **power stage temp. of the own pack** (all three identical); location fields = P[2]/P[3] reused | 0.1 K |
| 39–48 | BMS temp. average/max/location/min/location | **ambient temp. of the own pack** | 0.1 K |

The temperatures are transmitted in 0.1 K, without conversion.

### 2.3 CID2 0x62: System alarms (4 bytes) *(confirmed)*

| Byte | Bit | Condition |
|---|---|---|
| 0 | 7 | **never** (pack overvoltage is not reported) |
| 0 | 6 | pack undervoltage (Ev2 b6\|b7) |
| 0 | 5 | highest cell > cell OVP + 30 mV |
| 0 | 4 | cell undervoltage (Ev2 b2\|b3) |
| 0 | 3 | overtemperature (Ev3 & 0x33) |
| 0 | 2 | undertemperature (Ev3 & 0xCC) |
| 0 | 1 | MOS/power stage overtemperature (Ev4 b4\|b5) |
| 0 | 0 | cell difference fault (Ev1 b4) |
| 1 | 7 | temperature sensor fault (Ev1 b1) |
| 1 | 6 | charge overcurrent protection (Ev5 b1) |
| 1 | 5 | discharge OC/short circuit (Ev5 b3–7) |
| 1 | 4 | pack communication fault (`0x20000000` bit 3) |
| 2–3 | – | **always 0** (*assumption:* Pylon "protection" bytes, i.e. as with CAN 0x359, never protection) |

### 2.4 CID2 0x63: Charge/discharge management (9 bytes) *(confirmed)*

| Byte | Content | Unit |
|---|---|---|
| 0–1 | CVL (parameter 14) | mV |
| 2–3 | DVL (parameter 12) | mV |
| 4–5 | CCL | 0.1 A |
| 6–7 | DCL, **negative** | s16, 0.1 A |
| 8 | flags: 0x80 = cell ≤ OVP + 30 mV ("Charge enable"), 0x40 = discharging possible, 0x20 = SOC ≤ 9 %, 0x10 = full charge request (never set) | bits |

⚠ **Deviations from CAN 0x35C** *(confirmed)*:
- "Charge enable" can be 1 even though CCL = 0.
- The force-charge bits are **shifted by one bit** compared with 0x35C: the flag "SOC ≤ 5 %" is **not reported at all**. Below 5 % SOC (where the 9 % flag is cleared), **no forced charge** is therefore requested. Probably an off-by-one bug.

---

## 3. Version history *(confirmed)*

| Version | Change |
|---|---|
| 04.06 | 0x42, 0x44, 0x4F, 0x51, 0x61, 0x62, 0x63; Pylon address only 0x12 |
| 06.04 | **new 0x60** (system basic info, "SH-EnergyTCH Co.,Ltd") |
| 06.05 | identical to 06.04 |
| 06.11 | unchanged |
| **06.12** | **additional address 0x02** (for 0x60–0x63 and 0x4F); response ADR = **echo** of the request |
| 06.13 | RAM relocation only |

0x61, 0x62 and 0x63 have been unchanged in content since 04.06.

## 4. Which inverters? *(assumption)*

- The commands 0x60–0x63 with ADR 0x12 (group 1, address 2) correspond to the **Pylontech RS485 system protocol**.
- Most likely are off-grid devices without CAN: **Growatt SPF**, Voltronic/Axpert clones (BMS option "PYL"), MUST.
- Luxpower and Deye ("PYLON 485") are possible, but Deye low-voltage hybrids practically always run via CAN (see [can.md](can.md)).
- The address 0x02 added in 06.12 points to a further inverter type or a further firmware family.
