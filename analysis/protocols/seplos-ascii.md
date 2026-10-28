# Seplos BMS 2.0/10E/V16 (EMU1101): RS485 ASCII protocol ("MODBUS-ASCII"), reconstructed from the firmware

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The original V16.04.06–V16.06.13 firmware implements the protocol described here. Code behavior is the reference; differences from the vendor specification are identified below.

The [Seplos MODBUS-ASCII Protocol V2.0 specification](<../../vendor/docs/protocol%20specs/Seplos%20BMS%20Modbus-ASCII%20Protocol%20RS485%20V2.0%20%282019-10-15%29.pdf>) (2019-10-15, 15 pages, EMU10XX/11XX series) describes only 0x42 and 0x44 in detail. It lists 0x45, 0x47, 0x49, 0x4B, 0x4D, 0x4E, 0x4F, 0x51, 0xA0, 0xA1 and 0xA2 by name.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2, inverter protocols and available monitoring/service paths. Availability depends on the **active requester on each bus**, not the number of sockets or gateways.

Confidence: **confirmed** = directly from the code · **probable** = inferred from data flow · **assumption**. Without a tag, *confirmed* applies.

This page describes the **original firmware**. [UART write capabilities](../../mod/docs/firmware/uart-write-capabilities.md) compares its writable values with MAINT1.5.3 and MAINT1.6.3; their UART1 extensions are separate from the OEM command set.

> Despite its name, this is **not Modbus**. It is an ASCII protocol according to YD/T1363.3, which Pylontech also uses. A real Modbus RTU slave exists in addition, see [modbus-rtu.md](modbus-rtu.md).

---

## 1. Physical layer: sockets, UARTs, baud rates

The board has three RJ45 communication sockets: **CAN**, **RS485-1** and **RS485-2**. Besides CAN, the CAN socket also carries a second RS485 bus.

| Socket | UART | Baud rate | Protocols | Who responds |
|---|---|---|---|---|
| **RS485-1 / RS485-2** (pack bus, intra-pack) | UART0 `0x50010000` | **19200** (from 16.06.03); **9600** in 16.04.06 ("_9600") | this ASCII protocol, **full command set** | Slaves always. The master (DIP 0) with slaves polls by itself and **does not respond** on this bus |
| **CAN socket, RS485 pair** (inverter bus) | UART1 `0x50011000` | **9600** (all versions) | this ASCII protocol with a **restricted command set** + Pylontech system commands + Modbus RTU | 0x42/0x44/0x51: every pack under its DIP address; 0x60–0x63 and Modbus: only the master |
| (internal) RS232/TTL | UART2 `0x50012000` | 9600 | binary protocol `0x55…0xAA` (see [binary display protocol](binary-display-protocol.md)) | – |

- Data format: 8 data bits, no parity, 1 stop bit.
- RS485 has direction switching (UART0: GPIO `0x50002000` bit 6).
- **Multi-pack practice:** On RS485-1/2 the master is itself the bus master and cannot be queried there. Via the RS485 pair of the CAN socket (9600 baud), **all packs including the master** can be read with 0x42/0x44/0x51, provided their UART1 pairs are actually interconnected and no inverter/other requester independently polls UART1. The UART0 daisy-chain alone does not connect UART1.
- **Header** `RS485Y19200N9600` is identical in all seven images and does not prove operating or bootloader baud rates. App rates come from initialization code; the 04.06-9600 bootloader rate remains unverified.

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
- **Master mode:** DIP 0 with at least one slave. The master polls the slaves itself (CID2 0x5A, §5.10; 150 ms per slave, a new round starts with the next 1 s cycle, so about every 2 s with 11 slaves). In this mode its main loop calls **only the polling, never the ASCII dispatcher** (`0x6264`–`0x628A`); the evaluation accepts only 0x5A responses. **On RS485-1/2 the master therefore does not answer any requests, not even between rounds.** Its pack telemetry can still be read over a free, correctly wired UART1 bus; local UART2 remains available. *(confirmed, verified in practice)*
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

The UART1 dispatcher is `0x2AF2` (`0x2B0E–0x2B7A`): unsupported 0x47 ends in RTN 04 at `0x2B3E`. Its 230-character receive limit (`0x24E4–0x24F8`) already excludes the approximately 358-character 0xA1 frame. No command proxies parameter reads or writes to slaves; each addressed pack handles supported reads locally. [Local display access](binary-display-protocol.md#4-own-pack-only-no-parameter-proxy-in-a-multi-pack-bank) remains available during polling.

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

The documentation additionally lists 01 (VER), 07, E1–E4. **The firmware does not generate these codes.** Unknown command examples include 0x43, 0x46, 0x48, 0x4A, 0x4C, 0x50, 0x52–0x59, 0x5B–0x9F, 0xA7–0xA9 and commands above 0xAB; 0x4F is the empty-success exception.

### Timing
- The OEM protocol PDF defines no request interval. On UART1 the configured receive timeout is nominally **104.17 ms at 9600 baud**; foreign traffic followed too closely by an addressed query can merge into one receive buffer. Start with **200 ms after a complete answer before the next UART1 query**, one outstanding query and one coordinated host; the [receive-gap reference](uart1-receive-gap-and-buffer-ownership.md) explains the emulator evidence, buffer-ownership tradeoff and limits. This is a practical margin, not a guaranteed maximum processing time or a timing rule measured for UART0. The historical MQTT add-on observation was roughly 1 s between queries; it is not a universal protocol minimum.
- There is no authentication: all commands including calibration, parameters and restart can be executed without a password.

---

## 4. Command overview

| CID2 | Function | Pack bus | Inverter bus | Since | Handler in 06.13 |
|---|---|---|---|---|---|
| 0x42 | Telemetry | ✔ | ✔ | 04.06 | `0x03A4` |
| 0x44 | Alarms/status | ✔ | ✔ | 04.06 | `0x05B4` |
| 0x45 | Remote control | ✔ | – | 04.06 | `0x0A3C` |
| 0x47 | Read parameters | ✔ | – | 04.06 | `0x06E8` |
| 0x49 | Set capacity | ✔ | – | 04.06 | `0x09B4` |
| 0x4B | Read history | ✔ | – | 04.06 | `0x0C2E` |
| 0x4D / 0x4E | Read / set time | ✔ | – | 04.06 | `0x0CA0 / 0x0CF0` |
| 0x4F | Protocol version | ✔ (empty) | ✔ (empty) | 04.06 | no handler |
| 0x51 | Device info | ✔ | ✔ | 04.06 | `0x0ACA` |
| 0x5A | Intra-pack data | ✔ | – | 04.06 | `0x10D6` |
| 0x60–0x63 | Pylontech system commands | – | ✔ (master) | 0x61–0x63: 04.06, 0x60: 06.04 | UART1 dispatcher |
| 0xA0 | Calibration | ✔ | – | 04.06 | `0x0BBE` |
| 0xA1 | Write parameters | ✔ | – | 04.06 | `0x07C4` |
| 0xA2 / 0xA3 | Read / write string 1 (battery serial number) | ✔ | – | 04.06 | `0x0D64 / 0x0DC0` |
| 0xA4 / 0xA5 | Read / write string 2 | ✔ | – | 04.06 | `0x0E20 / 0x0E46` |
| 0xA6 | Set CAN protocol | ✔ | – | 04.06 | `0x0EA6` |
| 0xAA / 0xAB | Tunnel to binary port | ✔ | – | 06.13 | inline |

The UART0 dispatcher is `0x1132`; in 06.13 it uses two jump tables.

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

The current-measurement function `0x22CC` uses channel A (`0x20000C78`, measurement) and channel B (`0x20000CA0`, reference/offset), both in mA. Reserved 1 reads B at `+8`; when zero calibration is valid (event 8 bit 4 clear) and |B| ≤ 301 mA, the firmware subtracts B from A. Reserved 2 reads the corrected A at `+8`, only while idle. The reported 0.01 A current is rounded as `(A ± 5) / 10`; neither charging nor discharging means system-status bits 0/1 are both clear. Typical observed B values are a few tens of mA, such as −33 and 27.

Reserved 3/4 read u32 energy totals at `0x20000CC8+0x58/+0x5C` and encode them as u16 with the 65000-to-6500 fallback above. Remote-control type 5 resets both totals. These 0x42 field deviations are confirmed unchanged since 06.03.

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

**Byte alarms:** `00` normal, `01` lower limit, `02` upper limit, `F0` other. They come from `0x20000DDC`; the current alarm is at RAM offset +0x18 and the pack-voltage alarm at +0x16. Event 1–5 have already passed their function-switch masks and receive no additional wire mask. Bit alarms see §6.

### 5.3 CID2 0x45: Remote control

**Request:** INFO 3 bytes: `[0]` unused (`00`), `[1]` type, `[2]` parameter. **Response:** empty, RTN 00.

| Type | Parameter | Effect | Example (address 1) |
|---|---|---|---|
| 03 | `10` / other | force heating on for 3600 s = **1 h** (counter `0x200000C8` in the 1 s main cycle; on-off bit 3 set while running) / off | `~20014645A006000310FC6F` |
| 04 | `10` / other | **switch on / switch off** (clear/set system status bit 5 "Off"). A master with slaves reports every change of bit 5 as a broadcast to all slaves (see below) | on: `~20014645A006000410FC6E`, off: `~20014645A00600041FFC58`; broadcast on/off: `~20FF4645A006000410FC43` / `~20FF4645A00600041FFC2D` |
| 05 | – | **clear history** (EEPROM header and record count), reset **cycle count to 0** and cumulative charged/discharged totals (`0x20000CC8+0x58/+0x5C`) | |
| 06 | – | **restart** (interrupts disabled, watchdog `0x50009000` configured, endless loop until reset); **no response**, the board resets first *(measured)* | `~20014645A006000600FC6D` |
| other | | RTN 04 | |

Type 4 changes only the logical off bit immediately (`0x0A86–0x0ABC`); output evaluation follows in the next 1 s cycle (`0x61B0–0x61C0`). The BMS continues running and answering requests. On clears the bit without forcing either gate; off normally inhibits discharge and precharge while charging remains independently controlled. [Power on/off](../firmware/power-on-off.md) gives all MOSFET exceptions, wakeup and repeated-off conditions, GPIO shutdown behavior and bench evidence.

A master with slaves sends `00 04 1F` or `00 04 10` to `FF` once on each off-bit edge (`0x8A24`, transmit `0x13F6` between 0x5A polls), regardless of the trigger. Slaves apply this silently. There is no cyclic override of a unicast off; later on/wakeup conditions can clear it. A polling master does not itself process pack-bus 0x45 requests. Keep physical access to the button available for an initial control test.

**Only available on the pack bus (RS485-1/2).** The RS485 bus of the CAN socket knows no control commands; Modbus is also read-only there (FC 03/04).

### 5.4 CID2 0x47: Read parameters

**Request:** without INFO: `~200146470000FDA8<CR>`

**Response:** 169 bytes (LENGTH `8152`):

| Byte | Content |
|---|---|
| 0 | own address |
| 1 | `3C` (60) |
| 2–121 | parameters 0–59, each u16, RAM `0x20001300…` |
| 122 | `1B` (27) |
| 123–149 | parameters 60–86, each u8, RAM `0x200013F0…` |
| 150 | `08` |
| 151–158 | function switches BitGroup0–7, RAM `0x20000028…2F` |
| 159–168 | device name (10 ASCII) |

Meaning, RAM location and units of all parameters and switches: [configuration parameters](../firmware/configuration-parameters.md). Short form:
- cell voltage in mV, pack voltage in 10 mV, temperature in 0.1 K, current in 10 mA (discharging negative), capacity in 10 mAh
- byte parameters 60/61 (cell difference fault) in 10 mV, 62/63 (balancing difference) in mV
- **Switch byte k masks alarm event k+1** (k = 1…5); BitGroup0 is not a mask, only bit 1 has an effect (temperature sensor plausibility check). BitGroup6/7 are function switches (§6.6)

### 5.5 CID2 0x49: Set capacity

**Request:** INFO 4 bytes: `[0]` unused, `[1]` index, `[2..3]` value u16. **Only two indices:**

| Index | Effect | Rejection (RTN 06) |
|---|---|---|
| `3A` (58) | set **learned full capacity** and coulomb maximum (0.01 Ah); parameter field P58 stays unchanged | remaining capacity > value |
| `3B` (59) | set **remaining capacity** (coulomb counter) | full capacity < value |

Other indices → RTN 04. All other parameters can only be set via 0xA1.

49/3A sets coulomb maximum `0x200015E0 := value × 3600`; 49/3B sets the live coulomb counter `0x200015EC := value × 3600`, **not** parameter field P59. Conversely, A1 with a changed P59 does not set the live SOC. 0x49 changes RAM and does not immediately save block 6; the next storage occasion can persist it, such as a new cycle or a SOC change greater than 5 percentage points while neither charging nor discharging. These distinctions have CPU counterexamples from 2026-10-21; see [storage triggers and verified differences](../firmware/soc-capacity-and-persistence.md).

The value set lives in RAM only and is only a starting point: the 1 s SOC logic goes on from there and sets full or zero under the full/empty conditions (`0x8F70–0x8F98`, `0x8DC8–0x8E08`); below P79 the SOC protection blocks discharging. *(confirmed; measured: on a bench board without cells, i.e. at undervoltage, 75 Ah was accepted with RTN 00 and was back at 0 after 1.5 s)*

### 5.6 CID2 0x4B: Read history

- **Storage:** external I²C EEPROM (device 0xA4), ring buffer with 128 bytes per record, **max. 500 records**, header at 0xFF00. Written by `0x5998`, triggered by `0x5DB2` (called at `0x621E` in the main loop's 1-s block) *(certain, 06.13; 04.06/06.11/06.12 identical)*:
  - **at once on a change** of the system status (`0x2000003A`: `0x20`/`0x02`/`0x01`/`0x10`) or of event bytes 1–5, 6 (without bit 7) and 7 (bits 4–7 only) since the last trigger; event 8 does not count. Hence records one second apart when messages change (bench board);
  - **otherwise at the interval** of parameter 75 (operation) or 76 (standby) in minutes; raw status bits 0/1 select the running counter. Both counters restart after every trigger.
  - A record triggered by a change still holds the **events from before the change** in E1–E7 (`0x5998` reads the previous values `0x20000030…36`; only afterwards `0x5DB2` copies the new ones there). The new state appears in the next record.
  - If the RTC cannot be read over I²C, the record is skipped and not made up later; a clock marked invalid (event 8 bit 5) does not prevent it.
- **Request:** INFO 2 bytes, `[0]` unused, `[1]` = 0 → oldest record, ≠ 0 → next one. No records → empty response. Read error → RTN 8.
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
| 12–31 | name of the **active CAN protocol**, e.g. `CAN:PNG_DYE_Luxp_TBB`; an index outside 2…7 reports protocol 1 |

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

Rejection → RTN 06, unknown subcode → RTN 04. Saved via `0x5174` into calibration flash block 2 (`0x27000`, mirror `0x28000`), separate from the A1 parameter block.

Detailed effects *(confirmed, code review 2026-10-14)*:

- **Factors:** sub 1/2 store absolute factors computed from the previous factor and the ratio reference/measured (current `0x2392 → 0x2284`, factor `0x20000C78+0x0C`; voltage `0x1F38 → 0x1CA0`, cell factors `0x20000B64+12·i+8` and pack voltage factor `0x20000C24+8`). A new calibration with a good measurement therefore corrects an old error, within the acceptance limit. **No UART command reads the factors**; they live only in flash block 2 (cells from record offset `+3+2·i`, voltage `+37`, current A `+39`/`+41`, current B `+45`/`+47`; `0x5174–0x5234`, load `0x5260–0x5328`).
- **Sub 0 with current flowing:** only |channel| < 1000 mA is checked, then the momentary ADC bases become the zero point (`0x2348–0x2386`). A residual current (e.g. 0.8 A) stays as a **permanent offset** and skews current, SOC counting and current-dependent logic. The 0x42 current reads 0 in standby (`0x03A4–0x0452`), so it does not prove that no current flows.
- **Sub 1 without a minimum current:** only |BMS − reference| < 3.01 A (`0x2392–0x23B0`). Example: BMS 2 A, reference 0.01 A is accepted and divides the factor by 200; because of the 3-A limit a single new calibration cannot undo that.
- **Sub 2:** reference = mV per cell, compared with the arithmetic mean of the cell voltages (`0x20000D08`) and with the **port voltage P+/P−** (`0x20000CDA`), not B+/B− (`0x1EC0–0x1F88`). With the MOSFETs off the port reads 0 V and the calibration is refused.
- **Storage:** `0x4748` writes `0x27000` first, then the mirror; at boot `0x47A8` checks both CRCs and repairs a broken copy (`0x47D0–0x4888`). `0x5174` does not verify the write: a success answer and changed readings prove the RAM value, not the stored one.
- 06.04/06.05: same logic at shifted addresses (`0x0BAA`, `0x1E14`, `0x225E`, `0x4690`).

### 5.12 CID2 0xA1: Write parameters

Request INFO, 169 bytes, layout as the [0x47 response](seplos-ascii.md#54-cid2-0x47-read-parameters). Byte 0 is ignored:

- `[1]` = **0x3C**, then 60 × u16 → buffer
- `[122]` = **0x1B**, then 27 bytes → buffer
- `[150]` = **0x08**, then 8 function switch bytes and 10 bytes device name → **live immediately**

Sequence:

1. A wrong marker → RTN 04.
2. Plausibility check `0x4C3C` (e.g. ordered alarm/protection thresholds, limit values). Failure → **RTN 6**.
   - ⚠ Function switches and name have **nevertheless already been changed** in RAM in that case, but are not saved.
3. On success: transfer into the live tables and write to the **internal flash** parameter block (mirrored). The I²C EEPROM holds only the history.
4. If the P58 sent deviates from the learned full capacity by ≥ 10.00 Ah, **full capacity and coulomb maximum are set to P58** and flash block 6 is written (`0x08FC–0x09A8`). **This happens on every successful 0xA1, also when P58 is unchanged**; the SOC jumps.
5. No CAN re-init, no reset of protection counters. The next 1-s protection run uses the new thresholds and switches at once (MOSFETs, balancing, heating, CAN limits may change).

Rules of `0x4C3C` (16.06.13, raw values, equality allowed, first failure → RTN 06; `0x4C42–0x514C`) *(confirmed; code review 2026-10-14)*:

| Group | Rule |
|---|---|
| Cell | P0 ≥ P1 ≥ P3 ≥ P2 ≥ 2000, P0 ≤ 4300; P4 ≥ P5 ≥ P7 ≥ P6 ≥ 2000, P4 ≤ 4300; 3330 ≤ P8 ≤ P4; 1000 ≤ P9 ≤ P6 |
| Pack | P10 ≥ P11 ≥ P13 ≥ P12 ≥ 1600, P10 ≤ 6000; P14 ≥ P15 ≥ P17 ≥ P16 ≥ 1600, P14 ≤ 6000; P14 ≤ P19 ≤ P18 ≤ 6500 |
| Temperature (0.1 K) | each group P20–23, P24–27, P28–31, P32–35, P38–41, P42–45: a ≥ b ≥ d ≥ c ≥ 2431 (−30 °C), a ≤ 3531 (80 °C); heating P26 ≤ P36 ≤ P37 ≤ 2931 (20 °C); power 3231 ≤ P47 ≤ P46 ≤ P48 ≤ 3931 and 3231 ≤ P49 ≤ P48 |
| Current (0.01 A, signed) | P55 ≤ P52 ≤ P53 ≤ P51 ≤ P50 ≤ P54 ≤ 30000; −30000 ≤ P56 ≤ P55 |
| Other | 500 ≤ P57 ≤ 5000; P59 ≤ P58 ≤ 65000; 10 ≤ P61 ≤ P60 ≤ 100; 10 ≤ P63 ≤ P62 ≤ 100 |
| Ranges | P64 1–18, P65 7–16, P66/67 3–180, P68 5–250, P69 10–250, P70–72 1–30, P73 1–24, P74 1–100, P75 1–250, P76 30–250, P77 1–250, 1 ≤ P79 ≤ P78 ≤ 30, P80 70–99, P81 10–150, P82 0–100, P83 1–9, P84 0–50, P85 10–16, P86 0–50 |

Not checked: function switches, cell chemistry, P65 against the actual wiring.

### 5.13 CID2 0xA2–0xA5: Two 30-byte strings

| CID2 | Effect |
|---|---|
| 0xA2 / 0xA3 | read / write string 1 (`0x2000004C`): **battery serial number** (BatteryMonitor: "Battery_SN") *(certain)*; output via Modbus FC04 `0x0000` (first 22 characters) and Pylontech 0x60 (first 15 characters per entry) |
| 0xA4 / 0xA5 | read / write string 2 (`0x2000006A`): **BMS / protection board serial number** (BatteryMonitor: "BMS_SN") *(certain)*; no other output in the app code. On a bench board it held `SEPLOS-<11 digits>` *(measured)*, while string 1 held the image placeholder |

- Writing saves immediately (`0x53D8`): both strings and a third 30-byte area (`0x20000088`) are stored together in **flash block 4 = `0x29000`** (mirror `0x2A000`) and loaded at start-up via `0x603A → 0x549E`. Without a stored block the image placeholder `EMU110110S-XXXX-20220120-00001` stays *(certain)*.
- Pack bus (UART0) only: on the CAN socket (UART1) the master answers 0xA2/0xA4 with **RTN 04** *(measured)*. There, string 1 is reachable only through Modbus FC04 `0x0000`×21 (first 22 characters).
- **From 06.11** 0xA3/0xA5 read LENGTH/2 bytes (max. 30) and pad with spaces. Up to 06.05 exactly 30 bytes were always read.

Read responses contain 30 bytes. Example string 1 read at address 1: `~200146A20000FDA0<CR>`.

**Labels on the board** (photos of five EMU1101 PCBA-V16 boards, built 2022–2023; one of them read on the bus) *(observed)*: every board carries two labels.

- **Seplos barcode label:** model line `Model:<voltage><capacity>-1101-10E-SP<nn>-<cells>S` (e.g. `48150-1101-10E-SP85-16S`) and below it `SEPLOS-YYMMDD<4-digit counter>`. On the board that was read, exactly this number was in **string 2** (BMS serial number). String 1 (battery serial number) is set by the pack maker; on this board it had been set by hand to the value of string 2 afterwards, so in finished packs it presumably holds a number of its own. `SP<nn>` is the identifier 0x51 reports (`1101-SP85`).
- **Assembler's QR/DataMatrix label:** bill of materials/variant (e.g. `1101-48150-10E-V16-JC`) and its own number `HG…`/`HX…` + YYMMDD + sequence, dated a few weeks before the Seplos number (assembled, then programmed at Seplos). This number is not in 0xA2/0xA4. One product photo shows a different format (`V16SM…`).

Consequence: if a pack has no BMS serial number (string 2) or a placeholder, the right one can be read off the barcode label and written with 0xA5.

### 5.14 CID2 0xA6: Set CAN inverter protocol

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
- **From 06.11:** When switching to or from 7, `0x9A88` is additionally called (CAN re-initialisation, 100 ↔ 500 kbit/s). An unchanged value is not saved.
- **8…20** are stored and treated like 1 (`0x0EA6–0x0ED4`, `0x0ACA`, `0xAEBA`) *(Codex review 2026-10-14)*.
- **7 on 06.04/06.05:** accepted and stored, but runs as protocol 1 (no MUST code, no switch to 100 kbit/s; `0x0E3E–0x0E64`, `0xA0A8`). After a later update to ≥ 06.11 the stored value switches to MUST/100 kbit/s at boot, and any other inverter loses CAN. The 0x51 version (`10 06`) does not tell 06.04/06.05 from 06.11/06.13.
- Counterpart in the [binary display protocol](binary-display-protocol.md#3-commands): command 0x63.
- Example protocol 1 to address 1: `~200146A6E00201FD24<CR>`.

### 5.15 CID2 0xAA / 0xAB (from 06.13): Tunnel to the binary port

The sequence is confirmed; the connected device and payload purpose are assumptions. The BMS acts as a **gateway** between an RS485 ASCII host and the device on the binary port (display/dongle):

| Step | 0xAA ("read 6 bytes from device") | 0xAB ("write 6 bytes to device") |
|---|---|---|
| Host → BMS (ASCII) | `CID2 AA`, without INFO | `CID2 AB`, INFO = 6 bytes |
| BMS internal | `0x200000E8` = 1, **no immediate response** | 6 bytes → `0x200000EA…EF`, `E8` = 3 |
| BMS → device (binary) | `55 ADR AA 00 CRC AA` | `55 ADR AB 06 b0…b5 CRC AA` |
| Device → BMS (binary) | `55 ADR AA 06 b0…b5 CRC AA` → `E8` = 2 | `55 ADR AB 00 CRC AA` → `E8` = 4 |
| BMS → host (ASCII, function `0x128E`) | RTN 0, INFO = 6 bytes | RTN 0, empty INFO |

- There is **no timeout**: if the device does not respond, the host never gets a response.
- The 6 bytes are not evaluated in the BMS. *Assumption:* PIN/password or MAC of a Bluetooth/Wi-Fi dongle, or date/time of a display.

Up to 06.12 these commands return RTN 04. [Patch-version detection](../firmware/firmware-analysis.md#10-identifying-the-oem-firmware-revision) describes the isolation requirements. Binary framing and scheduling: [binary display protocol](binary-display-protocol.md).

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
| 6 Other | charger overvoltage | **Intermittent recharge waiting** | remaining capacity alarm | remaining capacity **protection** | charging locked (cell too low) | reverse polarity (**never set**) | output connection fault (GPIO input) | current limiter not ready (masked out in 0x44; preserved in 0x5A) |

Alarm generation, debounce, latches and clear conditions: [states and triggers](../firmware/states-and-triggers.md). Decode warnings/protections using each event’s rules; Event2 explicitly suppresses the corresponding warning when its voltage protection is active. Evaluators should prioritize protection or lockout. Event 4 bit 4 is protection (P48), bit 5 is alarm (P46).

### 6.2 On-off status

Bit 0 discharge MOSFET, 1 charge MOSFET, 2 current limiting, 3 heating, 4 precharge running (soft start, parameter 57), 5 discharge MOSFET just switched on (100 ms), 6 "external voltage at the port, MOSFET open" (auxiliary flag for system status bit 2). Bits 4–6 are masked out in 0x44. *(confirmed)*

### 6.3 System status

Bit 0 discharging, 1 charging, 2 "Float" (internal "charge path active" flag), 3 never set, 4 standby, 5 off, 6 discharge current ≥ 3 A, 7 charge current ≥ 3 A. In 0x44 only bits 0, 1, 4 and 5 are reported (`& 0x33`), in 0x5A all of them. Thresholds: [states and triggers](../firmware/states-and-triggers.md).

Bit 2 reports detected charger/external voltage at the output rather than a float charge phase. It is masked out of 0x44 and retained in 0x5A byte 31. Its voltage thresholds, debounce and heating/shutdown uses are described in [states and triggers](../firmware/states-and-triggers.md).

### 6.4 Balancing (0x44 byte +17/+18, RAM `0x20000006/07`)

Bit n = cell n+1 is **currently being balanced**. The mask actually passed to the measurement/balancing IC is reported. Its enable and selection conditions are described in [passive balancing](../firmware/states-and-triggers.md#passive-balancing).

### 6.5 Alarm events 7 and 8

| Event | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 7 | **balancing active** | **balancing locked / not needed** | **balancing time limit reached** | **balancing locked due to ambient temp.** | **charge activation automatic** (window open) | **charge activation manual** (after switch-on) | **charging via current limiter from 10 A** | **current limiting after charge overcurrent warning** |
| 8 | EEPROM error | RTC error | voltage not calibrated | current not calibrated | zero point not calibrated | **RTC time invalid** (bit 7 of RTC register 2, I²C 0xA2) | **charging forbidden** (controls charge MOSFET) | in 0x5A: GPIO pin 9 high |

In 0x44 only event 7 bits 4/5 and event 8 bits 0–5 are visible. **The balancing bits of event 7 can only be seen in the intra-pack response 0x5A** (byte 29, unfiltered).

### 6.6 Function switches BitGroup6 and BitGroup7 *(all confirmed)*

The 0x47/0xA1 switch bytes at INFO 151–158 are BitGroup0–7 (`0x20000028…2F`). Bit meanings, masks and behavior references are listed once in [configuration parameters §5](../firmware/configuration-parameters.md#5-function-switches-bitgroup07). Binary UART2 enable and format are BitGroup7 bits 3/4; they do not enable an ASCII parameter proxy.

## 7. Passive balancing: how it works (06.13 `0x653C`/`0x205A`)

The [states and triggers reference](../firmware/states-and-triggers.md) defines balancing enable, cell selection, neighbor exclusion, measurement phases, time and temperature locks, hysteresis and version differences. The wire mask and event bits are defined in [Balancing (0x44 byte +17/+18, RAM `0x20000006/07`)](seplos-ascii.md#64-balancing-0x44-byte-1718-ram-0x2000000607) and [Alarm events 7 and 8](seplos-ascii.md#65-alarm-events-7-and-8).

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
6. Two buses with different command sets; baud rates are 19200 / 9600 from 16.06.03, but both 9600 in 16.04.06. The documentation states 9600 across the board.
7. Event 4 bits 4/5 and event 5 bits 4–7 have, in practice, the meaning given above (protection/alarm or protection/lockout).

**Address collisions on UART1:** FF reads can produce several replies. `4F/02` can reach master 0 and slave 2 simultaneously; use it as a version distinction only with an isolated master. System 60–63 accepts master aliases 02/12, not 00. See the topology page for bus ownership and supported alternatives.

## 10. Firmware version differences

| Item | 04.06 | 06.03–06.05 | 06.11 / 06.12 | 06.13 |
|---|---|---|---|---|
| ASCII 0x42…0xA6 | present | same command set | same | dispatcher uses two jump tables |
| 0xA3 / 0xA5 | always read 30 bytes | same | use LENGTH, space padding | same |
| 0xA6 | no MUST special case | same | protocol 7/MUST special case; save only on change | same |
| 0xAA / 0xAB | absent | absent | absent | six-byte binary tunnel |

Other command handlers are semantically unchanged since 04.06 apart from address relocation and the specific differences described above. UART baud rates, UART1 address aliases and response addresses have their own version qualifications in [Physical layer: sockets, UARTs, baud rates](seplos-ascii.md#1-physical-layer-sockets-uarts-baud-rates) and [Addressing and response behavior](seplos-ascii.md#3-addressing-and-response-behavior). Binary command versions are listed in the [binary reference](binary-display-protocol.md#5-firmware-version-differences).
