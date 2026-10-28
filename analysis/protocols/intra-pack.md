# Seplos BMS 2.0/10E/V16 (EMU1101): Intra-Pack Communication (CID2 0x5A)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

This document describes how several packs connected in parallel communicate with each other over the RS485 pack bus. It is based on the disassembly of the firmware images under [`vendor/firmware/`](../../vendor/firmware), in detail V16.06.13, cross-checked against V16.04.06 through V16.06.12. The official protocol PDF ([`Seplos Modbus-ASCII Protocol RS485 V2.0 (2019-10-15).pdf`](<../../vendor/docs/protocol%20specs/Seplos%20BMS%20Modbus-ASCII%20Protocol%20RS485%20V2.0%20%282019-10-15%29.pdf>)) does not mention CID2 0x5A at all.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2, inverter protocols and available monitoring/service paths. Availability depends on the **active requester on each bus**, not the number of sockets or gateways.

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
if (rs485_address == 0  &&  slave_count != 0) {
    if (!(flag 0x20000000.bit2))
        master polling   (functions 0x13f6 = send request, 0x14ae = evaluate response)
    // bit 2 set: neither polling nor dispatcher (pause until the next round)
} else
    normal ASCII slave dispatcher (0x1132: 0x42, 0x44, 0x47, 0x5A, …)
```

- `flag 0x20000000.bit2` = "polling round complete": `0x14ae` sets it after the last slave of the round (`0x1570`), `0x99ba` clears it in the measurement cycle (about 1 s) after recomputing the system aggregate (`0x9a34`–`0x9a3a`). Then the next round starts. The bit does **not** switch to the dispatcher: while it is set, the main loop skips both polling and dispatcher (`0x6274`–`0x627a` → `0x628e`). *(confirmed)*

- `rs485_address` = RAM `0x20000027` (DIP switch). *(confirmed)*
- `slave_count` = RAM `0x20000026`, maximum **21** (0x15). *(confirmed)* If the function switch byte `0x2000002f` bit 5 is set, the master determines the number itself: start value 1 if its pin 9 is low, otherwise 0 (`0x944C`). If the last slave answers validly and reports event 8 bit 7 = 0 (successor present), `0x14AE` increments the number by 1. If it reports bit 7 = 1 or drops out (failure counter ≥ 10), the chain ends at that slave (`0x152A`–`0x1566`). Upper limit 21. *(confirmed)*
- Consequence *(confirmed, code and practice)*: In master mode the main loop calls only the polling, never the normal ASCII dispatcher. **On the pack bus the master does not answer any requests**, not even between rounds. External queries there also collide with its polling ("multimaster collisions"). The master is read via the RS485 bus of the CAN socket.

### Taking the master off the bus during operation (DIP 5–8 to 0)

- The DIP switches are not only read at startup: `0x2112` runs in the main loop's measurement cycle (`0x6152`–`0x6160`, about 1 s) and rewrites the slave count from DIP 5–8 to `0x20000026` every time (`0x21BE`, only if BitGroup7 bit 5 is off). *(confirmed)*
- With BitGroup7 bit 5 (automatic addressing) disabled, setting DIP 5–8 on the master to 0 during operation makes the main loop take the normal dispatcher `0x1132` immediately: polling stops, the master answers requests to address 0 on the pack bus, and the bus is free for an external client. Switching back restarts polling without a reboot. *(confirmed in code; whether "all OFF" decodes as 0 on the hardware has not been measured)*
- ⚠ **Limitation:** While DIP 5–8 are at 0, the master reports only **its own values as a single-pack system** to the inverter: capacity, SOC and current of the master pack only, DCL immediately for 1 pack. With unchanged gate/alarm state and no immediate zero/heating override, CCL falls via the ordinary ramp, by 1 A per second (step = packs online × 1 A, `0x995C`–`0x9986`), so from a large starting value it takes many minutes to reach the single-pack value. *(confirmed)*
  - Reason: with address 0 and slave count 0, `0x944C` clears the flag byte `0x20000000` and the online bitmask (`0x94C6`–`0x94CE`). Immediately afterwards (`0x6212`), `0x12E2` sets its own online bit (`0x1364`–`0x136A`) and bit 2 again (`0x136C`–`0x1380`). `0x99BA` therefore recomputes the aggregate every second, but only from its own pack. The same applies to a master operated alone.
  - The inverter thus sees only a fraction of the current and capacity while all packs keep delivering power. Every pack still protects itself via its MOSFETs. Even so, the inverter should be set to **"no battery power"** for this maintenance window.

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

- The edge is detected in `0x8A24` (shadow `0x200000F0`); ASCII 0x45 type 4 also sets the request directly (`0x0A96`–`0x0ABC`). It is stored in `0x20000000` bit 5 (on) or bit 4 (off).

**Meaning of the broadcast:** on/off only clears or sets the slave's logical off bit. Charging remains possible; charging recovery and eligible port-voltage wakeup can clear off. On does not force either gate against subsequent protection processing. Unicast off is therefore not a permanent per-pack lock. CCL/DCL follow actual paths and alarms, not off alone. [OEM details](../firmware/power-on-off.md).
- Slaves do not respond to broadcasts.
- Details on CID2 0x45: [CID2 0x45: Remote control](seplos-ascii.md#53-cid2-0x45-remote-control).

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
- There is a failure counter per pack. From the **11th** consecutive missed or invalid attempt (counter ≥ 10, `0x14FE`–`0x1528`), the pack's bit in the online bitmask is cleared (`0x20000500 + 0x18`, 32 bits, bit n = pack n). On a valid response the counter is reset and the bit is set. *(confirmed)*
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
| 27 | 54–55 | **Alarm event 6** (miscellaneous) | bit field, unfiltered (only 0x44 applies `& 0x7F`) | `0x20000035` | confirmed |
| 28 | 56–57 | **Switch state (On-off state)** | bit field | `0x200000b5` | confirmed |
| 29 | 58–59 | **Alarm event 7** | bit field, unfiltered (in 0x44 only `& 0x30`) | `0x20000036` | confirmed |
| 30 | 60–61 | **Alarm event 8** bits 0–6, **bit 7 = internal flag** | bit field | `(0x20000005 & 0x7F) \| (0x80 if 0x200000f6.bit3 == 0)` | confirmed (bit 7: input GPIO pin 9, see [firmware-analysis §8.2d](../hardware/internal-address-chain.md#confirmed-firmware-mechanism)) |
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
| Event 6 | Charger overvoltage | **Intermittent recharge waiting** | Remaining capacity alarm | Remaining capacity protection | Charging blocked (cell too low) | Reverse polarity (never set) | Output connection fault (GPIO input) | Current limiter not ready (only visible in 0x5A, masked in 0x44) |
| On-off | Discharge MOSFET on | Charge MOSFET on | Current limiting on | Heater on | Precharge in progress (P57) | Discharge MOSFET just switched on (100 ms) | External voltage at port with MOSFET open | – |
| Event 7 | **Balancing active** | **Balancing blocked / not needed** | Balancing time limit reached | Balancing blocked due to ambient temperature | Charge activation automatic | Charge activation manual | Charging via current limiter from 10 A | Current limiting after charge overcurrent warning |
| Event 8 | EEPROM fault | RTC fault | Voltage not calibrated | Current not calibrated | Zero point not calibrated | RTC time invalid | internal: "charging forbidden" request (controls the charge MOSFET, see SP80 in [firmware-changelog.md](../firmware/firmware-changelog.md)) | in 0x5A: **input GPIO pin 9 high** (presumably "no address request from neighbouring pack"; always 1 with DIP addressing) |
| System status | Discharging | Charging | "Float" = charger/external voltage detected at port (no float mode; visible only here, hidden in 0x44) | – (never set) | Standby | Off (shutdown) | **Discharge current ≥ 3 A** | **Charge current ≥ 3 A** |

Thresholds and origin of all system status bits: [Charging / discharging / standby / off (system status)](../firmware/states-and-triggers.md#charging--discharging--standby--off-system-status). When the SOC stays at 98.2 % or jumps to 98/100 %: [states-and-triggers](../firmware/states-and-triggers.md).

## Examples, fully decoded

### Schematic 32-byte INFO response

This is a calculated example with synthetic measurements and an arbitrary pack
address. It is not a captured installation log.

Complete frame, with calculated checksum:
`~2001465AC04000010CE40CDA0BA50B9B000014A027104E2001F414A000000000000003028010F052\r`

| Field | Raw value | Value |
|---|---|---|
| Header | `20 01 46 5A C040` | VER 2.0, arbitrary address 1, CID1 0x46, CID2 0x5A, 32 INFO bytes |
| DATA FLAG / constant | `00 01` | – |
| Highest cell voltage | `0CE4` | 3.300 V |
| Lowest cell voltage | `0CDA` | 3.290 V; spread 10 mV |
| Highest cell temperature | `0BA5` | 2981 → 25.0 °C |
| Lowest cell temperature | `0B9B` | 2971 → 24.0 °C |
| Current | `0000` | 0.00 A |
| Pack voltage | `14A0` | 52.80 V |
| Remaining capacity | `2710` | 100.00 Ah |
| Full capacity | `4E20` | 200.00 Ah |
| SOC | `01F4` | 50.0 % |
| Port voltage | `14A0` | 52.80 V |
| Alarm events 1–6 | `00 00 00 00 00 00` | No alarms |
| Switch state | `03` | Discharge and charge MOSFET on |
| Alarm event 7 | `02` | Bit 1: balancing blocked or not needed |
| Alarm event 8 | `80` | No faults; bit 7 = 1 with DIP addressing |
| System status | `10` | Standby; consistent with zero current |

### Schematic decoder-label mapping

If a decoder calls the two temperatures “Temperature 1” and “Temperature 2”,
they are **highest and lowest cell temperature**, not individual sensor readings.
The final ten INFO bytes in this synthetic example map as follows:

| Bytes | Correct mapping |
|---|---|
| First `00 00` | Alarm events 1 and 2 |
| Second `00 00` | Alarm events 3 and 4 |
| Third `00 00` | Alarm events 5 and 6 |
| `03 02` | Switch state: both MOSFETs on; event 7: balancing blocked/not needed |
| `80 10` | Event 8: no faults, DIP-addressing flag; system status: standby |

This accounts for all 32 bytes. The 0x5A response contains ten measurements and
ten status bytes. Individual cell voltages, individual temperature sensors,
cycle count, ambient and power section temperatures, SOH and charge/discharge
current limits are **not** transmitted in the 0x5A snapshot. Query each slave
directly using 0x42/0x44 for its cells, sensors, cycles, SOH and actual gate state. CCL/DCL are system aggregates exposed through the inverter protocols, not per-slave fields in 0x42/0x44.

## Historical capture validation

The private [structured capture fixtures](../../local/fixtures/emulation/intra-pack/README.md)
retain 24 actual replies, the separately identified issue #116 example and decoder-log
label mappings. Their JSON records preserve exact source tokens, source SHA-256/line
provenance, checksum/LENGTH results and decoded expectations. Use these fixtures for
offline decoder/emulation comparisons. The ignored local records are unavailable in
a fresh public checkout. The synthetic example above preserves the public decoding
method without reproducing an installation's operating history.

The relevant interpretation remains: system status distinguishes standby,
charging and discharging, with a separate charge-current ≥ 3 A flag and hysteresis
(retained down to 2.80 A). Alarm event 2 bit 0 indicates cell high alarm and bit 4
pack high alarm. See the firmware status/trigger analysis for the exact conditions.

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
| 16.06.13 | format unchanged; the snapshot is located 8 bytes further on (`0x20000524`), In the ASCII dispatcher 0x5A remains a single comparison (`0x1152`); new is a second jump table for CID2 0xA0–0xAB instead of the comparison chain in 06.12. New in the same area: CID2 0xAA/0xAB (see [ASCII tunnel commands](seplos-ascii.md#515-cid2-0xaa--0xab-from-0613-tunnel-to-the-binary-port)). |


**Role and bus availability (.13, confirmed):** only address 0 with an effective slave count >0 polls UART0 (`0x6264–0x628A`). At nonzero addresses the DIP slave count becomes 0 (`0x21CA–0x21D2`). Address 0/count 0 still serves UART1 system protocols and CAN, but aggregates only itself. The manufacturer also specifies a PC/FSU polling packs 1…N without a Seplos master; the external requester must aggregate. Automatic addressing Group7.Bit5 can override DIP, so DIP5–8 OFF alone does not guarantee a quiet bus.
