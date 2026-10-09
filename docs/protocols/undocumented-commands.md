# Seplos 10E / EMU1101: Undocumented Protocol Functions

Comparison between the official protocol PDFs and the actual behaviour of the firmware (as of **V16.06.13**, version differences noted in each case).

**Documentation checked** ([`specs/`](../../specs/)):
- [`Seplos MODBUS-ASCII Protocol V2.0 (2019-10-15).pdf`](<../../specs/Seplos MODBUS-ASCII Protocol V2.0 (2019-10-15).pdf>) (V2.0, 2019-10-15, 15 pages, series EMU10XX/11XX)

Despite the name "MODBUS-ASCII" it is not Modbus, but an **ASCII protocol according to YD/T1363.3** (`~ VER ADR CID1 CID2 LENGTH INFO CHKSUM CR`, VER 0x20, CID1 0x46). **Only CID2 0x42 (telemetry) and 0x44 (alarms)** are described in detail. 0x45, 0x47, 0x49, 0x4B, 0x4D, 0x4E, 0x4F, 0x51, 0xA0, 0xA1 and 0xA2 are listed by name only.

Confidence: **confirmed** = directly from the code · **probable** · **assumption**.

## Overview: What the firmware can do in addition

| Area | Docs | Firmware | Details |
|---|---|---|---|
| ASCII CID2 **0x5A** | – | **Intra-pack communication** (master ↔ slave), response with CID2 0x5A | [intra-pack.md](intra-pack.md) |
| ASCII 0x45 | name only | Force heating, on/off (also as master broadcast), clear history/counters, restart | §1.3 |
| ASCII 0x47 / 0xA1 | name only | read/write complete parameter block (169 bytes) | §1.4, §1.9 |
| ASCII 0x49 | name only | **sets only rated and remaining capacity** (parameters 58/59) | §1.5 |
| ASCII 0x4B | name only | History from I²C EEPROM, 500 records of 94 bytes each | §1.6 |
| ASCII 0x4D/0x4E | name only | read/set RTC (7 bytes) | §1.7 |
| ASCII 0x4F | name only | **no handler**: empty response | §1 |
| ASCII 0x51 | name only | returns, among other things, the **name of the active CAN protocol** | §1.8 |
| ASCII 0xA0 | name only | Calibration of current zero point / current / voltage | §1.10 |
| ASCII **0xA2–0xA5** | 0xA2 name only | read/write two 30-byte strings (serial number etc.) | §1.11 |
| ASCII **0xA6** | – | **select CAN inverter protocol (1–7)** | §1.12 |
| ASCII **0xAA/0xAB** | – | **new in 06.13**: tunnel to the binary port (6 bytes) | §1.13 |
| ASCII 0x42 | documented | **SOH fixed at 100 %**, "Reserved" fields populated, current 0 when idle | §1.1 |
| ASCII 0x44 | documented | Disconnection bytes always 0, event 7/8 filtered, last Reserved = system status | §1.2 |
| **Binary protocol** `0x55 … 0xAA` | – | separate UART (RS232/TTL, 9600 Bd), CRC-16/XMODEM, status push | §2 |
| **Pylontech RS485** (inverter port) | – | CID2 0x42/0x44/0x4F/0x51/**0x60–0x63** | [pylontech-rs485.md](pylontech-rs485.md) |
| **Modbus RTU** (inverter port) | – | Slave ID 1, FC 03/04, more than 20 register blocks | [modbus-rtu.md](modbus-rtu.md) |
| **CAN** | – | 7 inverter protocols | [can.md](can.md) |

---

## 1. ASCII protocol (pack/RS485 port, UART0)

### General *(confirmed)*

| Item | Behaviour |
|---|---|
| Port | UART0 (`0x50010000`), RS485 with direction pin (GPIO `0x50002000` bit 6) |
| Address | A frame is accepted if ADR = own DIP address **or 0xFF** (broadcast). In master mode only from the slave address currently being polled |
| VER | is **not** checked |
| Response | `~ 20 ADR 46 RTN LENGTH INFO CHKSUM CR` |
| Checks | CR missing → RTN 5; LENID/LCHKSUM wrong → RTN 3; CHKSUM wrong → RTN 2; wrong address → no response |
| Unknown CID2 | RTN **0x04** (e.g. 0x43, 0x46, 0x48, 0x4A, 0x4C, 0x50, 0x52–0x59, 0x5B–0x9F, 0xA7–0xA9, > 0xAB) |
| 0x4F | no handler → empty response with RTN 0 |
| Further RTN | **6** = data rejected, **8** = EEPROM/RTC/history error |
| Access protection | **none**: no password, no unlocking. Calibration, parameters and restart can also be called freely |

**Command set** (dispatcher `0x1132`):

| CID2 | Handler 06.13 | Since |
|---|---|---|
| 0x42 | `0x03A4` | 04.06 |
| 0x44 | `0x05B4` | 04.06 |
| 0x45 | `0x0A3C` | 04.06 |
| 0x47 | `0x06E8` | 04.06 |
| 0x49 | `0x09B4` | 04.06 |
| 0x4B | `0x0C2E` | 04.06 |
| 0x4D / 0x4E | `0x0CA0` / `0x0CF0` | 04.06 |
| 0x51 | `0x0ACA` | 04.06 |
| 0x5A | `0x10D6` | 04.06 |
| 0xA0 | `0x0BBE` | 04.06 |
| 0xA1 | `0x07C4` | 04.06 |
| 0xA2–0xA5 | `0x0D64`, `0x0DC0`, `0x0E20`, `0x0E46` | 04.06 |
| 0xA6 | `0x0EA6` | 04.06 |
| 0xAA, 0xAB | inline in the dispatcher | **06.13** |

### 1.1 CID2 0x42 (telemetry): deviations from the docs *(confirmed, unchanged since 06.03)*

| Field (docs) | Firmware |
|---|---|
| DATA FLAG | `00` |
| COMMAND GROUP | **own RS485 address** |
| Cell count M | parameter 65 |
| Temperature count N | fixed **6**: 4 cell sensors, ambient, power section (0.1 K) |
| **Current** | int16, 0.01 A. **Sent as 0 as long as neither charging nor discharging is active** (system status bit 0/1 = 0) |
| Custom P | fixed **10** |
| Battery capacity | **full capacity** (learned), 0.01 Ah |
| Rated capacity | parameter 58 |
| **SOH** | **fixed 1000 (= 100.0 %)**, not calculated |
| **Reserved 1** | int16 from `0x20000CA0+8`: **reference/offset channel (B) of the current measurement in mA**. If, with a calibrated zero point, it lies within ±301, it is subtracted from the measurement channel (drift compensation) *(confirmed)* |
| **Reserved 2** | **only when idle**: int16 from `0x20000C78+8` = **offset-corrected current in mA** (measurement channel A, from which the 0.01 A current is derived by rounded ÷ 10), otherwise 0 *(confirmed)* |
| **Reserved 3** | u32 `0xcc8+0x58` as u16; from 65,000 on, 6500 is sent. **Charged energy in 0.1 kWh** *(confirmed; reset to zero with 0x45 type 5)* |
| **Reserved 4** | u32 `0xcc8+0x5C`, same limitation. **Discharged energy in 0.1 kWh** *(confirmed)* |

Note on the current measurement (function `0x22CC`, *confirmed*): channel A (`0x20000C78`) is the measurement channel, channel B (`0x20000CA0`) a reference/offset channel, both in mA. If the zero point is calibrated (event 8 bit 4 = 0) and |B| ≤ 301, then A := A − B. The reported current is (A ± 5) / 10 in 0.01 A. Zero-point calibration (0xA0 sub 0) is only possible if both raw values are |x| < 1000. In practice: Reserved 1 is in the range of a few ±10 mA during operation (e.g. −33, 27).

### 1.2 CID2 0x44 (alarms): deviations from the docs *(confirmed)*

| Field | Firmware |
|---|---|
| Cell/temperature/current/voltage byte alarms | from `0x20000DDC` (current alarm is at +0x18 in RAM, voltage at +0x16) |
| Custom P | fixed **20** |
| Alarm event 1–5 | unfiltered (after function switch mask) |
| Alarm event 6 | `& 0x7F` |
| On-off state | `& 0x0F` |
| System status | `& 0x33`: **bit 2 is not reported**. According to the docs "Floating charge", actually an internal "charge path active" flag; it is included in 0x5A |
| **Disconnection 1/2** | **always 0x00** |
| Alarm event 7 | `& 0x30` (only auto/manual charge waiting) |
| Alarm event 8 | `& 0x3F` (internal "charging forbidden" bit 6 hidden) |
| Reserved 1–5 | 0 |
| **Reserved 6** | **copy of the system status** (`& 0x33`) |

### 1.3 CID2 0x45: Remote control *(confirmed)*

Request INFO, 3 bytes: `[0]` unused (sent as 0x00 by the master), `[1]` **type**, `[2]` **parameter**. Empty response, RTN 0. Unknown type → RTN 4.

| Type | Parameter | Effect |
|---|---|---|
| **0x03** | 0x10 | **Force heating ON**: counter `0x200000C8` = 3600. While it is running, on-off bit 3 (heater) is set. The counter runs in the 1 s main cycle, so the duration is **1 h** *(confirmed)* |
| 0x03 | ≠ 0x10 | Force heating OFF |
| **0x04** | 0x10 | **Switch on**: clear system status bit 5 ("off"). On the master additionally broadcast "0x10" to all slaves |
| 0x04 | ≠ 0x10 (master sends 0x1F) | **Switch off**: set system status bit 5. Master broadcast "0x1F" |
| **0x05** | – | **Clear history and reset counters**: EEPROM history header, record count, cumulative charged/discharged amount (`cc8+0x58/0x5C`) and **cycle count = 0** |
| **0x06** | – | **Restart** (interrupts off, briefly configure watchdog `0x50009000`, endless loop → WDT reset) |

- The master mirrors its on/off state to all slaves via **broadcast `~20FF4645…` with INFO `00 04 10` or `00 04 1F`** as soon as system status bit 5 changes (`0x8A24` detects the edge).
- No pack responds to broadcasts (ADR FF) with type 4.

### 1.4 CID2 0x47: Read parameters *(confirmed)*

Response INFO (169 bytes, without DATA FLAG):

| INFO byte | Content |
|---|---|
| 0 | own RS485 address |
| 1 | `0x3C` = 60 |
| 2–121 | parameters 0–59, u16 BE (`0x20001300…`) |
| 122 | `0x1B` = 27 |
| 123–149 | parameters 60–86, u8 (`0x200013F0…`) |
| 150 | `0x08` |
| 151–158 | function switches BitGroup0…7 (`0x20000028…2F`) |
| 159–168 | device name, 10 characters (without length byte) |

Meaning of each parameter and switch: [firmware-analysis.md, section 7](../firmware-analysis.md#7-parameters-and-function-switches). **Switch bytes 1–5 mask alarm events 2–6; BitGroup0 is not a mask (only bit 1: sensor plausibility check).**

### 1.5 CID2 0x49: Set parameters (capacities only) *(confirmed)*

Request INFO: `[0]` unused, `[1]` **parameter index**, `[2…3]` value u16 BE. **Only two indices are accepted**, all others → RTN 4:

| Index | Parameter | Effect |
|---|---|---|
| **58** (0x3A) | Rated capacity (0.01 Ah) | If remaining capacity ≤ value, **full capacity := value** and the coulomb counter maximum (`0x200015E0`) := value·3600. Otherwise RTN 6 |
| **59** (0x3B) | Remaining capacity | If full capacity ≥ value, the coulomb counter (`0x200015EC`) := value·3600. Otherwise RTN 6 |

All other parameters can only be changed via the complete block 0xA1. 0x49 only changes RAM; it is saved at the next storage occasion of flash block 6, e.g. SOC change > 5 % in standby or a new cycle (see firmware-analysis §8.2e). *(confirmed)*

### 1.6 CID2 0x4B: History *(confirmed)*

- **Storage:** external I²C EEPROM (device 0xA4), ring buffer with 128 bytes per record, **max. 500 records**, header at 0xFF00. Written by `0x5998`, at the interval of parameters 75/76 (operation/standby).
- **Request:** INFO `[1]` = 0 → oldest record, ≠ 0 → next one. No records → empty response. Read error → RTN 8.
- **Response (97 bytes):** `01`, flag "last record" (1/0), year u16 BE, followed by record bytes 1…93:

| Record offset | Content |
|---|---|
| 0–5 | Timestamp Y−2000, M, D, h, min, s |
| 6 | System status `& 0x33` |
| 7 | 0x0F |
| 8–13 | Alarm event 1–5, event 6 & 0x7F |
| 14–15 | 0 |
| 16 | Event 7 & 0x30 |
| 17 | Event 8 & 0x3F |
| 18–22 | 0 |
| 23 | 0x23 |
| 24–55 | 16 cell voltages (mV) |
| 56–63 | 4 cell temperatures (0.1 K) |
| 64–67 | Ambient and power section temperature (0.1 K) |
| 68–69 | Current 0.01 A (0 when idle) |
| 70–71 | Pack voltage 0.01 V |
| 72–75 | Remaining and full capacity 0.01 Ah |
| 76–77 | SOC 0.1 % |
| 78–79 | Rated capacity |
| 80–81 | Cycles |
| 82–83 | 1000 (SOH) |
| 84–85 | Port voltage |
| 86–93 | 0 |

### 1.7 CID2 0x4D / 0x4E: Time *(confirmed)*

Format 7 bytes: year u16 BE (2000+x), month, day, hour, minute, second.
- 0x4D reads the RTC.
- 0x4E sets it. Year ≤ 2000 → 2022. No plausibility check.
- Error → RTN 8.

### 1.8 CID2 0x51: Manufacturer info *(confirmed)*

32 bytes, without DATA FLAG:

| INFO byte | Content |
|---|---|
| 0–9 | Device name |
| 10–11 | Firmware version `10 06` |
| 12–31 | **Name of the active CAN protocol**, e.g. `CAN:PNG_DYE_Luxp_TBB`. If the index is not 2…7, protocol 1 is reported |

### 1.9 CID2 0xA1: Write parameter block *(confirmed)*

Request INFO, 169 bytes, counterpart to 0x47:
- `[1]` = **0x3C**, then 60 × u16 → buffer
- `[122]` = **0x1B**, then 27 bytes → buffer
- `[150]` = **0x08**, then 8 function switch bytes and 10 bytes device name → **live immediately**

Sequence:
1. A wrong marker → RTN 4.
2. Plausibility check `0x4C3C` (e.g. alarm < protection, limit values). Failure → **RTN 6**.
   - ⚠ Function switches and name have **nevertheless already been changed** in RAM in that case, but are not saved.
3. On success: transfer into the live tables and write to the **internal flash** parameter block (mirrored). The I²C EEPROM holds only the history.
4. If the new rated capacity deviates from the full capacity by ≥ 10.00 Ah, the **full capacity is reset to the rated capacity**.

### 1.10 CID2 0xA0: Calibration *(confirmed)*

Request INFO: `[0]` subcode, `[1…2]` reference value u16/s16 BE. Saved via `0x5174`.

| Sub | Function | Acceptance condition | clears event 8 |
|---|---|---|---|
| 0 | Current zero point | both current ADC raw values \|x\| < 1000 | bit 4 |
| 1 | Current gain (reference 0.01 A) | \|measured value − reference\| < 3.01 A | bit 3 |
| 2 | Voltage (reference cell voltage mV) | cell difference < 20 mV, \|avg. cell − ref\| < 30 mV, \|port voltage − ref·cells\| < 2 V | bit 2 |

Rejection → RTN 6. Unknown subcode → RTN 4.

### 1.11 CID2 0xA2–0xA5: Two 30-byte strings *(confirmed)*

| CID2 | Effect |
|---|---|
| 0xA2 / 0xA3 | read / write string 1 (`0x2000004C`): **pack serial number** *(probable; also output by Modbus FC04 `0x0000` and Pylontech 0x60)* |
| 0xA4 / 0xA5 | read / write string 2 (`0x2000006A`) *(assumption: BMS serial number or similar)* |

- Writing saves immediately (`0x53D8`).
- **From 06.11** 0xA3/0xA5 take the length from LENGTH (max. 30) and pad with spaces. Up to 06.05 exactly 30 bytes were always read.

### 1.12 CID2 0xA6: Set CAN inverter protocol *(confirmed)*

- Request INFO: 1 byte protocol number. **1…20** are valid, otherwise RTN 4. Names exist only for 1…7.

| No. | Name | Since |
|---|---|---|
| 1 | `CAN:PNG_DYE_Luxp_TBB` (Pylontech; Deye, Luxpower, TBB …) | 04.06 |
| 2 | `CAN:Growatt_SPF_SPH` | 04.06 |
| 3 | `CAN:Victron` | 04.06 |
| 4 | `CAN:SMA_SOFAR` | 04.06 |
| 5 | `CAN:GINLONG` | 04.06 |
| 6 | `CAN:Studer` | 04.06 |
| 7 | `CAN:MUST` | 06.11 |

- Sequence: index to `0x20000024`, `0x55` to `0x20000025`, save.
- **From 06.11:** When switching to or from 7, `0x9A88` is additionally called (CAN re-initialisation). An unchanged value is not saved.
- Counterpart in the binary protocol: command 0x63.

### 1.13 CID2 0xAA / 0xAB: Tunnel to the binary port (new in 06.13) *(sequence confirmed, purpose assumption)*

The BMS acts as a **gateway** between an RS485 ASCII host and the device on the binary port (display/dongle):

| Step | 0xAA ("read 6 bytes from device") | 0xAB ("write 6 bytes to device") |
|---|---|---|
| Host → BMS (ASCII) | `CID2 AA`, without INFO | `CID2 AB`, INFO = 6 bytes |
| BMS internal | `0x200000E8` = 1, **no immediate response** | 6 bytes → `0x200000EA…EF`, `E8` = 3 |
| BMS → device (binary) | `55 ADR AA 00 CRC AA` | `55 ADR AB 06 b0…b5 CRC AA` |
| Device → BMS (binary) | `55 ADR AA 06 b0…b5 CRC AA` → `E8` = 2 | `55 ADR AB 00 CRC AA` → `E8` = 4 |
| BMS → host (ASCII, function `0x128E`) | RTN 0, INFO = 6 bytes | RTN 0, empty INFO |

- There is **no timeout**: if the device does not respond, the host never gets a response.
- The 6 bytes are not evaluated in the BMS. *Assumption:* PIN/password or MAC of a Bluetooth/Wi-Fi dongle, or date/time of a display.

---

## 2. Binary protocol `0x55 … 0xAA` (UART2)

### 2.1 Physical layer

- UART2 (`0x50012000`), **9600 baud, 8N1**, **without RS485 direction control**, i.e. point-to-point (RS232/TTL). *(confirmed)*
- Active if function switch `0x2000002F` **bit 3** is set. *(confirmed)*
- *Assumption, well supported:* connection for an **LCD display or Bluetooth/Wi-Fi dongle** (RS232/"LCD" socket). The BMS continuously sends status frames, reports switching off/on, and the extended status message contains the list of all CAN protocol names together with the selection command.
- For comparison: ASCII runs on UART0 (`0x50010000`) with RS485 direction pin, Modbus and Pylontech RS485 on UART1 (`0x50011000`).

### 2.2 Frame *(confirmed)*

```
Format A (adressiert):  55 | ADR | CMD | LEN | DATA[LEN] | CRC_hi | CRC_lo | AA      (LEN+7 Byte)
Format B (ohne ADR):    55 | CMD | LEN | DATA[LEN] | CRC_hi | CRC_lo | AA
```

(Format A = addressed, LEN+7 bytes; format B = without ADR.)

- **Format A** applies to all responses. Format B applies to the spontaneous frames 0x46/0xA2/0xA3 when function switch `0x2F` **bit 4 = 0**. If bit 4 = 1, these are also sent in format A.
- ADR when sending = own DIP address. On reception ADR is **not** checked.
- **CRC = CRC-16/XMODEM** (polynomial 0x1021, init 0, not reflected, no XorOut), big-endian, over ADR … last data byte (format B: CMD … data). Check value "123456789" → `0x31C3`. Example: `55 01 AA 00 C5 85 AA`.
- **Errors:** The CMD byte of the response is replaced by the error code, LEN = 0:
  - **0x81** unknown command
  - **0x83** wrong marker
  - **0x87** length
  - **0x88** CRC
  - **0xE2** invalid value / check failed

### 2.3 Commands *(confirmed)*

| CMD | Direction | Data | Response / effect | Since |
|---|---|---|---|---|
| 0x47 | device → BMS | – | LEN 168: `3C` + 60×u16, `1B` + 27 bytes, `08` + 8 switches, 10 bytes name | 04.06 |
| 0xA1 | device → BMS | 158 bytes: `3C`+120, `1B`+27, `08`+8 (without name) | write parameters as ASCII 0xA1; OK → `A1`, LEN 0 | 04.06 |
| 0x63 | device → BMS | protocol 1…20 | set CAN protocol (as ASCII 0xA6). **From 06.11** special case 7/MUST with CAN re-initialisation | 04.06 |
| 0x64 | device → BMS | 1…20 | **Stub**: range check only, no effect. **Up to 06.12 bug: acknowledged with CMD 0x63, from 06.13 correctly 0x64** | 04.06 |
| 0xAA | device → BMS | 6 bytes | tunnel, state 2 (no binary response) | **06.13** |
| 0xAB | device → BMS | – | tunnel acknowledgement, state 4 | **06.13** |
| 0x46 | BMS → device | spontaneous | status frame (see below) | 04.06 |
| 0xA2 | BMS → device | spontaneous | once on **switching off** (system status bit 5: 0 → 1) | 04.06 |
| 0xA3 | BMS → device | spontaneous | once on **switching back on** (bit 5: 1 → 0) | 04.06 |
| 0xAA / 0xAB | BMS → device | spontaneous | tunnel requests (§1.13) | **06.13** |

**Sequence per main loop tick:** If a received frame is pending, it is processed. Otherwise the BMS sends exactly one spontaneous frame, with priority **A2 > A3 > tunnel > 0x46**. Edge detection uses a shadow byte: `0x200000E8` up to 06.12, `0x200000E9` from 06.13.

**Status frame 0x46:**
- **Short** (`0x761E`, format B, switch `0x2F` bit 4 = 0): `N`, N × cell mV, `06`, 4 cell temperatures, ambient, power section (0.1 K), current (0 when idle), pack voltage, remaining capacity, `03`, full capacity, cycles, port voltage, system status & 0x33, on-off & 0x0F, `06`, event 1–5, event 6 & 0x7F, RS485 address, slave count. **No SOC.** *(confirmed)*
- **Extended** (`0x77DC`, format A, bit 4 = 1), order *(confirmed)*; multi-byte values big-endian:
  1. `N`, N × cell mV
  2. `06`, 4 cell temperatures, ambient, power section (0.1 K)
  3. Current (0.01 A, 0 outside charging/discharging), pack voltage (0.01 V), remaining capacity (0.01 Ah)
  4. `06`, full capacity, **SOC** (0.1 %), rated capacity (P58), cycles, `03 E8` (SOH 100.0 %), port voltage
  5. Byte alarms: N × cell, 4 × cell temperature, ambient, power section, current, voltage
  6. System status & 0x33, on-off & 0x0F
  7. `08`, event 1–5, event 6 & 0x7F, event 7 & 0x30, event 8 & 0x3F
  8. Balancing mask (2 bytes), `00 00`
  9. **Name of the active CAN protocol** (20 bytes) – only this one, on every pack
  10. Device name (10 bytes), FW version `10 06`, CAN protocol number (u8), byte `0x200000A6`, constant `0x46`
  11. **Only master with slaves:** system block (max./min. cell voltage and temperature, total current, average voltage, Σ remaining and full capacity, system SOC, 1000, average port voltage, online bitmask of the packs, charge/discharge enable flags, OR of all alarm events). Otherwise 46 zero bytes; the length stays the same.

---

## 3. Further interfaces (separate files)

- **Pylontech RS485** on the inverter port (0x42/0x44/0x4F/0x51/0x60–0x63): [pylontech-rs485.md](pylontech-rs485.md)
- **Modbus RTU** on the inverter port: [modbus-rtu.md](modbus-rtu.md)
- **CAN**: [can.md](can.md)
- **Intra-pack** (0x5A): [intra-pack.md](intra-pack.md)

## 4. Version history (ASCII and binary)

| Item | 04.06 | 06.03–06.05 | 06.11 / 06.12 | 06.13 |
|---|---|---|---|---|
| ASCII commands 0x42…0xA6 | present | = | = | =, dispatcher as two jump tables |
| 0xA3 / 0xA5 | always 30 bytes | = | **length from LENGTH, space padding** | = |
| 0xA6 / binary 0x63 | without special case | = | **special case 7 (MUST), save only on change** | = |
| ASCII / binary 0xAA, 0xAB | – | – | – | **new (tunnel)** |
| Binary 0x64 | acknowledgement incorrectly 0x63 | = | = | **fixed** |
| All other handlers | – | semantically unchanged since 04.06 (only RAM addresses) | = | = |
