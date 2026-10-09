# Seplos 10E / EMU1101 (SH Energy ETECH): Firmware Analysis

This file summarizes the technical analysis of the firmware files under `../firmware/ehex/`: file format, memory layout, architecture, RAM usage, parameters and protection logic. The protocols are documented in separate files (see [README](../README.md)).

Confidence: **confirmed** = read directly from the code/bytes · **probable** = inferred from data flow/context · **assumption** = plausible, not proven. Unless stated otherwise, addresses refer to **V16.06.13**.

---

## 1. Files examined

| File (`firmware/ehex/`) | Lines | SHA-256 (prefix) | Image size | Stack top | Reset vector | Image SHA-256 (prefix) |
|---|---|---|---|---|---|---|
| `CAN1101[V16.04.06_PN01_220924_9600].ehex` | 3024 | `2b00410571fcb9da` | 48,096 B (0xBBE0) | 0x200017D8 | 0xB629 | `fa38fbd4dba02eb4` |
| `CAN1101[V16.06.03_PN01_230412].ehex` | 3017 | `246e1eca5637bcc1` | 47,980 B (0xBB6C) | 0x20001A90 | 0xB5BD | `689d3819eb9f73e1` |
| `CAN1101[V16.06.04_PN01_230613].ehex` | 3137 | `d69f27c1650e31cf` | 49,900 B (0xC2EC) | 0x20001A90 | 0xBD29 | `390299c85aae21b1` |
| `CAN1101[V16.06.05_PN01_230916_SP80].ehex` | 3137 | `c8f0560b7d32df30` | 49,900 B (0xC2EC) | 0x20001A90 | 0xBD29 | `a2abc282abf9d344` |
| `CAN1101[V16.06.11_PN01_240713].ehex` | 3297 | `2dae963fd5aa11aa` | 52,452 B (0xCCE4) | 0x20001A90 | 0xC70D | `b686b69e69878390` |
| `CAN1101[V16.06.12_PN01_241209].ehex` | 3298 | `46d25a5f565ae014` | 52,472 B (0xCCF8) | 0x20001A90 | 0xC721 | `f487ac4bc3b89c5f` |
| `CAN1101[V16.06.13_PN01_250607].ehex` | 3337 | `0ea75c9834cf1978` | 53,092 B (0xCF64) | 0x20001A98 | 0xC985 | `5c36a7e08fb881b3` |

Contents of the ZIP files in the `Firmware/` folder: each contains exactly the `.ehex`, some with macOS metadata (`__MACOSX/`). **Exception:** the 06.11 ZIP additionally contains `Seplos update doc.docx`, an update guide (section 9). Seplos does not include a changelog with any package.

**File name scheme** *(probable)*: `CAN1101[V<HW>.<Major>.<Patch>_PN01_<YYMMDD>[_Suffix]]`
- `CAN1101`: product EMU1101 with CAN
- `V16`: hardware version 16 (matches `HW16` in the header)
- `06.13`: firmware line and patch
- `PN01`: presumably project/part number 01
- `YYMMDD`: build date
- Suffix `_9600`: pack bus (UART0, RS485-1/2) at **9600 baud**. From 16.06.03 on it is 19200 baud *(confirmed, UART0 init)*. `_SP80`: special build

---

## 2. The `.ehex` format

An `.ehex` is an ASCII file with CRLF line endings: **16 pseudo Intel HEX records as a header**, followed by **regular Intel HEX**. *(confirmed)*

### 2.1 Header (256 bytes)

- Every record has the form `:10 0000 00 <16 bytes> AA`: length 16, address always 0000, type 00, **checksum always `AA`**. The checksum is therefore deliberately invalid; *presumably* this is how the update tool recognizes the header (the update tool and bootloader code are not available).
- The payloads of the 16 records together make up 256 bytes. *(An earlier version said 15 records / 240 bytes; recounted in all 7 files, there are 16 records with checksum `AA`. The 16th went unnoticed because, as a record at address 0, it is overwritten by the real code.)*

| Bytes | Content (identical in all 7 versions) | Meaning |
|---|---|---|
| 0–15 | `SWM181RCT6_64_M0` | MCU: **Synwit SWM181 RCT6**, Cortex-**M0**; "64" presumably flash variant/clock specification |
| 16–31 | `EMU1101_10D_HW16` | Device **EMU1101**, variant "10D", **hardware 16** |
| 32–47 | `RS485Y19200N9600` | Interface **RS485**. *Assumption:* "Y 19200" = update/bootloader baud rate (the update guide states 19200), "N 9600" = normal operating baud rate (default 9600 according to the protocol PDF) |
| 48–255 | `0x55` × 208 | Padding bytes |

The update tool presumably checks only this header for compatibility. There is **no** cryptographic signature or encryption. *(confirmed: the code is plain Thumb, and there is no signature/CRC structure over the image)*

### 2.2 Payload

- Type 00 records with 16 bytes (the last one shorter), contiguous addresses from `0x0000`, **valid Intel HEX checksums**.
- No type 04 (Extended Linear Address) records: all seven files contain only types 00, 05 and 01 after the header. *(confirmed)*
- Type 05 (Start Linear Address) = **`0x000000C1`**. This is the Keil entry `__main` in Thumb mode; the reset handler jumps there after hardware initialization. *(confirmed)*
- Type 01 (EOF).

The header is the only difference from regular Intel HEX. Removing the first 16 lines yields a file that any Intel HEX tool can read.

---

## 3. Image and memory layout

| Region | Content |
|---|---|
| `0x0000–0x00BF` | Cortex-M0 vector table (48 entries: SP, Reset, NMI, HardFault, …, 32 IRQs) |
| `0x0020`, `0x0024` | Reserved vector slots with **fixed values** `0x0B11FFAC` / `0x00006000`, identical in all versions. *Assumption:* Synwit-specific identifier or configuration (bootloader magic/ISP parameters) |
| `0x00C0` | Keil `__main` (scatter loader, entry 0xC1) |
| `0x00C0 … ~0xCC00` | Code (Thumb-1) with interspersed literal pools |
| after that | Constants: version, strings, NTC table, CRC tables, Keil runtime |
| End | Keil region table / RW init (`…0106000100366e01 18000000`, identical in all versions) |

- **Link address 0x00000000.** The application therefore sits at the start of flash. How the update over RS485 at 19200 baud works (section 9) cannot be determined from the image: either the SWM181 has an ISP loader in ROM, or a bootloader resides in another flash region. *(open)*
- **RAM:** The stack top is at `0x20001A98` (06.13), and at `0x200017D8` in 04.06. The RAM is therefore at least 6.8 KB, and the used region has grown across versions.
- **Compiler:** Keil MDK / ARMCC. Evidence: `__main` at 0xC0, `__ARM_common_switch8` jump tables (06.13 at `0xCBE4`), division via `__aeabi_uidiv`/`idiv` (06.13 `0xC9DC`/`0xCA08`), region table. *(confirmed)*
- **Peripherals:** The base addresses `0x4000_0000`, `0x4100_0000`, `0x4300_0000`, `0x4500_0000`, `0x5000_0000…0x5004_0000` and SCB/NVIC `0xE000_E000` are used. The set is **identical in all versions**, so the updates change only logic and protocols, not hardware usage. *(confirmed)*
  - GPIO `0x5000_2000` *(confirmed, from all writers)*: outputs bit 10 current limiter, bit 11 heater or relay (low = on), bit 12 **charge MOSFET**, bit 13 **discharge MOSFET**, bit 15 precharge path (soft start); inputs bit 1 button (low = pressed), bits 7/8/9 pulse addressing (§8.2d), bit 14 current limiter stage feedback.
  - GPIO `0x5000_1000`: input bit 0 external on/off switch (BitGroup7 bit 0), output bit 1 supply self-latching *(probable)*, input bit 10 output connection fault (BitGroup5 bit 6). *(confirmed, except the interpretation of bit 1)*
  - **Timing:** Timer 0 every **5 ms** (measurement, fast overcurrent/short-circuit path, soft start), timer 1 every **1 s** (coulomb/energy counter). The measurement sequencer counts 200 × 5 ms and then starts the main loop, which therefore also runs **exactly once per second** (06.13 `0x5FC4`, `0x1ABA`). All "cycles" in the protection logic are seconds. *(confirmed)*

---

## 4. Constants and strings

From `0xCC1C` (06.13; 06.11 `0xC9A4`, 06.04 `0xBFC0`, 06.03 `0xB854`, 04.06 `0xB8C0`):

| Offset | Content | Remark |
|---|---|---|
| +0x00 | `10 06` | **Firmware version 16.06**, the only version information in the image. 04.06 has `10 04`. The patch number (03/04/05/11/12/13) appears **nowhere in the image** (proof: 06.04 and 06.05 differ in exactly one byte, see [CHANGELOG](firmware-changelog.md)) *(confirmed)* |
| +0x02 | `CAN:PNG_DYE_Luxp_TBB` | Name of CAN protocol 1 (Pylontech; Deye, Luxpower, TBB …) |
| +0x16 | `CAN:Growatt_SPF_SPH ` | Protocol 2 |
| +0x2A | `CAN:Victron         ` | Protocol 3 |
| +0x3E | `CAN:SMA_SOFAR       ` | Protocol 4 |
| +0x52 | `CAN:GINLONG         ` | Protocol 5 |
| +0x66 | `CAN:Studer          ` | Protocol 6 |
| +0x7A | `CAN:MUST            ` | Protocol 7, **only from 06.11** |
| +0x8E | `SH-EnergyTCH Co.,Ltd` | Manufacturer name, **from 06.04** (20 characters) |
| after that | `05 07 06 04 00 03 01 02` | **Channel order of the 8-way analog multiplexer**: in steps 16–23 (after the 16 cell channels), the measurement sequencer `0x1ABA` selects these channels via GPIO `0x50004000` bits 4–6. Which sensor is connected to which channel is determined by the hardware. *(confirmed)* |
| after that | `8B7C F979 A579 …` | descending uint16 table = **NTC curve** (ADC → temperature), identical in all versions |

Further strings:
- `EMU110110E` (10 characters): default device name. It is copied to RAM `0x20000042` and output in CID2 0x47/0x51 and Modbus.
- `EMU110110S-XXXX-20220120-00001` (three times): default/placeholder serial number (barcode), identical in all versions.
- New in 06.13 is a short byte table (`0C 36 33 42 45 48 4B 4F 73 …`, at `0x117E`). This is not a data table but the **jump table of the ASCII dispatcher** for CID2 0xA0–0xAB (behind `bl 0xCBE4`, Keil `switch8`). *(confirmed)*

---

## 5. Firmware architecture (06.13)

### 5.1 Main loop and communication modes

- The RS485 address comes from the DIP switch (`0x20000027`). The DIP switch is read **analog**: switches 1–4 and 5–8 are each connected to a resistor network, and the firmware quantizes the two ADC values to 0–15 via the table `0xCE16` (`0x2112`). **Switches 1–4 = address** (0 = master, slaves 1–15), **switches 5–8 = number of slaves** (master only; at address ≠ 0 the number becomes 0). This allows at most 16 packs via DIP; the upper limit of 21 in the code applies only to automatic detection (BitGroup7 bit 5). *(confirmed; confirmed by the Seplos specification, chapter 4.4)*
- **Address 0 with at least one slave** → **master mode:** the pack polls the slaves with CID2 0x5A (see [Intra-pack protocol](protocols/intra-pack.md)). Otherwise, as a slave, it processes ASCII commands (dispatcher `0x1132`).
- On the inverter-side RS485 interface (shared RX buffer `0x20000DFE`), **two protocols run in parallel**:
  - **Pylontech ASCII** (frames with `~`, dispatcher `0x2AF2`: CID2 0x42, 0x44, 0x4F, 0x51, 0x60, 0x61, 0x62, 0x63), see [Pylontech RS485](protocols/pylontech-rs485.md)
  - **Modbus RTU** (dispatcher `0x45AC`, only active if `0x200000F7` bit 7), see [Modbus RTU](protocols/modbus-rtu.md)
- In addition there is **CAN** (protocol according to `0x20000024`), see [CAN protocols](protocols/can.md).
- There is also a **binary protocol** (`0x55 … 0xAA`, dispatcher `0x8288`, active if function switch `0x2000002f` bit 3). See [Protocol extensions](protocols/undocumented-commands.md).

### 5.1a Interfaces and peripherals *(confirmed unless stated otherwise)*

| Interface | Peripheral | Protocols | Remark |
|---|---|---|---|
| RS485 pack bus / PC, **sockets RS485-1/RS485-2** | **UART0** `0x50010000`, direction pin GPIO `0x50002000` bit 6, **19200 baud** (04.06: 9600) | Seplos ASCII with full command set (0x42…0xAB), intra-pack 0x5A | Master polls slaves; BatteryMonitor; firmware update (19200) |
| RS485 inverter, **RS485 pair of the CAN socket** | **UART1** `0x50011000`, **9600 baud** | **Modbus RTU** (read-only) + **Pylontech ASCII** (0x42/0x44/0x4F/0x51/0x60–0x63) on the same buffer | 0x42/0x44/0x51: each pack under its DIP address (bus operation of all packs incl. master possible); Modbus and 0x60–0x63: master only |
| RS232/TTL (display/dongle) | **UART2** `0x50012000`, 9600 8N1, without direction control | **Binary protocol** `0x55…0xAA`, CRC-16/XMODEM | active with function switch `0x2F` bit 3; device *assumption*: LCD/Bluetooth/WLAN |
| CAN | SJA1000-like `0x50020000`, pins port `0x50002000` pin 2/3 | 7 inverter protocols; **transmit only**, no reception | 500 kbit/s, MUST 100 kbit/s; only the master transmits |
| I²C | Hardware I²C controller `0x50018000`: device **0xA2 = RTC** (time; register 2 bit 7 → event 8 bit 5), device **0xA4 = history EEPROM** (500 × 128 bytes, header 0xFF00) | – | *(confirmed)* |
| Flash records | Settings and counters in **internal flash** via IAP (`0x4748` write, `0x47A8` read), address 0x25000 + block·0x1000, each with a mirror copy 0x1000 behind it and CRC-16/Modbus. Block 0 parameters, 2 calibration, 4 strings/device data/CAN protocol, 6 capacities/energy/cycles (§8.2e). The byte 0xA0 is the identifier of these records | – | *(confirmed)* |
| RTC | (driver `0x58E2`/`0x5882`) | ASCII 0x4D/0x4E | Error → event 8 bit 1 |
| Watchdog | `0x50009000` | ASCII 0x45 type 6 = restart | |

### 5.2 Function map (selection, 06.13)

| Address | Function | Confidence |
|---|---|---|
| `0x00C0` | Keil `__main` | confirmed |
| `0x0316` | Read hex ASCII → byte from the RX buffer; **accepts upper-case letters only** (lower-case letters yield 0) | confirmed |
| `0x03A4` | ASCII CID2 0x42 telemetry response | confirmed |
| `0x05B4` | ASCII CID2 0x44 alarm response | confirmed |
| `0x06E8` | ASCII CID2 0x47 read parameters | confirmed |
| `0x07C4` | ASCII CID2 0xA1 | confirmed (mapping) |
| `0x09B4` | ASCII CID2 0x49 set parameters | confirmed (mapping) |
| `0x0A3C` | ASCII CID2 0x45 remote control | confirmed (mapping) |
| `0x0ACA` | ASCII CID2 0x51 device info | confirmed |
| `0x0BBE` | ASCII CID2 0xA0 | confirmed (mapping) |
| `0x0C2E` | ASCII CID2 0x4B history | confirmed (mapping) |
| `0x0CA0` / `0x0CF0` | ASCII CID2 0x4D / 0x4E read/set time | confirmed (mapping) |
| `0x0D64`, `0x0DC0`, `0x0E20`, `0x0E46` | ASCII CID2 0xA2, 0xA3, 0xA4, 0xA5 | confirmed (mapping) |
| `0x0EA6` | ASCII CID2 0xA6 set CAN protocol | confirmed |
| `0x0EEC` | Check ASCII frame on the pack bus (address, checksums) | confirmed (role), individual steps not all traced |
| `0x102C`, `0x02A2` | Build response header with address / start transmission on the pack bus (with direction pin) | confirmed |
| `0x02EA` | Byte → two hex digits, **always upper case** | confirmed |
| `0x10D6` | ASCII CID2 0x5A intra-pack response | confirmed |
| `0x1132` | ASCII CID2 dispatcher (jump tables 0x42–0x51 and 0xA0–0xAB) | confirmed |
| `0x128E` | (new in 06.13) relay response for the 0xAA/0xAB mechanism | confirmed (function), purpose see protocol file |
| `0x12E2` | own measurements → intra-pack snapshot `0x20000524` | confirmed |
| `0x1384` | Master: write a slave's 0x5A response into the pack table | confirmed |
| `0x13F6` | Master: send next 0x5A request or 0x45 broadcast | confirmed |
| `0x14AE` | Master: response evaluation, online bitmask, slave count | confirmed |
| `0x1FCA` | Determine max/min cell voltage (`0xcc8+0/+2`) | confirmed |
| `0x2112` | Take over temperatures from ADC/NTC; with ≤ 8 cells, sensors 3/4 = sensor 2 | confirmed |
| `0x2600` | Pylontech RS485 CID2 0x60 system basic info (name, "SH-EnergyTCH Co.,Ltd", version, up to 4 serial numbers) | confirmed |
| `0x26A8` / `0x278C` / `0x2882` | Pylontech RS485 CID2 0x61 / 0x62 / 0x63 | confirmed (mapping) |
| `0x28F0` | Inverter port: decode frame | confirmed |
| `0x2A40` | Pylontech RS485: build response header `~20 ADR 46 RTN LEN` | confirmed |
| `0x2AF2` | Pylontech RS485 dispatcher (inverter port) | confirmed |
| `0x25B2` | Inverter port: start transmission (with direction pin) | confirmed |
| `0x2B80…0x432A` | Modbus register handlers (see [Modbus RTU](protocols/modbus-rtu.md)) | confirmed |
| `0x43A6` | Modbus: check FC/start address (FC 03/04 only, otherwise exception 01) | confirmed |
| `0x4554` | Modbus: append CRC and send | confirmed |
| `0x45AC` | Modbus dispatcher | confirmed |
| `0x53D8` | Save flash block 4 (strings, device data, CAN protocol) | confirmed |
| `0x5564` / `0x55CE` | Flash block 6 (remaining/full capacity, energy counters, cycles) save / load at startup | confirmed |
| `0x6894` | Check sensor/connection faults (BitGroup0 bit 1, BitGroup5 bit 6); **not** the general event mask. Event 2 is masked with BitGroup1 in `0x6686` | confirmed |
| `0x66C2` | Temperature alarms (cell/ambient/power stage) and heater | confirmed |
| `0x6FFA` | "Charging forbidden" logic, control of the charge MOSFET (SP80 location) | confirmed |
| `0x75A8`, `0x75E6` | Binary protocol: send, CRC | confirmed (role) |
| `0x77DC` | Binary protocol: extended status frame (format A) | confirmed |
| `0x8288` | Binary protocol dispatcher | confirmed |
| `0x9A88` | CAN initialization (500 kbit/s or 100 kbit/s for MUST) | confirmed |
| `0x9B2E` | CAN bus-off recovery | confirmed |
| `0x944C`/`0x94D2`/`0x96CE`/`0x98A8`/`0x99BA` | Master aggregation: sums/extreme values, counts/flags, limits CVL/CCL/DVL/DCL, sequence control | confirmed |
| `0xA826` | CAN frame set protocol 1 (Pylontech/Deye) | confirmed |
| `0xAEBA` | CAN transmit dispatcher | confirmed |
| `0xC4DA` | Send CAN frame | confirmed |
| `0x4C3C` | Parameter plausibility check (before taking over 0xA1) | confirmed |
| `0x4890` / `0x4748` | Write parameter block to **internal flash** (`0x25000 + block × 0x1000`, erase + program, mirrored copy +0x1000) | confirmed |
| `0x5174` | Save calibration data | confirmed |
| `0x5998` / `0x574C` | Write history record / EEPROM driver | confirmed |
| `0x5D76` | Clear history and reset counters (ASCII 0x45 type 5) | confirmed |
| `0x7350` | Forced heating (counter `0x200000C8`) | confirmed |
| `0x8A24` | On/off edge → master broadcast 0x45 | confirmed |
| `0xCBE4` | Keil `__ARM_common_switch8` | confirmed |

---

## 6. RAM usage (06.13)

In 06.13, many variables above approx. `0x200000C0` are shifted by **+8 bytes** compared to 06.12. The low addresses have been stable since 06.03.

| Address | Type | Content | Confidence |
|---|---|---|---|
| `0x20000000` | u8 | Master's pack bus: bit 0 request sent/response expected, bit 1 request finished (timeout 150 ms), bit 2 polling round over all slaves complete (then aggregation `0x99BA`, reset once per second), bit 3 pack communication error (30 consecutive rounds with fewer packs online than configured), bits 4/5 broadcast 0x45 type 4 off/on pending | confirmed |
| `0x20000005` | u8 | **Alarm event 8** (bit 0 EEPROM, 1 RTC, 2–4 calibration, **bit 6 = internal request "charging forbidden"**) | confirmed |
| `0x20000006/07` | u8 | Balancing status cells 1–8 / 9–16 | confirmed |
| `0x20000024` | u8 | **active CAN protocol** 1…7 (1 = PNG_DYE_Luxp_TBB/Pylontech) | confirmed |
| `0x20000025` | u8 | `0x55` = "save settings" | confirmed |
| `0x20000026` | u8 | Number of slave packs (master), max. 21 | confirmed |
| `0x20000027` | u8 | RS485/DIP address | confirmed |
| `0x20000028…2F` | u8 ×8 | **Function switches** (BatteryMonitor "BitGroup0…7"), see section 7.3 | confirmed |
| `0x20000030…35` | u8 ×6 | **Alarm events 1…6** | confirmed |
| `0x20000036` | u8 | **Alarm event 7** | confirmed |
| `0x20000042` | char[10] | Device name (`EMU110110E`) | confirmed |
| `0x2000004C` | char[30] | String 1, **pack serial number** (ASCII 0xA2/0xA3; in Modbus FC04 0x0000 and Pylontech 0x60) | confirmed (meaning probable) |
| `0x2000006A` | char[30] | String 2 (ASCII 0xA4/0xA5) | confirmed (meaning open) |
| `0x200000C8` | u16 | Remaining time of forced heating (ASCII 0x45 type 3, start value 3600) | confirmed |
| `0x200000E9` | u8 | (06.13) shadow of the system status for the off/on edge (binary 0xA2/0xA3) | confirmed |
| `0x200000F8` | u8 | Bit 2 = heater minimum charge current active (CCL ≥ packs × 10 A) | confirmed |
| `0x200012F6/F8/FA` | u16 | History: count / start / read pointer | confirmed |
| `0x20001634` / `0x20001627` / `0x2000161E` | struct | Master aggregates: extreme values / pack numbers of the extreme values / OR of all alarm events | confirmed |
| `0x200015E0` / `0x200015EC` | u32 | Coulomb counter: maximum (full capacity·3600) / current value (remaining capacity·3600) | confirmed |
| `0x200000AC` | u8 | **System status** (bit 0 discharging, 1 charging, 2 "Float" = internal "charge path active" flag, not a float charging mode, 3 never set, 4 standby, 5 off, 6 discharge current ≥ 3 A, 7 charge current ≥ 3 A; see §8.2c) | confirmed |
| `0x200000B5` | u8 | **On-off state** (bit 0 discharge MOS, 1 charge MOS, 2 current limiting, 3 heater) | confirmed |
| `0x200000BB` | u8 | (from 06.12) unfiltered hysteresis state of the cell temperature alarms | confirmed |
| `0x200000E8` | u8 | (06.13) state of the 0xAA/0xAB relay (1…4) | confirmed |
| `0x200000EA…EF` | u8 ×6 | (06.13) 6 data bytes of the 0xAA/0xAB relay | confirmed |
| `0x200000F7` | u8 | Master system flags: bit 0 discharging, 1 charging, 2 highest cell ≤ OVP + 30 mV, 3 discharging possible, 4 SOC ≤ 5 %, 5 SOC ≤ 9 %, 7 master/inverter communication active (CAN, Modbus, Pylontech) | confirmed |
| `0x20000108` | struct | ASCII protocol: state and transmit buffer | confirmed |
| `0x20000304` | buf | ASCII protocol: receive buffer | confirmed |
| `0x20000500` | struct | Master polling: current pack index, error counter, online bitmask (+0x18) | confirmed |
| `0x20000524` | 30 B × 22 | **Pack table** (index 0 = own pack), see intra-pack protocol | confirmed |
| `0x20000C78` / `0x20000CA0` | struct | the two **current measurement channels** A (measurement channel) and B (reference/offset), each two records of 0x14 bytes; result in mA at `+8` = (raw value − zero point) × factor / reference (`0x2218`); zero-point calibration `0x2348`, adjustment `0x22CC`; in 0x42 as "Reserved 1/2" | formula confirmed, field names probable |
| `0x20000CC8` | struct | **Measurements**, see 6.1 | confirmed |
| `0x20000DDC` | u8[] | Byte alarms (0x44): cells 0–15, +0x10–13 cell temp., +0x14 ambient, +0x15 power stage, +0x16 pack voltage, +0x18 current | confirmed |
| `0x20000DFE` | buf | Modbus RTU: receive buffer (response from `+0x120`) | confirmed |
| `0x20001300` | u16 ×60 | **Parameters 0…59**, see 7.1 | confirmed |
| `0x200013F0` | u8 ×27 | **Parameters 60…86**, see 7.2 | confirmed |
| `0x20001426` / `0x200014E6` | buf | Binary protocol: transmit/receive buffer | confirmed |
| `0x2000164C` | struct | System values for the inverter protocols (current int32 `+0xC`, voltage `+0x10`, … as well as u32 `+0x2C`/`+0x30`), see Modbus RTU §2 | confirmed |

### 6.1 Measurement structure `0x20000CC8`

| Offset | Type | Content | Unit |
|---|---|---|---|
| +0x00 | u16 | highest cell voltage | mV |
| +0x02 | u16 | lowest cell voltage | mV |
| +0x04 | u16 | highest cell temperature (max of the 4 cell sensors, `0x21D6`) | 0.1 K |
| +0x06 | u16 | lowest cell temperature (heater logic) | 0.1 K |
| +0x08 | i16 | current (+ charging / − discharging) | 0.01 A |
| +0x0A | u16 | pack voltage | 0.01 V |
| +0x0C | u16 | remaining capacity | 0.01 Ah |
| +0x0E | u16 | full capacity | 0.01 Ah |
| +0x10 | u16 | SOC | 0.1 % |
| +0x12 | u16 | port voltage (P+/P−) | 0.01 V |
| +0x14…+0x33 | u16 ×16 | cell voltages 1–16 | mV |
| +0x34…+0x3B | u16 ×4 | cell temperatures 1–4 | 0.1 K |
| +0x3C | u16 | ambient temperature | 0.1 K |
| +0x3E | u16 | power stage/MOSFET temperature | 0.1 K |
| +0x58 | u32 | **charged energy** in 0.1 kWh (confirmed: 1 Hz timer ISR `0x9044` sums I·U every second, +1 per 360,000 W·s = 100 Wh; only in system status "charging"); in 0x42 as "Reserved 3" (u16), from 65,000 on, 6500 is sent | 0.1 kWh |
| +0x5C | u32 | **discharged energy** in 0.1 kWh (confirmed, as above, only in system status "discharging"); "Reserved 4", same limitation | 0.1 kWh |
| +0x60 | u16 | cycle count | – |

Temperatures are always stored internally in 0.1 K, °C = (x − 2731)/10. Fixed thresholds in the code: 2281 (−45 °C), 2431 (−30 °C), 2631 (−10 °C), 2931 (+20 °C), **2981 (+25 °C, new in 06.11)**, 3231 (+50 °C), 3731 (+100 °C), 3931 (+120 °C), 4031 (+130 °C).

---

## 7. Parameters and function switches

The response to ASCII CID2 0x47 is: 60 × u16 from `0x20001300`, then 27 × u8 from `0x200013F0`, then the 8 switch bytes `0x20000028…2F`, then the 10-byte device name. The order corresponds exactly to the parameter list in BatteryMonitor and in the XML export. *(confirmed)*

### 7.1 Parameters 0…59 (u16, `0x20001300 + 2·i`)

Column "Value" = the example configuration export `Parameter 20260419_1308.xml` (module "1101-SP75"; [config/parameter-export-example.xml](../config/parameter-export-example.xml)). Raw value units *(confirmed, from comparisons with the measurements)*: P0–P9 mV, P10–P19 10 mV, P20–P49 0.1 K, P50–P56 10 mA (discharging negative), P57 ms, P58/P59 10 mAh, P60/P61 10 mV, P62/P63 mV, P64/P73/P77 h, P66/P67/P69 s, P68 ms, P71/P72/P75/P76 min, P84/P86 0.1 mΩ.

| i | RAM | Parameter (BatteryMonitor) | Value |
|---|---|---|---|
| 0 | 0x1300 | Cell high voltage alarm | 3.450 V |
| 1 | 0x1302 | … recovery | 3.350 V |
| 2 | 0x1304 | Cell undervoltage alarm | 2.900 V |
| 3 | 0x1306 | … recovery | 3.100 V |
| 4 | 0x1308 | Cell overvoltage protection | 3.650 V |
| 5 | 0x130A | … recovery | 3.450 V |
| 6 | 0x130C | Cell undervoltage protection | 2.700 V |
| 7 | 0x130E | … recovery | 3.100 V |
| 8 | 0x1310 | Balancing start voltage | 3.400 V |
| 9 | 0x1312 | Charging forbidden below (cell) | 1.500 V |
| 10 | 0x1314 | Pack high voltage alarm | 55.20 V |
| 11 | 0x1316 | … recovery | 53.60 V |
| 12 | 0x1318 | Pack undervoltage alarm | 46.40 V |
| 13 | 0x131A | … recovery | 48.00 V |
| 14 | 0x131C | Pack overvoltage protection | 56.00 V |
| 15 | 0x131E | … recovery | 53.60 V |
| 16 | 0x1320 | Pack undervoltage protection | 43.20 V |
| 17 | 0x1322 | … recovery | 48.00 V |
| 18 | 0x1324 | Charger overvoltage protection | 63.00 V |
| 19 | 0x1326 | … recovery | 61.00 V |
| 20–27 | 0x1328–0x1336 | Charging: overtemp. alarm/rec., undertemp. alarm/rec., overtemp. protection/rec., undertemp. protection/rec. | 50/47, 2/5, 55/50, −10/0 °C |
| 28–35 | 0x1338–0x1346 | Discharging: same | 52/47, −10/3, 55/50, −15/0 °C |
| 36 | 0x1348 | Cell heater on | 0.0 °C |
| 37 | 0x134A | Cell heater off | 10.0 °C |
| 38–45 | 0x134C–0x135A | Ambient: high alarm/rec., low alarm/rec., overtemp. protection/rec., undertemp. protection/rec. | 50/47, 0/3, 60/55, −10/0 °C |
| 46–49 | 0x135C–0x1362 | Power stage: alarm/rec., protection/rec. | 90/85, 100/85 °C |
| 50 | 0x1364 | Charge overcurrent alarm | 150 A |
| 51 | 0x1366 | … recovery | 145 A |
| 52 | 0x1368 | Discharge overcurrent alarm | −155 A |
| 53 | 0x136A | … recovery | −153 A |
| 54 | 0x136C | Charge overcurrent protection | 160 A |
| 55 | 0x136E | Discharge overcurrent protection | −160 A |
| 56 | 0x1370 | Transient overcurrent protection | −300 A |
| 57 | 0x1372 | Soft start delay | 2000 ms |
| 58 | 0x1374 | **Rated capacity** (in 0x42 as "Rated capacity") | 280.00 Ah |
| 59 | 0x1376 | SOC / remaining capacity (set value) | 75.00 Ah |

### 7.2 Parameters 60…86 (u8, `0x200013F0 + (i−60)`)

| i | RAM | Parameter | Value |
|---|---|---|---|
| 60 | 0x13F0 | Cell difference fault | 0.50 V |
| 61 | 0x13F1 | … recovery | 0.30 V |
| 62 | 0x13F2 | Balancing on above difference | 0.030 V |
| 63 | 0x13F3 | Balancing off below difference | 0.020 V |
| 64 | 0x13F4 | Static balancing, time | 10 h |
| 65 | 0x13F5 | **Cells in series** (= cell count in 0x42/0x44) | 16 |
| 66 | 0x13F6 | Charge overcurrent delay | 10 s |
| 67 | 0x13F7 | Discharge overcurrent delay | 10 s |
| 68 | 0x13F8 | Transient delay | 30 ms |
| 69 | 0x13F9 | Overcurrent recovery delay | 60 s |
| 70 | 0x13FA | Overcurrent recovery attempts | 5 |
| 71 | 0x13FB | Charge current limiting, delay | 5 min |
| 72 | 0x13FC | Charge activation, delay | 1 min |
| 73 | 0x13FD | Charge activation, interval | 10 h |
| 74 | 0x13FE | Charge activation, count | 10 |
| 75 | 0x13FF | Recording interval in operation | 30 min |
| 76 | 0x1400 | Recording interval in standby | 240 min |
| 77 | 0x1401 | Standby shutdown delay | 48 h |
| 78 | 0x1402 | Remaining capacity alarm | 15 % |
| 79 | 0x1403 | Remaining capacity protection | 5 % |
| 80 | 0x1404 | **Intermittent charge capacity** (intermittent charge: resume below …) | 96 % |
| 81 | 0x1405 | Cycle cumulative capacity | 80 % |
| 82 | 0x1406 | Connection fault impedance | 10.0 mΩ |
| 83–86 | 0x1407–0x140A | Compensation point 1/2: position, impedance | 9 / 0.0; 13 / 0.0 |

### 7.3 Function switches (`0x20000028…2F` = BitGroup0…7)

**Switch bytes 1…5 (BitGroup1–5) are the enable masks for alarm events 2…6.** Proven for byte 1 ↔ event 2 *(confirmed, see below)*, byte 2 ↔ event 3 and byte 5 ↔ event 6 *(confirmed)*; analogously for 3, 4 *(probable)*. **BitGroup0 is not a mask**: only its bit 1 is used, as the enable for the sensor plausibility check (16.06.13 `0x68A0`); event 1 is not ANDed with it. The function `0x6894` is not a mask function; it checks sensor/connection faults (BitGroup0 bit 1, BitGroup5 bit 6).

**Event 2 / BitGroup1 in detail** (06.13 `0x6686`, 06.12 `0x64BA`, identical) *(confirmed)*:
1. The voltage evaluation (06.13 `0x647E` → `0x6400`) sets or clears the bits of event 2 (`0x20000031`) without delay: warning or protection when the measured value is ≥ the parameter, return below the recovery parameter.
2. Directly afterwards (main loop, before all consumers) comes `Event 2 &= BitGroup1`.
3. Then each warning is cleared if the associated protection is active (bit 1 → bit 0, bit 3 → bit 2, bit 5 → bit 4, bit 7 → bit 6).
4. Only after that do the charge lock (`0x6FFA`), SOC logic (`0x8F56`, `0x9044`), system flags and all protocols read the byte. Between evaluation and mask, only balancing (`0x653C`) reads, and it does not read event 2.

A cleared bit in BitGroup1 therefore switches off the quantity **completely**: no message, no MOSFET switching, no SOC reaction, no effect on CCL/alarm flags. The hysteresis state is lost in every cycle. A cleared bit therefore switches off the corresponding alarm or protection. The bit meaning corresponds to the alarm table in [Intra-pack protocol](protocols/intra-pack.md) (bit meanings from SEPLOS BMS Communication Protocol_v2.0.pdf, table 13).

| Byte | RAM | masks | Example value | Switched off (bit = 0) |
|---|---|---|---|---|
| BitGroup0 | 0x28 | **no mask**; only bit 1 = plausibility check of the temperature sensors | `FF` | – |
| BitGroup1 | 0x29 | Event 2 | `DF` | **Bit 5 = pack overvoltage protection: completely deactivated in the example configuration** *(confirmed)*; the cell OVP remains active |
| BitGroup2 | 0x2A | Event 3 | `FF` | – |
| BitGroup3 | 0x2B | Event 4 | `3F` | Bit 6 cell heater, bit 7 severe fault message/relay |
| BitGroup4 | 0x2C | Event 5 | `BF` | Bit 6 transient overcurrent lock |
| BitGroup5 | 0x2D | Event 6 | `9F` | Bit 5 reverse polarity (never set anyway), bit 6 output connection fault |
| BitGroup6 | 0x2E | Functions (see below) | `BF` | Bit 6 charging via current limiter from 10 A |
| BitGroup7 | 0x2F | Functions (see below) | `1F` | Bits 5–7 off |

Masks and order in the 1 s block (06.13) *(confirmed, 06.12 same structure)*: voltage `0x647E` → **BitGroup1 → event 2** (`0x6686`) → temperature `0x66C2` → sensor/connection `0x6894` → **BitGroup2 → event 3, BitGroup3 → event 4** (`0x6946`) → current `0x69BA`/`0x6CBC`/`0x6D62` → **BitGroup4 → event 5** (`0x6DB0`) → SOC `0x8E4C`/`0x8F56` → event 6 and **BitGroup5 → event 6** (end `0x9190`) → charge/discharge lock `0x6FFA`/`0x7184`. Each mask comes after the producer and before all consumers; a cleared bit switches off the message **and** the reaction. **BitGroup0 is not a mask:** only bit 1 is read (temperature sensor plausibility: sensor < −45 °C or ≥ 100 °C, or spread ≥ 20 K → event 1 bit 1, heater off); the other 7 bits have no effect.

Individual bits with their own function *(all confirmed, code addresses 06.13)*:
- `0x2B` (BitGroup3) bit 6: cell heater; heater output only if event 4 bit 6 **and** (charging or external voltage at the port, system status bit 1/2) (`0x7350`); also enables the **heater minimum charge current** (CCL ≥ packs × 10 A). Bit 7: if bit 6 is off and bit 7 is on, the heater/relay output (GPIO 11) switches on event 4 bit 7 "severe fault" *(use as an alarm contact probable)*.
- `0x2C` (BitGroup4) bit 4: transient detection (5 ms path `0x6AB8`), bit 5: short-circuit detection (comparator `0x6C44`, soft start check), bits 6/7: lock after parameter 70 transient or short-circuit events (`0x6CBC`).
- `0x2D` (BitGroup5) bit 1: intermittent recharge (`0x9190`); bit 6: output connection fault check via GPIO `0x50001000` pin 10 (`0x6904`).
- `0x2E` (BitGroup6): bit 0 balancing on; bit 1 balancing also at idle; bit 2 time limit parameter 64 h; bit 3 balancing lock at ambient temperature; **bit 4 automatic charge activation** (`0x6E30`) and at the same time **charge lock "cell < parameter 9" off** (`0x64D2`); **bit 5 manual charge activation** after power-on (`0x6DC4`); **bit 6** charging from 10 A via the current limiter (`0x6AB8`, `0x70F4`); **bit 7** current limiter after charge overcurrent warning for parameter 71 minutes (`0x69BA`, `0x70F4`).
- `0x2F` (BitGroup7): **bit 0** external on/off switch (GPIO `0x50001000` pin 0, high = off; `0x89E8`); **bit 1** standby shutdown after parameter 77 (`0x88D0`); bit 2 and bit 6 **without function** (no reader); bit 3 binary protocol (UART2); bit 4 binary format A; bit 5 ignore DIP address, pulse addressing and slave count adjustment in the master (§8.2d; hardware interpretation probable); **bit 7 CCL mode** (1 = parameter 50 − 10 A, 0 = parameter 50 / 2; 0 in the example configuration).

Meaning of each parameter and bit with the example configuration values: [Configuration parameters](configuration-parameters.md).

---

## 8. Protection and state logic (from the code)

### 8.1 "Charging forbidden" and charge MOSFET (06.13 `0x6FFA`, 06.05 `0x6516`)

The function sets or clears **alarm event 8 bit 6** ("charging forbidden"). From this follow the system status/on-off bit 1 and finally GPIO `0x50002000` bit 12, i.e. the charge MOSFET.

1. A counter counts up (max. 30) as long as the current is **< −10.00 A** (discharging). If the current is above that, it is set to 0.
2. From counter value 10, i.e. with sustained discharge above 10 A:
   - If **cell or pack overvoltage protection** is active (event 2 bit 1/5), these bits are **cleared**: discharging lifts the OVP protection. Charging remains forbidden in this cycle.
   - If no OVP protection is active, charging is allowed.
3. Otherwise charging is forbidden if one of these bits is set:
   - Event 2: cell OVP (bit 1), pack OVP (bit 5)
   - Event 3: charge overtemp. protection (bit 1), charge undertemp. protection (bit 3)
   - Event 4: ambient overtemp. protection (bit 1), undertemp. protection (bit 3), power stage overtemp. protection (bit 4)
   - Event 5: charge overcurrent protection (bit 1)
   - Event 6 with mask **`0x71`**: charger overvoltage (bit 0), cell too low to charge (bit 4), reverse polarity (bit 5), output connection fault (bit 6)
     - **SP80 only (06.05):** mask **`0x73`**, i.e. additionally **bit 1 "Intermittent recharge waiting"**
   - internal flag (`0x200000EA` in 06.05) bit 6
4. Afterwards: on-off bit 1 → GPIO pin of the charge MOSFET. If current limiting (bit 2) is off, GPIO bit 10 is cleared.

The bit masks are identical in all versions, **except SP80**. The **source of the temperature condition** changed in 16.06.11: up to 16.06.05 it tests the reported event 3 (`0x20000032`, masked by the current direction), from 16.06.11 the raw protection byte `0x200000BB` (not masked by direction). *(confirmed: 16.06.05 `0x6576`, 16.06.11 `0x6E84`, 16.06.13 `0x7050`)*

Additionally (06.12/06.13): if event 7 bit 6 or 7 is set (current limiting, see §8.1b) and the pack is charging, the **charge MOSFET is switched off and the current limiter switched on**. The standby shutdown (§8.1c) also sets "charging forbidden" 60 s before shutting down. *(confirmed)*

### 8.1a Discharge lock and discharge MOSFET (06.13 `0x7184`, 06.12 `0x6FB8`) *(confirmed)*

The discharge MOSFET (on-off bit 0, GPIO 13) is **off** as long as any of the following applies:
- Event 2 bit 3/7: cell or pack undervoltage protection
- Raw cell temperature state `0x200000BB` & 0xA0: discharge over/undertemperature protection
- Event 4 & 0x1A: ambient over/undertemperature protection, power stage protection
- Event 5 bits 3–7: discharge overcurrent protection, short-term overcurrent protection, short-circuit protection, both locks
- Event 6 & 0x68: **SOC protection (parameter 79)**, reverse polarity (never set), output connection fault
- Empty flag (`0x200000F5` bit 0, set when the SOC jumps to 0 % due to UVP)
- System status bit 5 "off"

**Charging ≥ 3 A (system status bit 7) clears the undervoltage protection** (event 2 bit 3/7), mirroring "discharging > 10 A lifts OVP". At power-on, precharge runs first (§8.1b).

### 8.1b Current limiter, soft start, overcurrent reconnection *(confirmed, 06.12 identical)*

- **Current limiter** (on-off bit 2, GPIO 10): it replaces the charge MOSFET during charging if event 7 bit 6 or 7 is set and the pack is not discharging.
  - **Event 7 bit 7** (BitGroup6 bit 7, `0x69BA`): charge overcurrent warning (I ≥ P50) present for **P66/2 seconds**. Ends after **P71 minutes** or 5 s without charging (`0x70F4`).
  - **Event 7 bit 6** (BitGroup6 bit 6, 5 ms path `0x6AB8`): charge current ≥ **10.00 A** → immediately onto the limiter. Ends after 5 s without charging.
  - GPIO 10 is only released once the feedback input GPIO 14 has been high for 500 ms (until then event 6 bit 7).
  - The firmware does not define the limiting current itself; it is set by the hardware *(probable)*.
- **Soft start/precharge** (`0x725A`, 5 ms path): when the discharge MOSFET is switched on, the precharge path (GPIO 15, on-off bit 4) runs first for at most **parameter 57 ms**. If the output voltage stops rising (checked every 100 ms), precharge ends earlier. If the output voltage is then below half of the target value, the firmware reports a **short circuit** (event 5 bit 5, with BitGroup4 bit 5); otherwise GPIO 13 switches (on-off bit 5 for 100 ms).
- **Overcurrent reconnection** (`0x6D62`): charge/discharge overcurrent, short-term and short-circuit protection (event 5 & 0x3A) are cleared automatically after **parameter 69 seconds**. Charging clears event 5 bits 3–7, discharging clears bit 1.
- **Lock** (`0x6CBC`, only with BitGroup4 bit 6/7): after **parameter 70** short-term or short-circuit events (the counter resets after 301 s without an event), event 5 bit 6 or 7 is set. The lock is excluded from automatic reconnection and is only cleared when the pack detects charging. P70 does **not** affect the normal charge/discharge overcurrent.
- **Short-term overcurrent** (BitGroup4 bit 4, 5 ms path): current < P56 for longer than P68 ms → GPIO 13 off immediately, event 5 bit 4.

### 8.1c Charge activation and standby shutdown *(code confirmed, 06.12 identical)*

- **Charge activation** (parameters 72–74, `0x6DC4`/`0x6E30`/`0x6EC2`):
  - automatic (BitGroup6 bit 4, event 7 bit 4): as long as UVP, the empty flag or SOC protection persists, every **P73 hours**, at most **P74** times
  - manual (BitGroup6 bit 5, event 7 bit 5): once after power-on, if UVP, the empty flag or SOC protection persists and the port voltage is below a threshold
  - Window: for **P72 minutes**, the latch of cell/pack UVP, empty flag and SOC protection is cleared every second, so the MOSFETs can close. Aborted if for 5 s the following do not hold: lowest cell > P9, current > −3 A, both MOSFET paths on. Charging ≥ 3 A for > 5 s or lowest cell > P7 resets the attempts.
  - Purpose *(probable)*: a charger should be able to detect and charge a switched-off battery. Since the voltage evaluation immediately sets UVP again as long as a cell is ≤ P6, it is effective in practice between P6 and P7.
- **Standby shutdown** (parameter 77, BitGroup7 bit 1, `0x88D0`): a seconds counter runs in standby without external voltage at the port (system status bit 4 and not bit 2); 5 s outside this condition reset it. After **P77 hours**, with highest cell < P5 and no charge activation in progress: 60 s "charging forbidden", then **"off"**. Afterwards (`0x8A24`): if after 30 s there is a voltage > P15 at the port (charger), it is aborted; otherwise the firmware saves its state to internal flash (block 6, `0x5564` → `0x4748`) and sets GPIO `0x50001000` bit 1 to 0. That this switches off the supply (self-latching) is *probable*. Button or port voltage abort it.

### 8.2 Temperature alarms and heater (06.13 `0x66C2`, 06.12 `0x64F6`, 06.11 `0x64FA`)

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

### 8.2a Passive balancing

Full description (enable conditions, cell selection, neighbor lock, reasons why it is rarely active): [Seplos ASCII protocol §7](protocols/seplos-ascii.md) (section 7, passive balancing). In short: cell ≥ parameter 8 and ≥ parameter 63 above the lowest cell; start only with spread > parameter 62; not during discharging. In 06.11, the lock threshold for the lowest cell was lowered from 3.0 V to 2.0 V; otherwise the logic has been unchanged since 04.06. *(confirmed)*

### 8.2b Energy and cycle counters

- **Energy counter** (`0x9044`, timer ISR with period `SystemCoreClock` = 1 s): every second, with system status "charging", `I(0.01 A) × U_Pack(0.01 V) / 10000` (= watts) is added to an accumulator; with "discharging", the absolute value. From 360,000 W·s (100 Wh), `cc8+0x58` (charged) or `cc8+0x5C` (discharged) is incremented by 1. **Unit 0.1 kWh.** *(confirmed)*
  - Output: ASCII 0x42 "Reserved 3/4" (u16, fixed 6500 from 65,000), Victron CAN 0x378 (u32).
  - Reset: ASCII 0x45 type 5 ("clear history").
  - Practice (the example system's packs, Oct. 2026): master 1,103.3 kWh charged / 984.3 kWh discharged (≈ 89 % energy efficiency).
- **Cycle counter** (`0x9250`): during discharging, the SOC decrease since the start of discharge is summed up. When the sum reaches **parameter 81 "Cycle cumulative capacity"** (e.g. 80 %), `cc8+0x60` is incremented by 1 and saved. A cycle is therefore a cumulative SOC decrease of e.g. 80 %, not a full charge/discharge. *(confirmed)*

### 8.2e What is stored persistently *(confirmed, 06.12 = 06.13)*

Remaining and full capacity, energy counters (`cc8+0x58/0x5C`) and cycles are stored in **flash block 6** (`0x5564`, loaded at startup by `0x55CE`; if the block is invalid, remaining/full capacity come from P59/P58, energy and cycles start at 0). There is **no time interval**. Block 6 is written:
1. in standby, as soon as the SOC deviates by more than 5.0 % from the last saved value (`0x903E`)
2. on every new cycle
3. after learning the full capacity
4. before self-shutdown ("off" with shutdown)
5. when writing the parameter block (ASCII 0xA1) and via binary command
6. on 0x45 type 5 (clear history and counters)

ASCII 0x49 (set P58/P59) only changes the RAM; it is saved at the next of these occasions. **On power loss**, whatever was counted since the last save is lost. During an ongoing charge or discharge phase, nothing is saved except on a new cycle: after a power loss in the middle of charging, the energy counters and SOC are at the state before this phase (the SOC is then corrected again via the voltage rules).

### 8.2c System status: all bits from the code

Byte `0x200000AC`, checked in 06.12 and 06.13 (logic identical). All current thresholds refer to the reported pack current in 0.01 A (06.12 `0x20000CC8`, 06.13 `0x20000CD0`), + = charging. *(all confirmed)*

| Bit | Meaning | set | cleared | Code (06.12 / 06.13) |
|---|---|---|---|---|
| 0 | **Discharging** | I ≤ −0.50 A; with ambient temperature alarm/protection (event 4 bits 0–3) only at ≤ −1.00 A | I > −0.40 A or > −0.80 A; also on "off" | `0x84A0` / `0x870C` |
| 1 | **Charging** | I ≥ +0.60 A; with event 4 bits 0–3 only at ≥ +1.20 A | I < +0.50 A or < +1.00 A | same |
| 2 | **"Float"** = charger/external voltage detected at the port | immediately with bit 1 (charging) or port voltage ≥ pack voltage + 1.00 V; otherwise after 5 s if at least one MOSFET is off and port ≥ pack − 0.20 V (on-off bit 6). Difference port − pack: 06.12 `0x20000D0E`, 06.13 `0x20000D16` (`cc8+0x4E`, 0.01 V) | after 5 s without this condition | `0x856E` / `0x87DA` |
| 3 | – | **never** (no write access sets it) | – | – |
| 4 | **Standby** | neither bit 0 nor bit 1 | bit 0 or 1 set; on "off" | `0x84A0` / `0x870C` |
| 5 | **Off (shutdown)** | button > 3 s, external switch (BitGroup7 bit 0), standby shutdown (parameter 77, BitGroup7 bit 1) or control command 0x45 type 4 | charging detected (bit 1), button, switch low, control command type 4 with value 0x10 | `0x870C`, `0x87B8`, `0x0A3C` / `0x8978`, `0x8A24`, `0x0A3C` |
| 6 | **Discharge current ≥ 3 A** | I ≤ −3.01 A | I > −2.81 A | `0x84A0` / `0x870C` |
| 7 | **Charge current ≥ 3 A** | I ≥ +3.01 A | I < +2.81 A | same |

- Bit 7 is evaluated by the SOC calibration: the voltage rules for 98/100 % only take effect after there has been no charging with ≥ 3 A for 30 s (see [States and triggers §2](states-and-triggers.md), SOC calibration). No reader was found for bit 6. Both are only visible in the intra-pack response 0x5A. In 0x44 the firmware only reports `& 0x33` (bits 0, 1, 4, 5).
- Bits 0/1 are the basis for everything that requires "charging"/"discharging", e.g. the energy counters (§8.2b) and the charge/discharge temperature limits.
- The thresholds here apply to the individual pack. The master decides for the whole system separately with its own dead band (see [Modbus RTU §2](protocols/modbus-rtu.md), total current: discharging ≤ −0.8 A, charging ≥ +1.0 A).
- Confirmed with 24 real 0x5A captures (see [Intra-pack protocol](protocols/intra-pack.md), real captures/test data).

### 8.2d Alarm event 8 bit 7 and automatic address assignment

Bit 7 of alarm event 8 exists only in the intra-pack response 0x5A (06.13 `0x1348`). It is **1 if bit 3 of `0x200000F6` is cleared** (06.12: `0x200000EF`). *(confirmed)*

- **Source of bit 3** (06.13 `0x93D0`): debounced input **GPIO `0x50002000` pin 9**. Pin low for 10 cycles → bit 3 = 1, pin high for 200 cycles → bit 3 = 0. Event 8 bit 7 = 1 therefore means **"pin 9 is high"**. *(confirmed)*
- **Who else uses pin 9** (06.13 `0x944C`, only if function switch `0x2F` bit 5 is set): *(code confirmed)*
  - `0x9334` measures the length of a low pulse on **pin 8** and converts it into a number (÷ 10, rounded; no pulse or too long → 21).
  - This number is taken over as the **RS485 address** (`0x20000027`) instead of the DIP address.
  - If **pin 9** goes low (and no pulse is running yet), the pack outputs a low pulse of length (own address + 1) × 10 on **pin 7** (`0x9410`).
- **Interpretation** *(probable)*: a **pulse chain for automatic address assignment**. Pin 8 = input from the predecessor, pin 7 = output to the successor, pin 9 = request from the successor. Each pack reads its address from the pulse length and passes on address + 1. Which socket wires these are is open; one candidate is pins 4/5 of the RS485 sockets, which the Seplos specification labels "Internal communication (NC)".
- **Practical consequence:** with normal DIP addressing (`0x2F` bit 5 off), pin 9 is high at rest, which is why event 8 in 0x5A almost always shows `0x80`. This is not a fault. It is set in all 24 captures of a 12-pack system.
- Function switch `0x2F` bit 5 thus gets a second meaning: besides the automatic adjustment of the slave count in the master, it also enables this pulse addressing.

### 8.3 Miscellaneous

- With **≤ 8 cells** (parameter 65), cell temperatures 3 and 4 take the value of sensor 2. *(confirmed, 06.13 `0x2162`)*
- **SOH** is not calculated: CID2 0x42 reports a fixed 1000 ‰. *(confirmed)*
- **Current in CID2 0x42:** if neither charging nor discharging is active (system status bit 0/1 = 0), the current is reported as **0**. The current with 1 mA resolution is then in "Reserved 2", and the reference/offset channel of the current measurement in "Reserved 1" (see [Protocol extensions §1.1](protocols/undocumented-commands.md)). *(confirmed)*

---

## 9. Update procedure (from `Seplos update doc.docx` in the 06.11 ZIP)

Summary of the enclosed guide (English, without changelog):

- **Reason according to Seplos:** "BatteryMonitor cannot connect" or "with two parallel packs, only one is online at the inverter". The cause is said to be a "communication interference in the previous firmware". The remedy is said to be the update to "16.6". This is the **only official statement about a change**. What is meant is apparently the firmware line **16.06** (as opposed to 16.04), not specifically 06.11. A comparison 06.05 → 06.11 shows: the master polling functions (request, evaluation, snapshot, 0x5A response) are identical apart from shifted addresses. *(confirmed)* The rework 04.06 → 06.03, by contrast, affects large parts of the communication code (see [CHANGELOG](firmware-changelog.md)).
- **Procedure:**
  1. Disconnect the parallel connection, switch off the pack.
  2. Set DIP switch 1 to ON, then back to OFF (described this way).
  3. Switch on the pack. This must happen before the update, otherwise reading the pack capacity fails.
  4. In the "Firmware Update" tool, connect via a USB-RS485 adapter at **19200 baud**.
  5. Select the `.ehex`, "Download". In case of errors, press the reset button or repeat.
- The 19200 baud matches the header field `RS485Y19200…`.

---

## 10. Determining the patch version of a running BMS

**It cannot be read out directly.** The image contains only `0x10 0x06` (16.06), or `0x10 0x04` for 16.04. This value is returned by ASCII 0x51 (INFO bytes 10/11), Modbus `0x0001` block register 0x1C, Pylontech 0x51/0x60 and CAN 0x35F/0x320. *(confirmed)*

**It can be derived partially**, namely via functions that only exist from a certain version on. All statements come from the code; this has not been tested on a real device.

| Test | Interface | Result → version | Intervention |
|---|---|---|---|
| ASCII **0x51**, bytes 10/11 | Pack bus (each pack) | `10 04` → 16.04.x; `10 06` → 16.06.x | none |
| ASCII **0xAA** (without INFO) to the pack | Pack bus (each pack) | immediate RTN 04 → **≤ 06.12**; no response → **06.13** | minor: with 06.13 and an active binary port, a tunnel request is sent to the connected device |
| Pylontech **0x60** to ADR 0x12 | Inverter RS485, master only | RTN 04 → **≤ 06.03**; response with "SH-EnergyTCH" → **≥ 06.04** | none |
| Pylontech **0x4F** to ADR **0x02** | Inverter RS485, master only | no response → **≤ 06.11**; response → **≥ 06.12** | none |
| Modbus FC03 `0x1000` × 21 | Inverter RS485, master only | Exception 02 → **≤ 06.03**; data → **≥ 06.04** | none |
| Modbus FC04 `0x0000` × 21 | same | Exception → **≤ 06.05**; data → **≥ 06.11** | none |
| Modbus FC03 `0x9000` × 26 or `0x001F` × 9 | same | data → **06.13**; exception 03/02 → **≤ 06.12** | none |
| SP80 vs. 06.04 | Pack bus 0x44 | only detectable in the state "Intermittent recharge waiting" (event 6 bit 1): charge MOSFET (on-off bit 1) off → **SP80**, on → 06.04 | none, but the state must occur |

Result:
- **Via the pack bus only** (as in the MQTT add-on), 16.04, 16.06.03–06.12 and 06.13 can be distinguished.
- **With access to the master's inverter RS485**, all versions can be separated: 06.03 / 06.04–06.05 / 06.11 / 06.12 / 06.13.
- 06.04 and 06.05 (SP80) can only be distinguished by their behavior.
- Between 06.03 and 06.12, the pack bus commands are identical in content. The only difference (0xA3/0xA5 since 06.11) would only be measurable by writing a serial number string and is therefore not recommended.

## 11. Methodology and limitations

- The tools and commands are described in [tools/README.md](../tools/README.md).
- The image contains no symbols. All function names are derived from data flow, constants and the protocol PDFs.
- **Not** contained in the image: bootloader, a table of default parameters (defaults are set in the code or kept in the parameter block in internal flash), texts of the BatteryMonitor tool.
- RAM addresses apply to 06.13. Older versions are partially shifted (see section 6).
