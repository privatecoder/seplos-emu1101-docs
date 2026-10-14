# Seplos BMS V2.0 / 10E (EMU1101): RS485 ASCII protocol ("MODBUS-ASCII"), reconstructed from the firmware

This description replaces the official Seplos PDFs ("MODBUS-ASCII Communication Protocol" / "Communication Protocol V2.0"). It is based **exclusively on the behavior of the firmware** (disassembly of V16.04.06 to V16.06.13), not on the Seplos documentation. Where the documentation differs, this is noted.

Confidence: **confirmed** = directly from the code · **probable** = inferred from data flow · **assumption**. Without a tag, *confirmed* applies.

> Despite its name, this is **not Modbus**. It is an ASCII protocol according to YD/T1363.3, which Pylontech also uses. A real Modbus RTU slave exists in addition, see [modbus-rtu.md](modbus-rtu.md).

---

## 1. Physical layer: sockets, UARTs, baud rates

The board has three sockets: **CAN**, **RS485-1** and **RS485-2**. Besides CAN, the CAN socket also carries a second RS485 bus.

| Socket | UART | Baud rate | Protocols | Who responds |
|---|---|---|---|---|
| **RS485-1 / RS485-2** (pack bus, intra-pack) | UART0 `0x50010000` | **19200** (from 16.06.03); **9600** in 16.04.06 ("_9600") | this ASCII protocol, **full command set** | Slaves always. The master (DIP 0) with slaves polls by itself and **does not respond** on this bus |
| **CAN socket, RS485 pair** (inverter bus) | UART1 `0x50011000` | **9600** (all versions) | this ASCII protocol with a **restricted command set** + Pylontech system commands + Modbus RTU | 0x42/0x44/0x51: every pack under its DIP address; 0x60–0x63 and Modbus: only the master |
| (internal) RS232/TTL | UART2 `0x50012000` | 9600 | binary protocol `0x55…0xAA` (see [undocumented-commands.md §2](undocumented-commands.md#2-binary-protocol-0x55--0xaa-uart2)) | – |

- Data format: 8 data bits, no parity, 1 stop bit.
- RS485 has direction switching (UART0: GPIO `0x50002000` bit 6).
- **Multi-pack practice:** On RS485-1/2 the master is itself the bus master and cannot be queried there. Via the RS485 pair of the CAN socket (9600 baud), **all packs including the master** can be read with 0x42/0x44/0x51.
- **Header of the `.ehex` file** `RS485Y19200N9600`: *assumption:* "19200" = pack bus/update port (the update tool uses 19200), "9600" = inverter bus.

---

## 2. Frame structure

```
SOI  VER  ADR  CID1  CID2/RTN  LENGTH  INFO       CHKSUM  EOI
'~'  2    2    2     2         4       LENID      4       CR
7Eh  ASCII hex (each byte as 2 characters)        ASCII   0Dh
```

| Field | Content | Firmware behavior |
|---|---|---|
| SOI | `~` (0x7E) | reception synchronizes on `~` |
| VER | `20` (V2.0) | **not checked** on reception; response always `20` |
| ADR | address 0x00…0x0F (DIP switch), `FF` = broadcast | see §3 |
| CID1 | `46` (LiFePO4 BMS) | **not checked** on reception; response always `46` |
| CID2 | command (request) or **RTN** (response) | exception: intra-pack response carries `5A` instead of RTN |
| LENGTH | LCHKSUM (4 bits) + LENID (12 bits) | see §2.1 |
| INFO | LENID ASCII characters = LENID/2 bytes | byte values as hex ASCII, multi-byte values big-endian |
| CHKSUM | 16 bits | see §2.2 |
| EOI | CR (0x0D) | CR missing → RTN 05 |

The firmware always sends hex digits **in uppercase** (`0x02EA`) and **only understands uppercase in requests**: lowercase letters are read as 0 (`0x0316`), and the request then fails the checksum. *(confirmed)*

### 2.1 LENGTH

- **LENID** = number of ASCII characters in INFO, i.e. 2 × number of bytes. 12 bits, maximum 4095.
- **LCHKSUM** = (−(D11..D8 + D7..D4 + D3..D0)) mod 16, i.e. sum of the three nibbles modulo 16, inverted, +1.
- LENGTH = LCHKSUM << 12 | LENID, sent as 4 hex characters.
- For LENID = 0, LENGTH = `0000`.

| INFO bytes | LENID | LENGTH |
|---|---|---|
| 0 | 0x000 | `0000` |
| 1 | 0x002 | `E002` |
| 9 | 0x012 | `D012` |
| 32 (0x51, 0x5A) | 0x040 | `C040` |
| 49 (0x44) | 0x062 | `8062` |
| 75 (0x42) | 0x096 | `1096` |
| 169 (0x47/0xA1) | 0x152 | `8152` |

The firmware checks LCHKSUM (error → RTN 03). On the pack port it also checks the character count (RTN 03); on the inverter port LENID is not compared with the actual length.

### 2.2 CHKSUM

**Sum of all ASCII characters** between SOI and CHKSUM (i.e. VER … INFO), **modulo 65536, two's complement**: `CHKSUM = (−Σ) & 0xFFFF`. Sent as 4 hex characters, high byte first.

Worked example (0x51 to address 1, without INFO):

```
Chars:    2  0  0  1  4  6  5  1  0  0  0  0
ASCII:   32 30 30 31 34 36 35 31 30 30 30 30   Σ = 0x0253
CHKSUM = (−0x0253) & 0xFFFF = 0xFDAD
Frame:   ~200146510000FDAD<CR>
```

> The Seplos documentation gives "Σ = 038EH → FC72H" as an example for `1203400456ABCEFE`. The actual character sum of this string is **0x038F** (→ `FC71`). The example in the documentation is therefore wrong. The address tables of the documentation (e.g. `~20014642E00201FD35`), on the other hand, are correct.

---

## 3. Addressing and response behavior

### Pack bus (RS485-1/2, UART0)
- A pack accepts a frame if **ADR = its own DIP address or `FF`**.
- **Master mode:** DIP 0 with at least one slave. The master polls the slaves itself (CID2 0x5A, §5.10; 150 ms per slave, a new round starts with the next 1 s cycle, so about every 2 s with 11 slaves). In this mode its main loop calls **only the polling, never the ASCII dispatcher** (`0x6264`–`0x628A`); the evaluation accepts only 0x5A responses. **On RS485-1/2 the master therefore does not answer any requests, not even between rounds.** It can only be read on the RS485 bus of the CAN socket (9600 baud). *(confirmed, verified in practice)*
- Response ADR = **always its own DIP address**, even for requests to `FF`. *(confirmed)*
- No pack responds to a broadcast `FF` with 0x45 type 4 (on/off).

### Inverter bus (CAN socket, UART1)

| CID2 | accepted ADR |
|---|---|
| 0x42, 0x44, 0x51 | own DIP address or `FF` |
| 0x4F | own DIP address; on the master additionally `12` (from 06.12 also `02`) |
| 0x60–0x63 | master only: `12` (from 06.12 also `02`) |
| all others | RTN 04 |

- Response ADR: up to 06.11 its own DIP address (special case request to `12` → `12`), **from 06.12 echo of the requested address**.

### Check order and return codes (RTN)

| Check / event | RTN |
|---|---|
| wrong address | **no response** |
| CR missing / framing error | 05 |
| LENID/LCHKSUM wrong | 03 |
| CHKSUM wrong | 02 |
| unknown CID2 | 04 |
| invalid subcode/type/index | 04 |
| data rejected (plausibility, limits) | 06 |
| EEPROM/RTC/history error | 08 |
| OK | 00 |

The documentation additionally lists 01 (VER), 07, E1–E4. **The firmware does not generate these codes.**

### Timing
- There are no documented minimum intervals. Empirical value (MQTT add-on): about 1 s between requests, otherwise erroneous responses occur.
- There is no authentication: all commands including calibration, parameters and restart can be executed without a password.

---

## 4. Command overview

| CID2 | Function | Pack bus | Inverter bus | Since |
|---|---|---|---|---|
| 0x42 | Telemetry | ✔ | ✔ | 04.06 |
| 0x44 | Alarms/status | ✔ | ✔ | 04.06 |
| 0x45 | Remote control | ✔ | – | 04.06 |
| 0x47 | Read parameters | ✔ | – | 04.06 |
| 0x49 | Set capacity | ✔ | – | 04.06 |
| 0x4B | Read history | ✔ | – | 04.06 |
| 0x4D / 0x4E | Read / set time | ✔ | – | 04.06 |
| 0x4F | Protocol version | ✔ (empty) | ✔ (empty) | 04.06 |
| 0x51 | Device info | ✔ | ✔ | 04.06 |
| 0x5A | Intra-pack data | ✔ | – | 04.06 |
| 0x60–0x63 | Pylontech system commands | – | ✔ (master) | 0x61–0x63: 04.06, 0x60: 06.04 |
| 0xA0 | Calibration | ✔ | – | 04.06 |
| 0xA1 | Write parameters | ✔ | – | 04.06 |
| 0xA2 / 0xA3 | Read / write string 1 (battery serial number) | ✔ | – | 04.06 |
| 0xA4 / 0xA5 | Read / write string 2 | ✔ | – | 04.06 |
| 0xA6 | Set CAN protocol | ✔ | – | 04.06 |
| 0xAA / 0xAB | Tunnel to binary port | ✔ | – | 06.13 |

In the INFO layouts below, the **INFO byte** counts (not the ASCII character). The ASCII offset within INFO is 2 × byte index.

---

## 5. Commands in detail

### 5.1 CID2 0x42: Telemetry

**Request:** INFO 1 byte "Command Group" (ignored; usually: the address). Example address 1: `~20014642E00201FD35<CR>`

**Response:** 75 bytes (LENGTH `1096`, for 16 cells)

| Byte | Content | Type / unit |
|---|---|---|
| 0 | DATA FLAG = `00` | |
| 1 | own address | |
| 2 | cell count M (parameter 65) | u8 |
| 3 … 2+2M | cell voltage 1…M | u16, mV |
| +0 | number of temperatures = **6** | u8 |
| +1…+8 | cell temperature 1–4 (with ≤ 8 cells: 3/4 = copy of 2) | u16, 0.1 K |
| +9…+10 | ambient temperature | u16, 0.1 K |
| +11…+12 | power stage / MOSFET temperature | u16, 0.1 K |
| … | **current**, + = charging. **0 as long as neither charging nor discharging is active** | s16, 0.01 A |
| … | pack voltage | u16, 0.01 V |
| … | remaining capacity | u16, 0.01 Ah |
| … | number of user-defined values = **10** | u8 |
| … | full capacity (learned) | u16, 0.01 Ah |
| … | SOC | u16, 0.1 % |
| … | rated capacity (parameter 58) | u16, 0.01 Ah |
| … | cycles | u16 |
| … | **SOH: always 1000** | u16, 0.1 % |
| … | port voltage (P+/P−) | u16, 0.01 V |
| … | "Reserved 1": reference/offset channel of the current measurement (drift compensation) | s16, mA |
| … | "Reserved 2": offset-corrected current with 1 mA resolution, **only when idle**, otherwise 0 | s16, mA |
| … | "Reserved 3": **charged energy** (sum of I·U while system status is "charging", 1 s cycle); from 65000 on, 6500 is sent | u16, 0.1 kWh |
| … | "Reserved 4": **discharged energy**, likewise | u16, 0.1 kWh |

Temperature in °C = (x − 2731) / 10. Fixed ASCII offsets for 16 cells (within INFO): cells 6, temperatures 72/76/80/84, ambient 88, power stage 92, current 96, voltage 100, remaining 104, full 110, SOC 114, rated 118, cycles 122, SOH 126, port 130, reserved 134/138/142/146.

### 5.2 CID2 0x44: Alarms and status

**Request:** as 0x42. Example: `~20014644E00201FD33<CR>`

**Response:** 49 bytes (LENGTH `8062`, for 16 cells)

| Byte | Content |
|---|---|
| 0 | DATA FLAG `00` |
| 1 | own address |
| 2 | cell count M |
| 3 … 2+M | byte alarm per cell |
| +0 | number of temperatures = 6 |
| +1…+4 | byte alarm cell temperature 1–4 |
| +5 / +6 | byte alarm ambient / power stage |
| +7 / +8 | byte alarm current / pack voltage |
| +9 | number of bit alarms = **20** |
| +10…+15 | **alarm event 1–5**, **event 6 & 0x7F** |
| +16 | **on-off status & 0x0F** |
| +17 / +18 | **balancing status cells 1–8 / 9–16** (§6.4) |
| +19 | **system status & 0x33**: bit 2 ("Float", actually an internal "charge path active" flag, §6.3) is masked out here |
| +20 / +21 | Disconnection 1/2: **always 0** |
| +22 | **alarm event 7 & 0x30** |
| +23 | **alarm event 8 & 0x3F** |
| +24…+28 | 0 |
| +29 | copy of the system status (& 0x33) |

**Byte alarms:** `00` normal, `01` lower limit, `02` upper limit, `F0` other. Bit alarms see §6.

### 5.3 CID2 0x45: Remote control

**Request:** INFO 3 bytes: `[0]` unused (`00`), `[1]` type, `[2]` parameter. **Response:** empty, RTN 00.

| Type | Parameter | Effect | Example (address 1) |
|---|---|---|---|
| 03 | `10` / other | force heating on for 3600 s = **1 h** (counter in the 1 s main cycle) / off | `~20014645A006000310FC6F` |
| 04 | `10` / other | **switch on / switch off** (clear/set system status bit 5 "Off"). The master sends this as a broadcast to all slaves on a state change | on: `~20014645A006000410FC6E`, off: `~20014645A00600041FFC58`; broadcast on/off: `~20FF4645A006000410FC43` / `~20FF4645A00600041FFC2D` |
| 05 | – | **clear history + reset cycle and cumulative counters** | |
| 06 | – | **restart** (watchdog) | `~20014645A006000600FC6D` |
| other | | RTN 04 | |

Regarding "Off" (type 4):
- The firmware keeps running afterwards. It detects the edges, sends the broadcasts and can be switched on again with type 4/`10`. *(confirmed)*
- "Off" opens the **discharge MOSFET** (discharge lock `0x7184`) and clears the discharging/standby states. Charging cancels "Off" at any time. *(confirmed)*
- Further triggers for "Off": button > 3 s, external switch (BitGroup7 bit 0, GPIO `0x50001000` bit 0 high; low switches back on) and the standby shutdown after parameter 77 (BitGroup7 bit 1). *(confirmed)*
- After "Off" via button or standby shutdown, the BMS saves its state to internal flash and sets GPIO `0x50001000` bit 1 to 0, provided no voltage is present at the port and the button is not pressed. That this drops the self-hold of the power supply (BMS completely off) is *probable*. Details: [states-and-triggers.md §14](../states-and-triggers.md#14-onoff-standby-shutdown-and-external-switch).
- Physical access to the button should be ensured before the first test.

**Only available on the pack bus (RS485-1/2).** The RS485 bus of the CAN socket knows no control commands; Modbus is also read-only there (FC 03/04).

### 5.4 CID2 0x47: Read parameters

**Request:** without INFO: `~200146470000FDA8<CR>`

**Response:** 169 bytes (LENGTH `8152`):

| Byte | Content |
|---|---|
| 0 | own address |
| 1 | `3C` (60) |
| 2–121 | parameters 0–59, each u16 |
| 122 | `1B` (27) |
| 123–149 | parameters 60–86, each u8 |
| 150 | `08` |
| 151–158 | function switches BitGroup0–7 |
| 159–168 | device name (10 ASCII) |

Meaning, RAM location and units of all parameters and switches: [firmware-analysis.md §7](../firmware-analysis.md#7-parameters-and-function-switches). Short form:
- cell voltage in mV, pack voltage in 10 mV, temperature in 0.1 K, current in 10 mA (discharging negative), capacity in 10 mAh
- byte parameters 60/61 (cell difference fault) in 10 mV, 62/63 (balancing difference) in mV
- **Switch byte k masks alarm event k+1** (k = 1…5); BitGroup0 is not a mask, only bit 1 has an effect (temperature sensor plausibility check). BitGroup6/7 are function switches (§6.6)

### 5.5 CID2 0x49: Set capacity

**Request:** INFO 4 bytes: `[0]` unused, `[1]` index, `[2..3]` value u16. **Only two indices:**

| Index | Effect | Rejection (RTN 06) |
|---|---|---|
| `3A` (58) | set rated/**full capacity** (0.01 Ah) | remaining capacity > value |
| `3B` (59) | set **remaining capacity** (coulomb counter) | full capacity < value |

Other indices → RTN 04. All other parameters can only be set via 0xA1.

### 5.6 CID2 0x4B: Read history

**Request:** INFO 2 bytes: `[0]` unused, `[1]` = `00` oldest record, otherwise next.
- Storage: ring buffer in an I²C EEPROM, **max. 500 records**. Written at once on every change of the system status or events 1–7 (partly masked), otherwise at the interval of parameter 75 (operation) / 76 (standby); such a record still holds the events from before the change. Details: [undocumented commands §1.6](undocumented-commands.md).

**Response:** 97 bytes (empty if no records exist):

| Byte | Content |
|---|---|
| 0 | `01` |
| 1 | last record reached (1/0) |
| 2–3 | year |
| 4–96 | record bytes 1…93 |

Record layout:

| Record offset | Content |
|---|---|
| 0–5 | Y−2000, M, D, h, min, s |
| 6 | system status & 0x33 |
| 7 | `0F` |
| 8–13 | event 1–5, event 6 & 0x7F |
| 16 | event 7 & 0x30 |
| 17 | event 8 & 0x3F |
| 23 | `23` |
| 24–55 | 16 cell voltages (mV) |
| 56–63 | 4 cell temperatures (0.1 K) |
| 64–67 | ambient and power stage temperature (0.1 K) |
| 68–69 | current |
| 70–71 | pack voltage |
| 72–75 | remaining and full capacity |
| 76–77 | SOC |
| 78–79 | rated capacity |
| 80–81 | cycles |
| 82–83 | `03E8` (SOH 100 %) |
| 84–85 | port voltage |

Read error → RTN 08.

### 5.7 CID2 0x4D / 0x4E: Time

- **Format:** 7 bytes: year u16 (e.g. `07EA` = 2026), month, day, hour, minute, second.
- **0x4D:** request without INFO (`~2001464D0000FD9B<CR>`), response 7 bytes.
- **0x4E:** INFO 7 bytes, response empty. Year ≤ 2000 → 2022. No plausibility check.
- Error → RTN 08.

### 5.8 CID2 0x4F: Protocol version

No handler: response RTN 00 without INFO. The version is only in the VER field (`20`).

### 5.9 CID2 0x51: Device info

**Request:** without INFO: `~200146510000FDAD<CR>`

**Response:** 32 bytes (LENGTH `C040`), **without** DATA FLAG:

| Byte | Content |
|---|---|
| 0–9 | device name (e.g. `EMU110110E`) |
| 10–11 | firmware version `10 06` = 16.06 (16.04.06: `10 04`). **The patch number is not transmitted** |
| 12–31 | name of the **active CAN protocol**, e.g. `CAN:PNG_DYE_Luxp_TBB` |

### 5.10 CID2 0x5A: Intra-pack data

- Response with **CID2 = `5A` instead of RTN**, INFO 32 bytes (LENGTH `C040`).
- Max./min. cell voltage and temperature, current (without idle zeroing), voltage, capacities, SOC, port voltage, event 1–8 (unfiltered), on-off, system status.
- Details: [intra-pack.md](intra-pack.md). Request: `~2002465A0000FD9C<CR>` (pack 2).

### 5.11 CID2 0xA0: Calibration

**Request:** INFO 3 bytes: `[0]` subcode, `[1..2]` reference value.

| Sub | Function | Reference | Acceptance condition | clears event 8 |
|---|---|---|---|---|
| 00 | current zero point | – | both converted current channels \|x\| < 1000 mA (a residual current stays as an offset) | bit 4 |
| 01 | current gain | reference current s16, 0.01 A | deviation < 3.01 A, no minimum current | bit 3 |
| 02 | voltage | reference cell voltage mV | cell difference < 20 mV, \|avg − ref\| < 30 mV, \|port P+/P− − ref·M\| < 2 V | bit 2 |

Rejection → RTN 06, unknown subcode → RTN 04. Stored in calibration flash block 2; no UART command reads the factors. Details: [undocumented commands §1.10](undocumented-commands.md).

### 5.12 CID2 0xA1: Write parameters

- **Request:** INFO 169 bytes, layout as the 0x47 response. Byte 0 is ignored, the markers `3C`/`1B`/`08` are mandatory (otherwise RTN 04).
- Plausibility check (alarm < protection, limits) → on error RTN 06.
- ⚠ Function switches and device name are applied **before the check**. With RTN 06 they are therefore changed in RAM, but not saved.
- On success, the data is written to the internal flash parameter block (mirrored). If the rated capacity deviates from the full capacity by ≥ 10 Ah, the full capacity is reset.

### 5.13 CID2 0xA2–0xA5: Two 30-byte strings

| CID2 | Function |
|---|---|
| 0xA2 | read string 1 (battery serial number, *confirmed*), response 30 bytes: `~200146A20000FDA0<CR>` |
| 0xA3 | write string 1 (saved immediately) |
| 0xA4 / 0xA5 | read / write string 2 |

Writing: up to 06.05 always 30 bytes are read; from 06.11 only LENGTH/2 bytes (max. 30), the rest is padded with spaces.

### 5.14 CID2 0xA6: Set CAN inverter protocol

- **Request:** INFO 1 byte: 1 PNG_DYE_Luxp_TBB (Pylontech/Deye/Luxpower), 2 Growatt_SPF_SPH, 3 Victron, 4 SMA_SOFAR, 5 GINLONG, 6 Studer, 7 MUST (from 06.11).
- 1…20 are accepted; 8…20 act like 1. Otherwise RTN 04.
- Saved immediately. When switching to or from 7, CAN is reinitialized (100 ↔ 500 kbit/s).
- 06.04/06.05 store 7 as well but run it as 1; after an update to ≥ 06.11 MUST then applies (see [undocumented commands §1.12](undocumented-commands.md)).
- Example protocol 1 to address 1: `~200146A6E00201FD24<CR>`

### 5.15 CID2 0xAA / 0xAB (from 06.13): Tunnel to the binary port

| CID2 | Effect |
|---|---|
| 0xAA | without INFO: request 6 bytes from the device on the RS232/binary port |
| 0xAB | INFO 6 bytes: send 6 bytes to the device |

- **No immediate response.** The response (RTN 00, for 0xAA with 6 bytes INFO) only comes once the device has responded. There is no timeout.
- Up to 06.12 → RTN 04. This can be used for version detection (see [firmware-analysis.md §10](../firmware-analysis.md#10-determining-the-patch-version-of-a-running-bms)).

---

## 6. Bit fields

### 6.1 Alarm events 1–6 (0x44, 0x5A, history)

| Event | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 1 Fault | voltage sensor | temperature sensor | current sensor | button | **cell difference** (≥ par. 60, off < par. 61) | charge switch | discharge switch | current limit switch |
| 2 Voltage | cell high alarm | cell **protection** (OVP) | cell low alarm | cell **protection** (UVP) | pack high alarm | pack **protection** (OVP) | pack low alarm | pack **protection** (UVP) |
| 3 Cell temp. | charge high alarm | charge high **protection** | charge low alarm | charge low **protection** | discharge high alarm | discharge high **protection** | discharge low alarm | discharge low **protection** |
| 4 Temp. | ambient high alarm | ambient high **protection** | ambient low alarm | ambient low **protection** | **power stage protection** | **power stage alarm** | cell heating requested | **severe fault** (latch, see below) |
| 5 Current | charge alarm | charge **protection** | discharge alarm | discharge **protection** | transient **protection** | short-circuit **protection** | transient **lockout** | short-circuit **lockout** |
| 6 Other | charger overvoltage | **Intermittent recharge waiting** | remaining capacity alarm | remaining capacity **protection** | charging locked (cell too low) | reverse polarity (**never set**) | output connection fault (GPIO input) | current limiter not ready (masked out in 0x44/0x5A) |

Additions from the code *(all confirmed, 06.12 = 06.13)*:
- **Event 1:** Only bit 1 (temperature sensor) and bit 4 (cell difference ≥ P60 × 10 mV, off < P61 × 10 mV) have their own logic with a function switch; bit 3 "button" = button pressed > 301 s.
- **Event 4 bit 7 "severe fault":** set after 5 s with temperature sensor fault, cell ≥ P4 + 50 mV, cell ≤ P6 − 200 mV, discharge protection at current ≤ P55 or charge overcurrent protection at current ≥ P54. It is only cleared by the mask BitGroup3 bit 7 = 0, so otherwise it remains until restart. With BitGroup3 bit 7 (and bit 6 off) it switches the heater/relay output (GPIO 11), *probably* intended as an alarm contact.
- **Event 6 bit 0:** port voltage ≥ P18 for > 5 s, off < P19. **Bit 4:** lowest cell ≤ P9, but only if BitGroup6 bit 4 = 0. **Bit 5 (reverse polarity):** no code sets it. **Bit 6:** GPIO `0x50001000` pin 10 low for ≥ 5 s, only with BitGroup5 bit 6; parameter 82 is not read. **Bit 7:** feedback of the current limiter stage (GPIO `0x50002000` pin 14).

For alarm/protection pairs, **both bits are usually set** during a protection event. Evaluators should give priority to protection or lockout. For event 4 bit 4/5 the following applies (verified in the code): bit 4 = protection (parameter 48), bit 5 = alarm (parameter 46).

### 6.2 On-off status

Bit 0 discharge MOSFET, 1 charge MOSFET, 2 current limiting, 3 heating, 4 precharge running (soft start, parameter 57), 5 discharge MOSFET just switched on (100 ms), 6 "external voltage at the port, MOSFET open" (auxiliary flag for system status bit 2). Bits 4–6 are masked out in 0x44. *(confirmed)*

### 6.3 System status

Bit 0 discharging, 1 charging, 2 "Float" (internal "charge path active" flag), 3 never set, 4 standby, 5 off, 6 discharge current ≥ 3 A, 7 charge current ≥ 3 A. In 0x44 only bits 0, 1, 4 and 5 are reported (`& 0x33`), in 0x5A all of them. Thresholds: [firmware-analysis §8.2c](../firmware-analysis.md#82c-system-status-all-bits-from-the-code).

**Bit 2 ("Floating charge" according to the Seplos documentation):**
- The firmware has **no float charging mode**: the charge voltage limit sent to the inverter is fixed (pack OVP parameter); there is no absorption or float phase.
- Bit 2 means **"charger or external voltage detected at the output"**. It depends on the difference **port voltage − pack voltage** (06.13 `0x20000D16` = `cc8+0x4E`, 0.01 V). From 06.12: set immediately when charging (bit 1) or port ≥ pack + 1.00 V; when idle it follows, with 5 s debouncing, the condition "**at least one MOSFET off** and port ≥ pack − 0.20 V" (on-off bit 6). If both MOSFETs are on, it is cleared after 5 s. Up to 06.11 it was only set after 30 s. *(confirmed: code 06.12 `0x856E`, 06.13 `0x87DA`, difference from `0x1CFA`; consistent with 24 captured frames)*
- Bit 2 is used for heating (heating only when charging or when a charger is detected) and for the standby shutdown (no shutdown as long as external voltage is present).
- In **0x44 bit 2 is masked out** (`& 0x33`). In **0x5A (byte 31)** the system status is included in full, i.e. including bit 2.
- The Seplos designation is misleading. For evaluations the bit is of little use.

### 6.4 Balancing (0x44 byte +17/+18, RAM `0x20000006/07`)

Bit n = cell n+1 is **currently being balanced**. The mask actually passed to the measurement/balancing IC is reported. When it is ≠ 0 is described in §7.

### 6.5 Alarm events 7 and 8

| Event | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 7 | **balancing active** | **balancing locked / not needed** | **balancing time limit reached** | **balancing locked due to ambient temp.** | **charge activation automatic** (window open) | **charge activation manual** (after switch-on) | **charging via current limiter from 10 A** | **current limiting after charge overcurrent warning** |
| 8 | EEPROM error | RTC error | voltage not calibrated | current not calibrated | zero point not calibrated | **RTC time invalid** (bit 7 of RTC register 2, I²C 0xA2) | **charging forbidden** (controls charge MOSFET) | in 0x5A: GPIO pin 9 high |

In 0x44 only event 7 bits 4/5 and event 8 bits 0–5 are visible. **The balancing bits of event 7 can only be seen in the intra-pack response 0x5A** (byte 29, unfiltered).

### 6.6 Function switches BitGroup6 and BitGroup7 *(all confirmed)*

| BitGroup6 (`0x2E`) | Function |
|---|---|
| 0 | **balancing on** |
| 1 | balancing also when idle (1) or only when charging (0); never when discharging |
| 2 | time limit: balancing without charging stops after parameter 64 hours, until the next charge |
| 3 | balancing lock on ambient temperature warning/protection |
| 4 | **automatic charge activation** (parameters 72–74); at the same time **disables** the charge lock "cell < parameter 9" (event 6 bit 4) |
| 5 | **manual charge activation** once after switch-on |
| 6 | charging from 10 A immediately via the current limiter (event 7 bit 6) |
| 7 | current limiter after charge overcurrent warning for parameter 71 minutes (event 7 bit 7) |

| BitGroup7 (`0x2F`) | Function |
|---|---|
| 0 | external on/off switch (GPIO `0x50001000` pin 0, high = off) |
| 1 | **standby shutdown** after parameter 77 hours |
| 2 | no function (no reader) |
| 3 | binary protocol on RS232/TTL |
| 4 | binary protocol format A (extended) |
| 5 | ignore DIP address, address via pulse chain (GPIO 7/8/9), master adjusts slave count *(hardware interpretation probable, see firmware-analysis §8.2d)* |
| 6 | no function (no reader) |
| 7 | CCL mode: 1 = parameter 50 − 10 A, 0 = parameter 50 / 2 |

Details on all function switches: [configuration-parameters.md §5](../configuration-parameters.md#5-function-switches-bitgroup07).

---

## 7. Passive balancing: how it works (06.13 `0x653C`/`0x205A`)

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

## 8. Example frames (calculated, checksums correct)

| Purpose | Frame |
|---|---|
| Telemetry pack 0 | `~20004642E00200FD37` |
| Telemetry pack 1 | `~20014642E00201FD35` |
| Alarms pack 1 | `~20014644E00201FD33` |
| Parameters pack 1 | `~200146470000FDA8` |
| Device info pack 1 | `~200146510000FDAD` |
| Time pack 1 | `~2001464D0000FD9B` |
| Serial number pack 1 | `~200146A20000FDA0` |
| History oldest record pack 1 | `~2001464BC0040000FCC6` |
| Broadcast switch on | `~20FF4645A006000410FC43` |
| Intra-pack request pack 2 | `~2002465A0000FD9C` |

Each followed by a terminating CR (0x0D).

## 9. Deviations from the Seplos documentation (short list)

1. Not Modbus. VER and CID1 are not checked. RTN 01/07/E1–E4 never occur.
2. The checksum calculation example in the documentation is wrong (0x038F instead of 0x038E).
3. 0x42: SOH fixed at 100 %; current 0 when idle; all four "Reserved" fields are used.
4. 0x44: Disconnection always 0; system status without bit 2 ("Float", actually an internal "charge path active" flag, §6.3); event 7/8 masked; last reserved = system status.
5. Undocumented commands: 0x5A, 0xA3–0xA6, 0xAA/0xAB. Documented commands that are only mentioned by name (0x45, 0x47, 0x49, 0x4B, 0x4D, 0x4E, 0x51, 0xA0–0xA2): see §5.
6. Two buses with different command sets and different baud rates (19200 / 9600). The documentation states 9600 across the board.
7. Event 4 bits 4/5 and event 5 bits 4–7 have, in practice, the meaning given above (protection/alarm or protection/lockout).
