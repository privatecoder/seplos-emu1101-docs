# Seplos 10E (EMU1101): Intra-Pack Communication (CID2 0x5A)

This document describes how several packs connected in parallel communicate with each other over the RS485 pack bus. It is based on the disassembly of the firmware images under [`firmware/ehex/`](../../firmware/ehex/), in detail V16.06.13, cross-checked against V16.04.06 through V16.06.12. The official protocol PDF ([`specs/Seplos MODBUS-ASCII Protocol V2.0 (2019-10-15).pdf`](<../../specs/Seplos MODBUS-ASCII Protocol V2.0 (2019-10-15).pdf>)) does not mention CID2 0x5A at all.

Confidence: **confirmed** = read directly from the code · **probable** = inferred from the data flow · **assumption** = plausible, but not proven.

## Summary

- Intra-pack communication uses the normal Seplos ASCII protocol (YD/T1363.3 frame `~ VER ADR CID1 CID2 LENGTH INFO CHKSUM CR`) with the undocumented command **CID2 = 0x5A**. *(confirmed)*
- The **master** (pack with RS485/DIP address 0) polls the **slaves** (addresses 1…n) in turn. *(confirmed)*
- The slave replies with **CID2 = 0x5A** instead of the return code `00`. This is an exception; all other responses carry the RTN code. *(confirmed)*
- The response contains **32 bytes of INFO**, i.e. LENGTH = `C040`. *(confirmed)*
- Format and content are **unchanged since V16.04.06** up to V16.06.13. Since 06.13 only some RAM addresses have been shifted internally by 8 bytes. *(confirmed)*

## Sequence on the bus

### Master mode

The main loop (06.13 from `0x6264`) selects the mode:

```
if (rs485_address == 0  &&  slave_count != 0  &&  !(flag 0x20000000.bit2))
    master polling   (functions 0x13f6 = send request, 0x14ae = evaluate response)
else
    normal ASCII slave dispatcher (0x1132: 0x42, 0x44, 0x47, 0x5A, …)
```

- `rs485_address` = RAM `0x20000027` (DIP switch). *(confirmed)*
- `slave_count` = RAM `0x20000026`, maximum **21** (0x15). *(confirmed)* If the function switch byte `0x2000002f` bit 5 is set, the master adjusts the number automatically: it increases it as long as the last slave responds, and decreases it when a slave drops out. *(probable)*
- Consequence *(confirmed, code and practice)*: In master mode the main loop calls only the polling, never the normal ASCII dispatcher. **On the pack bus the master does not answer any requests**, not even between rounds. External queries there also collide with its polling ("multimaster collisions"). The master is read via the RS485 bus of the CAN socket.

### Master request (function `0x13f6`)

- Round-robin index in RAM `0x20000500`. It runs from 1 to `slave_count` and then starts again at 1. *(confirmed)*
- Frame without INFO (LENGTH `0000`), address = pack index:

| Target | Frame (ASCII) |
|---|---|
| Pack 1 | `~2001465A0000FD9D\r` |
| Pack 2 | `~2002465A0000FD9C\r` |
| Pack 3 | `~2003465A0000FD9B\r` |

This is the frame "`20.01.46.5A.00.00`" from esphome issue #116.

**On/off synchronisation:** If the master's on/off state changes (system status bit 5 "off"), it sends, instead of the next 0x5A request, a **broadcast to address 0xFF with CID2 0x45** (remote control, type 4). *(confirmed)*

| Event | Frame |
|---|---|
| Master switched on | INFO `00 04 10` → all slaves switch **on** |
| Master switched off | INFO `00 04 1F` → all slaves switch **off** |

- The edge is detected in `0x8A24`; the request is stored in `0x20000000` bit 5 (on) or bit 4 (off).
- Slaves do not respond to broadcasts.
- Details on CID2 0x45: [undocumented-commands.md §1.3](undocumented-commands.md#13-cid2-0x45-remote-control-confirmed).

### Slave response (handler `0x10d6`)

```
~ 20 <ADR> 46 5A C040 <64 ASCII characters = 32 bytes INFO> <CHKSUM> \r
```

- ADR = the slave's own address.
- In the field that otherwise holds the RTN code, the slave explicitly inserts `0x5A` (`strb 0x5a → [Puffer+0x15]`, i.e. buffer+0x15). *(confirmed)*
- LENGTH `C040`: LENID = 0x040 = 64 ASCII characters, LCHKSUM = `C`. *(confirmed)*

### Evaluation by the master (`0x14ae` / `0x1384`)

- The master accepts only responses with CID2 = 0x5A and the expected total length (82 characters including framing). *(confirmed)*
- It decodes **30 bytes** starting at INFO byte 2, i.e. without `00 01`, and stores them in a table: `0x20000524 + 30 × pack index`. **Index 0 is the master itself** (function `0x12e2` copies its own values there). *(confirmed)*
- There is a failure counter per pack. After **10** missed or invalid responses, the pack's bit in the online bitmask is cleared (`0x20000500 + 0x18`, 32 bits, bit n = pack n). On a valid response the counter is reset and the bit is set. *(confirmed)*
- From this table the master forms the **system values for the inverter** (CAN, Modbus, Pylontech RS485). Function `0x99BA` calls `0x94D2`, `0x96CE` and `0x98A8` for this. *(confirmed)*

| System value | Derivation |
|---|---|
| Voltage, port voltage | **Average** of the online packs |
| Current, remaining/full capacity | **Sum** |
| SOC | Σ remaining / Σ full |
| Cell voltage, cell temperature | Max/min across all packs, with pack number |
| Alarms | **OR** of all packs (bytes 22–30 of each record) |
| Charge/discharge enable, CCL/DCL | Number of packs allowed to charge or discharge; a pack with event 6 bit 1 "Intermittent recharge waiting" counts as **charge-blocked** |
| Communication error | If packs are missing for 30 cycles, `0x20000000` bit 3 is set (CAN 0x359, Modbus, Pylontech report this) |

Details: [can.md §3](can.md#3-limits-and-data-source-master-aggregation-confirmed) and [modbus-rtu.md §2](modbus-rtu.md#2-data-source-system-aggregate-0x2000164c).

## INFO layout of the 0x5A response (32 bytes)

All 16-bit values are big-endian and, as everywhere in the protocol, transmitted as hex ASCII. The source is the snapshot `0x20000524` (06.13; 06.12 `0x2000051c`) that the slave updates cyclically. Function `0x12e2` (06.13) or `0x1252` (06.12) fills it from the measurement structure `0x20000cc8` and the alarm bytes.

| INFO byte | ASCII offset in INFO | Content | Format / scaling | Source (06.13) | Confidence |
|---|---|---|---|---|---|
| 0 | 0–1 | DATA FLAG, always `00` | – | constant | confirmed |
| 1 | 2–3 | always `01`, **not** the pack address | – | constant | confirmed |
| 2–3 | 4–7 | **highest cell voltage** | uint16, mV | `0xcc8+0x00` (max over all cells) | confirmed |
| 4–5 | 8–11 | **lowest cell voltage** | uint16, mV | `0xcc8+0x02` (min over all cells) | confirmed |
| 6–7 | 12–15 | **highest cell temperature** | uint16, 0.1 K → (x−2731)/10 °C | `0xcc8+0x04` (max over the 4 cell sensors, `0x21D6`) | confirmed |
| 8–9 | 16–19 | **lowest cell temperature** | uint16, 0.1 K → (x−2731)/10 °C | `0xcc8+0x06` (min over the 4 cell sensors; also used for the heater logic) | confirmed |
| 10–11 | 20–23 | **current** | int16, 0.01 A, + = charging | `0xcc8+0x08` | confirmed |
| 12–13 | 24–27 | **pack voltage** | uint16, 0.01 V | `0xcc8+0x0a` | confirmed |
| 14–15 | 28–31 | **remaining capacity** | uint16, 0.01 Ah | `0xcc8+0x0c` | confirmed |
| 16–17 | 32–35 | **full capacity** (Battery capacity) | uint16, 0.01 Ah | `0xcc8+0x0e` | confirmed |
| 18–19 | 36–39 | **SOC** | uint16, 0.1 % | `0xcc8+0x10` | confirmed |
| 20–21 | 40–43 | **port voltage** | uint16, 0.01 V | `0xcc8+0x12` | confirmed |
| 22 | 44–45 | **Alarm event 1** (sensor/switch faults) | bit field, see below | `0x20000030` | confirmed |
| 23 | 46–47 | **Alarm event 2** (voltage) | bit field | `0x20000031` | confirmed |
| 24 | 48–49 | **Alarm event 3** (cell temperature) | bit field | `0x20000032` | confirmed |
| 25 | 50–51 | **Alarm event 4** (ambient/power section/heater) | bit field | `0x20000033` | confirmed |
| 26 | 52–53 | **Alarm event 5** (current) | bit field | `0x20000034` | confirmed |
| 27 | 54–55 | **Alarm event 6** (miscellaneous) | bit field, bit 7 masked | `0x20000035 & 0x7F` | confirmed |
| 28 | 56–57 | **Switch state (On-off state)** | bit field | `0x200000b5` | confirmed |
| 29 | 58–59 | **Alarm event 7** | bit field, unfiltered (in 0x44 only `& 0x30`) | `0x20000036` | confirmed |
| 30 | 60–61 | **Alarm event 8** bits 0–6, **bit 7 = internal flag** | bit field | `(0x20000005 & 0x7F) \| (0x80 if 0x200000f6.bit3 == 0)` | confirmed (bit 7: input GPIO pin 9, see [firmware-analysis §8.2d](../firmware-analysis.md#82d-alarm-event-8-bit-7-and-automatic-address-assignment)) |
| 31 | 62–63 | **System status**, unfiltered (in 0x44 only `& 0x33`) | bit field | `0x200000ac` | confirmed |

### Bit meanings (from `Seplos MODBUS-ASCII Protocol V2.0 (2019-10-15).pdf`, table 13)

The mapping of the RAM bytes to the events is established via the 0x44 handler: it writes exactly these bytes in this order. *(confirmed)*

| Byte | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| Event 1 | Voltage sensor fault | Temperature sensor fault | Current sensor fault | Key/button fault | Cell difference fault | Charge switch fault | Discharge switch fault | Current limit fault |
| Event 2 | Cell high voltage alarm | Cell overvoltage protection | Cell low voltage alarm | Cell undervoltage protection | Pack high voltage alarm | Pack overvoltage protection | Pack low voltage alarm | Pack undervoltage protection |
| Event 3 | Charge overtemp. alarm | Charge overtemp. protection | Charge undertemp. alarm | Charge undertemp. protection | Discharge overtemp. alarm | Discharge overtemp. protection | Discharge undertemp. alarm | Discharge undertemp. protection |
| Event 4 | Ambient overtemp. alarm | Ambient overtemp. protection | Ambient undertemp. alarm | Ambient undertemp. protection | Power section overtemp. protection | Power section overtemp. alarm | Cell heating requested | **Severe fault** (latch: sensor fault, cell ≥ P4 + 50 mV, cell ≤ P6 − 200 mV, overcurrent protection; see [seplos-ascii.md](seplos-ascii.md) §6.1) |
| Event 5 | Charge overcurrent alarm | Charge overcurrent protection | Discharge overcurrent alarm | Discharge overcurrent protection | Transient overcurrent protection | Short-circuit protection | Transient overcurrent lockout | Short-circuit lockout |
| Event 6 | Charger overvoltage | **Intermittent recharge waiting** | Remaining capacity alarm | Remaining capacity protection | Charging blocked (cell too low) | Reverse polarity (never set) | Output connection fault (GPIO input) | Current limiter not ready (masked in 0x5A) |
| On-off | Discharge MOSFET on | Charge MOSFET on | Current limiting on | Heater on | Precharge in progress (P57) | Discharge MOSFET just switched on (100 ms) | External voltage at port with MOSFET open | – |
| Event 7 | **Balancing active** | **Balancing blocked / not needed** | Balancing time limit reached | Balancing blocked due to ambient temperature | Charge activation automatic | Charge activation manual | Charging via current limiter from 10 A | Current limiting after charge overcurrent warning |
| Event 8 | EEPROM fault | RTC fault | Voltage not calibrated | Current not calibrated | Zero point not calibrated | RTC time invalid | internal: "charging forbidden" request (controls the charge MOSFET, see SP80 in [firmware-changelog.md](../firmware-changelog.md)) | in 0x5A: **input GPIO pin 9 high** (presumably "no address request from neighbouring pack"; always 1 with DIP addressing) |
| System status | Discharging | Charging | "Float" = charger/external voltage detected at port (no float mode; visible only here, hidden in 0x44) | – (never set) | Standby | Off (shutdown) | **Discharge current ≥ 3 A** | **Charge current ≥ 3 A** |

Thresholds and origin of all system status bits: [firmware-analysis §8.2c](../firmware-analysis.md#82c-system-status-all-bits-from-the-code). When the SOC stays at 98.2 % or jumps to 98/100 %: [states-and-triggers](../states-and-triggers.md).

## Examples, fully decoded

### Frame from esphome-seplos-bms issue #116

Log: `20.01.46.5A.C0.40.00.01.0D.2D.0D.2A.0B.6A.0B.63.02.41.15.12.6B.68.6D.60.03.D6.15.16.00.00.00.00.00.00.03.02.80.82`

Complete frame with checksum (calculated):
`~2001465AC04000010D2D0D2A0B6A0B63024115126B686D6003D6151600000000000003028082F059\r`

| Field | Raw value | Value |
|---|---|---|
| Header | `20 01 46 5A C040` | VER 2.0, pack address 1, CID1 0x46, CID2 0x5A, 32 bytes INFO |
| DATA FLAG / constant | `00 01` | – |
| highest cell voltage | `0D2D` | 3.373 V |
| lowest cell voltage | `0D2A` | 3.370 V (difference 3 mV) |
| highest cell temperature | `0B6A` | 2922 → 19.1 °C |
| lowest cell temperature | `0B63` | 2915 → 18.4 °C |
| current | `0241` | +5.77 A (charging) |
| pack voltage | `1512` | 53.94 V |
| remaining capacity | `6B68` | 274.96 Ah |
| full capacity | `6D60` | 280.00 Ah |
| SOC | `03D6` | 98.2 % |
| port voltage | `1516` | 53.98 V |
| Alarm events 1–6 | `00 00 00 00 00 00` | no alarms |
| Switch state | `03` | discharge and charge MOSFET on |
| Alarm event 7 | `02` | bit 1: balancing blocked or no balancing needed |
| Alarm event 8 | `80` | no faults; bit 7 = input pin 9 high (idle state) |
| System status | `82` | bit 1 = **charging**, bit 7 = **charge current ≥ 3 A**; consistent with +5.77 A |

### Example log (esphome, 38-byte frame)

| Log output | Correct mapping |
|---|---|
| Maximum Cell Voltage 3.296 V | ✔ highest cell voltage |
| Minimum Cell Voltage 3.293 V | ✔ lowest cell voltage |
| Temperature 1: 18.3 °C | **highest** cell temperature, not sensor 1 |
| Temperature 2: 17.5 °C | **lowest** cell temperature, not sensor 2 |
| Current 0.01 A | ✔ current |
| Total voltage 52.71 V | ✔ pack voltage |
| Residual capacity 166.75 Ah | ✔ remaining capacity |
| Battery capacity 280.00 Ah | ✔ full capacity |
| State of charge 59.5 % | ✔ SOC |
| Port voltage 52.71 V | ✔ port voltage |
| Unknown `0x00 0x00` (1st) | Alarm event 1 = 0, alarm event 2 = 0 |
| Unknown `0x00 0x00` (2nd) | Alarm event 3 = 0, alarm event 4 = 0 |
| Unknown `0x00 0x00` (3rd) | Alarm event 5 = 0, alarm event 6 = 0 |
| Unknown `0x03 0x02` | Switch state = 0x03 (both MOSFETs on), alarm event 7 = 0x02 (bit 1: balancing blocked / not needed) |
| Unknown `0x80 0x10` | Alarm event 8 = 0x80 (no faults, bit 7 = pin 9 in idle state), system status = 0x10 = **standby** (consistent with 0.01 A) |

This accounts for all 32 bytes. No fields are missing: the 0x5A response contains no more than the 10 measurements and 10 status bytes. Individual cell voltages, individual temperature sensors, cycle count, ambient and power section temperature, SOH and the charge/discharge current limits are **not** transmitted over the pack bus. For those, the slaves must be queried directly with 0x42/0x44.

## Real captures (test data)

24 responses from 10 packs (addresses 1, 2, 4–11) of a 12-pack system (firmware 16.06, captured on the pack bus). All checksums are correct. The mapping above fits every frame, including the thresholds of the system status bits: `10` standby down to −0.19 A, `01` discharging from −0.52 A, `02` charging from +1.49 A, `82` from +3.01 A (still set at +2.92 A, hysteresis down to 2.81 A). At SOC 98.2 % and 3.40–3.49 V per cell, alarm event 2 shows `01` (cell high alarm) or `11` (additionally pack high alarm).

| Frame | Pack | Cell max / min (V) | Current (A) | Pack (V) | SOC (%) | Events 1–6 | System status |
|---|---|---|---|---|---|---|---|
| `~2001465AC04000010D090D070B270B20FFF214D956A96D60031814DB00000000000003028010F02E` | 1 | 3.337 / 3.335 | -0.14 | 53.37 | 79.2 | `000000000000` | `10` |
| `~2001465AC04000010D120D100B270B20000114E756B36D60031814E900000000000003028010F08B` | 1 | 3.346 / 3.344 | +0.01 | 53.51 | 79.2 | `000000000000` | `10` |
| `~2002465AC04000010D0A0D060B290B19FFFF14DA43636D60026814DD00000000000003028010F00F` | 2 | 3.338 / 3.334 | -0.01 | 53.38 | 61.6 | `000000000000` | `10` |
| `~2002465AC04000010D0B0D060B290B19FFFF14DA43636D60026814DC00000000000003028010F00F` | 2 | 3.339 / 3.334 | -0.01 | 53.38 | 61.6 | `000000000000` | `10` |
| `~2004465AC04000010D070D060B1B0B13FFF014D758E16D60032C14DA00000000000003028010F01D` | 4 | 3.335 / 3.334 | -0.16 | 53.35 | 81.2 | `000000000000` | `10` |
| `~2005465AC04000010D060D050B240B19FFED14D658C56D60032B14D800000000000003028010F01B` | 5 | 3.334 / 3.333 | -0.19 | 53.34 | 81.1 | `000000000000` | `10` |
| `~2006465AC04000010D140D110B280B21009514EA58FB6D60032D14EE00000000000003028002F03B` | 6 | 3.348 / 3.345 | +1.49 | 53.54 | 81.3 | `000000000000` | `02` |
| `~2007465AC04000010D080D060B2F0B24FFEF14D75BDD6D60034714DB00000000000003028010EFEA` | 7 | 3.336 / 3.334 | -0.17 | 53.35 | 83.9 | `000000000000` | `10` |
| `~2007465AC04000010D080D060B2F0B24FFEF14D85BDD6D60034714DB00000000000003028010EFE9` | 7 | 3.336 / 3.334 | -0.17 | 53.36 | 83.9 | `000000000000` | `10` |
| `~2007465AC04000010D140D120B2E0B24009B14EB5BED6D60034814EF00000000000003028002F019` | 7 | 3.348 / 3.346 | +1.55 | 53.55 | 84.0 | `000000000000` | `02` |
| `~2008465AC04000010D080D070B2C0B23FFEE14D85A2A6D60033814DA00000000000003028010F003` | 8 | 3.336 / 3.335 | -0.18 | 53.36 | 82.4 | `000000000000` | `10` |
| `~200A465AC04000010D080D060B230B18FFEE14D858E56D60032C14D900000000000003028010F007` | 10 | 3.336 / 3.334 | -0.18 | 53.36 | 81.2 | `000000000000` | `10` |
| `~200B465AC04000010D080D070B1C0B12FFEE14D9583F6D60032614DB00000000000003028010F000` | 11 | 3.336 / 3.335 | -0.18 | 53.37 | 80.6 | `000000000000` | `10` |
| `~2001465AC04000010D090D060B270B20FFF214D956A46D60031814DB00000000000003028010F034` | 1 | 3.337 / 3.334 | -0.14 | 53.37 | 79.2 | `000000000000` | `10` |
| `~2001465AC04000010D1D0D190B270B2100B414F856E26D60031A14FB00000000000003028002F042` | 1 | 3.357 / 3.353 | +1.80 | 53.68 | 79.4 | `000000000000` | `02` |
| `~200B465AC04000010D4F0D4C0B2E0B1B015715496B7C6D6003D6154A00110000000003028082F00A` | 11 | 3.407 / 3.404 | +3.43 | 54.49 | 98.2 | `001100000000` | `82` |
| `~2007465AC04000010D200D1E0B2F0B2500CB14FF5C846D60034D150200000000000003028002F030` | 7 | 3.360 / 3.358 | +2.03 | 53.75 | 84.5 | `000000000000` | `02` |
| `~2009465AC04000010D230D210B280B1F011915045E8B6D600360150500000000000003028002F07C` | 9 | 3.363 / 3.361 | +2.81 | 53.80 | 86.4 | `000000000000` | `02` |
| `~2004465AC04000010D130D110B1E0B16FFCC14EA5D686D60035614EC00000000000003028001F006` | 4 | 3.347 / 3.345 | -0.52 | 53.54 | 85.4 | `000000000000` | `01` |
| `~2001465AC04000010D4A0D470B440B34029515426B696D6003D6154500010000000003028082F063` | 1 | 3.402 / 3.399 | +6.61 | 54.42 | 98.2 | `000100000000` | `82` |
| `~200B465AC04000010D4F0D4C0B2E0B1B012415496B7C6D6003D6154A00110000000003028082F010` | 11 | 3.407 / 3.404 | +2.92 | 54.49 | 98.2 | `001100000000` | `82` |
| `~2006465AC04000010D920D860B410B3100C915B16B7B6D6003D615B300110000000003028002F043` | 6 | 3.474 / 3.462 | +2.01 | 55.53 | 98.2 | `001100000000` | `02` |
| `~2005465AC04000010D9F0D9B0B390B28011C15C76B6A6D6003D615C900110000000003028002F011` | 5 | 3.487 / 3.483 | +2.84 | 55.75 | 98.2 | `001100000000` | `02` |
| `~2005465AC04000010D990D970B390B28012D15C06B6A6D6003D615C300110000000003028082F02C` | 5 | 3.481 / 3.479 | +3.01 | 55.68 | 98.2 | `001100000000` | `82` |

## Parser notes (for `seplos-mqtt-remote-rs485` / esphome)

- Detection: response CID2 == `5A` and LENGTH == `C040`. The usual check "CID2 must be 00" discards these frames; this must be taken into account.
- In the Python code (`decode_intra_pack_info_frame`) the offsets 4/8/12/16/20/24/28/32/36/40 (ASCII within INFO) are correct. The temperatures are max/min, not sensor 0/1.
- The alarm bytes start at ASCII offset 44 (INFO byte 22). The order is Event1, Event2, Event3, Event4, Event5, Event6, On-off, Event7, Event8, system status. The commented-out lines `cell_overvoltage`/`pack_overvoltage` in the script must therefore read event 2, i.e. INFO byte 23, ASCII offset 46. Bit 0/1 = cell alarm/protection, bit 4/5 = pack alarm/protection.
- On the bus only master requests and slave responses are visible. The master's own values exist only internally in table index 0 and do not appear on the pack bus.

## Version history

| Version | Change to the 0x5A protocol |
|---|---|
| 16.04.06 | present, identical 32-byte format (handler `0x106e`) |
| 16.06.03 – 16.06.12 | unchanged |
| 16.06.13 | format unchanged; the snapshot is located 8 bytes further on (`0x20000524`), and the 0x5A case has moved into the jump table of the ASCII dispatcher instead of being handled as a single comparison. New in the same area: CID2 0xAA/0xAB (see [undocumented-commands.md](undocumented-commands.md)). |
