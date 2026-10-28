# Seplos BMS 2.0/10E/V16 (EMU1101): Firmware Analysis

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The EMU1101 application uses a Cortex-M0 Thumb image packaged in a Seplos-specific `.ehex` container. Original images are under [vendor firmware](../../vendor/firmware/); [protocol references](../protocols/README.md) describe the external interfaces.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2, inverter protocols and available monitoring/service paths. Availability depends on the **active requester on each bus**, not the number of sockets or gateways.

Confidence: **confirmed** = read directly from the code/bytes · **probable** = inferred from data flow/context · **assumption** = plausible, not proven. Unless stated otherwise, addresses refer to **V16.06.13**.

---

## 1. Files examined

| File (`../../vendor/firmware/`) | Lines | SHA-256 (prefix) | Image size | Stack top | Reset vector | Image SHA-256 (prefix) |
|---|---|---|---|---|---|---|
| `CAN1101[V16.04.06_PN01_220924_9600].ehex` | 3024 | `2b00410571fcb9da` | 48,096 B (0xBBE0) | 0x200017D8 | 0xB629 | `fa38fbd4dba02eb4` |
| `CAN1101[V16.06.03_PN01_230412].ehex` | 3017 | `246e1eca5637bcc1` | 47,980 B (0xBB6C) | 0x20001A90 | 0xB5BD | `689d3819eb9f73e1` |
| `CAN1101[V16.06.04_PN01_230613].ehex` | 3137 | `d69f27c1650e31cf` | 49,900 B (0xC2EC) | 0x20001A90 | 0xBD29 | `390299c85aae21b1` |
| `CAN1101[V16.06.05_PN01_230916_SP80].ehex` | 3137 | `c8f0560b7d32df30` | 49,900 B (0xC2EC) | 0x20001A90 | 0xBD29 | `a2abc282abf9d344` |
| `CAN1101[V16.06.11_PN01_240713].ehex` | 3297 | `2dae963fd5aa11aa` | 52,452 B (0xCCE4) | 0x20001A90 | 0xC70D | `b686b69e69878390` |
| `CAN1101[V16.06.12_PN01_241209].ehex` | 3298 | `46d25a5f565ae014` | 52,472 B (0xCCF8) | 0x20001A90 | 0xC721 | `f487ac4bc3b89c5f` |
| `CAN1101[V16.06.13_PN01_250607].ehex` | 3337 | `0ea75c9834cf1978` | 53,092 B (0xCF64) | 0x20001A98 | 0xC985 | `5c36a7e08fb881b3` |

Contents of the ZIP files in the original firmware distribution: each contains exactly the `.ehex`, some with macOS metadata (`__MACOSX/`). **Exception:** the 06.11 ZIP additionally contains `Seplos update doc.docx`, an update guide (section 9). No changelog is included in the seven retained packages.

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

- Every record has the form `:10 0000 00 <16 bytes> AA`: length 16, address always 0000, type 00, **checksum always `AA`**. The checksum is therefore deliberately invalid; *presumably* this is how the update tool recognizes the header (the bootloader implementation is unavailable).
- The payloads of the 16 records together make up 256 bytes.

| Bytes | Content (identical in all 7 versions) | Meaning |
|---|---|---|
| 0–15 | `SWM181RCT6_64_M0` | MCU: **Synwit SWM181 RCT6**, Cortex-**M0**; "64" presumably flash variant/clock specification |
| 16–31 | `EMU1101_10D_HW16` | Device identifier **EMU1101**, header text "10D" (meaning unconfirmed), **hardware 16** |
| 32–47 | `RS485Y19200N9600` | RS485 header text, identical in all seven images. It does not establish operating/bootloader rates: UART0 is 9600 in 04.06, 19200 from the next available build 06.03; UART1 is always 9600. The 04.06-9600 bootloader rate remains unverified |
| 48–255 | `0x55` × 208 | Padding bytes |

**Header identifier and board model:** All seven OEM headers literally contain
`EMU1101_10D_HW16`. This does not establish a hardware/model variant called 10D.
The firmware's default device name is `EMU110110E`, and observed PCB labels say
10E. Treat 10D as an internal header identifier of unconfirmed meaning; patches
preserve the header unchanged.

The retained EHEX payloads contain plain Thumb code and no identified whole-image cryptographic signature or encryption. Per-record Intel HEX checksums are present. The unavailable bootloader's compatibility checks and other content validation are not established by examining the application image or PC updater alone.

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

- **Link address 0x00000000.** The application therefore sits at the start of flash. How the update over RS485 at 19200 baud works (section 9) cannot be determined from the image: either the SWM181 has an ISP loader in ROM, or a bootloader resides in another flash region *(location open)*. It is reached by an application reset (0x45 type 6); protocol and historical measurements in the [bootloader reference](../protocols/bootloader-update-protocol.md).
- **RAM:** The stack top is at `0x20001A98` (06.13), and at `0x200017D8` in 04.06. The RAM is therefore at least 6.8 KB, and the used region has grown across versions.
- **Compiler:** Keil MDK / ARMCC. Evidence: `__main` at 0xC0, `__ARM_common_switch8` jump tables (06.13 at `0xCBE4`), division via `__aeabi_uidiv`/`idiv` (06.13 `0xC9DC`/`0xCA08`), region table. *(confirmed)*
- **Peripherals:** The base addresses `0x4000_0000`, `0x4100_0000`, `0x4300_0000`, `0x4500_0000`, `0x5000_0000…0x5004_0000` and SCB/NVIC `0xE000_E000` are used. The same peripheral address set is used in all seven images; individual modes, pins and logic still require version-specific comparison. *(confirmed)*
  - GPIO `0x5000_2000` *(confirmed, from all writers)*: outputs bit 10 current limiter, bit 11 heater or relay (low = on), bit 12 **charge MOSFET**, bit 13 **discharge MOSFET**, bit 15 precharge path (soft start); inputs bit 1 button (low = pressed), bits 7/8/9 [pulse addressing](../hardware/internal-address-chain.md#confirmed-firmware-mechanism), bit 14 current limiter stage feedback.
  - GPIO `0x5000_1000`: input bit 0 external on/off switch (BitGroup7 bit 0), output bit 1 supply self-latching *(probable)*, input bit 10 output connection fault (BitGroup5 bit 6). *(confirmed, except the interpretation of bit 1)*
  - **Timing:** Timer 0 every **5 ms** (measurement, fast overcurrent/short-circuit path, soft start), timer 1 every **1 s** (coulomb/energy counter). The measurement sequencer counts 200 × 5 ms and then starts the main loop, which therefore runs **nominally once per second** (06.13 `0x5FC4`, `0x1ABA`). All "cycles" in the protection logic are seconds. *(confirmed)*

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

In 04.06, 8 more bytes follow the version (`4F 4B 6A 6B 00 48 08 48`); the CAN names start at +0x0A there. *(confirmed)*
| +0x8E | `SH-EnergyTCH Co.,Ltd` | Manufacturer name, **from 06.04** (20 characters) |
| after that | `05 07 06 04 00 03 01 02` | **Channel order of the 8-way analog multiplexer**: in steps 16–23 (after the 16 cell channels), the measurement sequencer `0x1ABA` selects these channels via GPIO `0x50004000` bits 4–6. Which sensor is connected to which channel is determined by the hardware. *(confirmed)* |
| after that | `8B7C F979 A579 …` | descending uint16 table = **NTC curve** (ADC → temperature), identical in all versions |

Further strings:
- `EMU110110E` (10 characters): default device name. It is copied to RAM `0x20000042` and output in CID2 0x47/0x51 and Modbus.
- `EMU110110S-XXXX-20220120-00001` (three times): default/placeholder serial number (barcode), identical in all versions.
- New in 06.13 is a short byte table (`0C 36 33 42 45 48 4B 4F 73 …`, from `0x1182`). This is not a data table but the **jump table of the ASCII dispatcher** for CID2 0xA0–0xAB (behind `bl 0xCBE4` at `0x117E`, Keil `switch8`). *(confirmed)*

---

## 5. Firmware architecture (06.13)

### 5.1 Main loop and communication modes

- The RS485 address comes from the DIP switch (`0x20000027`). The DIP switch is read **analog**: switches 1–4 and 5–8 are each connected to a resistor network, and the firmware quantizes the two ADC values to 0–15 via the table `0xCE16` (`0x2112`). **Switches 1–4 = address** (0 = master, slaves 1–15), **switches 5–8 = number of slaves** (master only; at address ≠ 0 the number becomes 0). This allows at most 16 packs via DIP; the upper limit of 21 in the code applies only to automatic detection (BitGroup7 bit 5). *(confirmed; confirmed by the Seplos specification, chapter 4.4)*
- **Address 0 with at least one slave** → **master mode:** the pack polls the slaves with CID2 0x5A (see [Intra-pack protocol](../protocols/intra-pack.md)). Otherwise, as a slave, it processes ASCII commands (dispatcher `0x1132`).
- On the inverter-side RS485 interface (shared RX buffer `0x20000DFE`), **two protocols run in parallel**:
  - **Pylontech ASCII** (frames with `~`, dispatcher `0x2AF2`: CID2 0x42, 0x44, 0x4F, 0x51, 0x60, 0x61, 0x62, 0x63), see [Pylontech RS485](../protocols/pylontech-rs485.md)
  - **Modbus RTU** (dispatcher `0x45AC`, only active if `0x200000F7` bit 7), see [Modbus RTU](../protocols/modbus-rtu.md)
- In addition there is **CAN** (protocol according to `0x20000024`), see [CAN protocols](../protocols/can.md).
- There is also a **binary protocol** (`0x55 … 0xAA`, dispatcher `0x8288`, active if function switch `0x2000002f` bit 3). See the [UART2 display/Bluetooth protocol](../protocols/binary-display-protocol.md).

### 5.1a Interfaces and peripherals *(confirmed unless stated otherwise)*

| Interface | Peripheral | Protocols | Remark |
|---|---|---|---|
| RS485 pack bus / PC, **sockets RS485-1/RS485-2** | **UART0** `0x50010000`, direction pin GPIO `0x50002000` bit 6, **19200 baud** (04.06: 9600) | Seplos ASCII with full command set (0x42…0xAB), intra-pack 0x5A | Master polls slaves; BatteryMonitor; firmware update (19200 on the lab board; 04.06-9600 bootloader rate unverified) |
| RS485 inverter, **RS485 pair of the CAN socket** | **UART1** `0x50011000`, **9600 baud** | **Modbus RTU** (read-only) + **Pylontech ASCII** (0x42/0x44/0x4F/0x51/0x60–0x63) on the same buffer | 0x42/0x44/0x51: each pack under its DIP address (bus operation of all packs incl. master possible); Modbus and 0x60–0x63: master only |
| Local display/Bluetooth (electrical levels unverified) | **UART2** `0x50012000`, 9600 8N1, without direction control | **Binary protocol** `0x55…0xAA`, CRC-16/XMODEM | active with function switch `0x2F` bit 3; device interpretation: local LCD/Bluetooth; WLAN attachment not established |
| CAN | SJA1000-like `0x50020000`, pins port `0x50002000` pin 2/3 | 7 inverter protocols; **transmit-only application protocol**; no useful incoming control dispatcher identified | 500 kbit/s, MUST 100 kbit/s; only the master transmits |
| I²C | Hardware I²C controller `0x50018000`: device **0xA2 = RTC** (time; register 2 bit 7 → event 8 bit 5), device **0xA4 = history EEPROM** (500 × 128 bytes, header 0xFF00) | – | *(confirmed)* |
| Flash records | Settings and counters in **internal flash** via IAP (`0x4748` write, `0x47A8` read), address 0x25000 + block·0x1000, each with a mirror copy 0x1000 behind it and CRC-16/Modbus. Block 0 parameters, 2 calibration, 4 strings/device data/CAN protocol, 6 capacities/energy/cycles ([persistence reference](soc-capacity-and-persistence.md#4-what-returns-after-loss-of-power)). The byte 0xA0 is the identifier of these records | – | *(confirmed)* |
| RTC | (driver `0x58E2`/`0x5882`) | ASCII 0x4D/0x4E | Error → event 8 bit 1 |
| Watchdog | `0x50009000` | ASCII 0x45 type 6 = restart | |

**Manufacturer port specifications:** The48150-10E manual p.27 explicitly
specifies9600-baud RM485 in theCAN socket:1/8=B,2/7=A,4=CAN-H,5=CAN-L,3/6=GND.
The48200 manual instead labels thoseRS485 wiresNC; its image onPDF p.38 shows
Bluetooth LCD004 besideLCD003. This establishes the accessories,without proving
their exact wire format or its binding to theUART2 dispatcher. Other hardware
specifications and source discrepancies are kept separate from code findings in
[the manual comparison](../hardware/hardware-specifications.md).

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
| `0x2112` | Take over temperatures from ADC/NTC (with ≤ 8 cells, sensors 3/4 = sensor 2) **and** decode the DIP switches → address `0x20000027` (`0x219C`), slave count `0x20000026` (`0x21BE`); runs every second | confirmed |
| `0x2600` | Pylontech RS485 CID2 0x60 system basic info (name, "SH-EnergyTCH Co.,Ltd", version, up to 4 serial numbers) | confirmed |
| `0x26A8` / `0x278C` / `0x2882` | Pylontech RS485 CID2 0x61 / 0x62 / 0x63 | confirmed (mapping) |
| `0x28F0` | Inverter port: decode frame | confirmed |
| `0x2A40` | Pylontech RS485: build response header `~20 ADR 46 RTN LEN` | confirmed |
| `0x2AF2` | Pylontech RS485 dispatcher (inverter port) | confirmed |
| `0x25B2` | Inverter port: start transmission (with direction pin) | confirmed |
| `0x2B80…0x432A` | Modbus register handlers (see [Modbus RTU](../protocols/modbus-rtu.md)) | confirmed |
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
| `0x496A` | **Load the parameter block from flash into the live tables** (flash block 0 via `0x47A8` → `0x20001300` 60×u16, `0x200013F0` 27 B, `0x20000042` 10 B switches); defaults on an invalid record. Called in the deferred 1 s init `0x6032` | confirmed (role) |
| `0x5260` | Load a flash record (calibration/capacities, `0x47A8`), called at `0x6036` | confirmed (role) |
| `0x1914` | **Measurement acquisition** from ADC/peripheral (`0x41000040`) into the measurement buffers `0x200007B8`/`0x20000B58`; called in the fast measurement cycle `0x6054` | confirmed (role) |
| `0x5DB2` | History trigger: record on a change of system status/events 1–7, otherwise interval P75/P76 (writer `0x5998`), called at `0x621E` in the 1-s block | certain |
| `0x9E0A` | CAN alarm frame from the alarm OR `0x2000161E` into the CAN buffer `0x20001680` | confirmed (role) |
| `0x7F82` | Persist capacity/parameters (block-6 save `0x5564`, plausibility `0x4C3C`) | probable |
| `0x62DC` | LED driving (GPIO, calls the driver `0xB3A8` repeatedly), called at `0x60F4` | probable |
| `0x01AA` / `0x24A8` / `0x5FF0` | ISRs: UART0 RX / UART1 RX / 5 ms timer | confirmed |
| `0xB900`–`0xCF64` (selection) | Keil/compiler runtime (division, memcpy/memset, drivers), not documented individually | confirmed (role) |

---

## 6. RAM usage (06.13)

In 06.13, many variables above approx. `0x200000C0` are shifted by **+7 or +8 bytes** compared to 06.12 (e.g. pin 9 flag `0x200000EF` → `0x200000F6`: +7). The low addresses have been stable since 06.03.

| Address | Type | Content | Confidence |
|---|---|---|---|
| `0x20000000` | u8 | Master's pack bus: bit 0 request sent/response expected, bit 1 request finished (timeout 150 ms), bit 2 polling round over all slaves complete (then aggregation `0x99BA`, reset once per second; at address 0 without slaves, `0x12E2` sets it every second, aggregate then only from its own pack), bit 3 pack communication error (30 consecutive rounds with fewer packs online than configured), bits 4/5 broadcast 0x45 type 4 off/on pending | confirmed |
| `0x20000005` | u8 | **Alarm event 8** (bit 0 EEPROM, 1 RTC, 2–4 calibration, **bit 6 = internal request "charging forbidden"**) | confirmed |
| `0x20000006/07` | u8 | Balancing status cells 1–8 / 9–16 | confirmed |
| `0x20000024` | u8 | **active CAN protocol** 1…7 (1 = PNG_DYE_Luxp_TBB/Pylontech) | confirmed |
| `0x20000025` | u8 | `0x55` = "save settings" | confirmed |
| `0x20000026` | u8 | Number of slave packs (master), max. 21 | confirmed |
| `0x20000027` | u8 | RS485/DIP address | confirmed |
| `0x20000028…2F` | u8 ×8 | **Function switches** (BatteryMonitor "BitGroup0…7"), see [function-switch reference](configuration-parameters.md#5-function-switches-bitgroup07) | confirmed |
| `0x20000030…35` | u8 ×6 | **Alarm events 1…6** | confirmed |
| `0x20000036` | u8 | **Alarm event 7** | confirmed |
| `0x20000042` | char[10] | Device name (`EMU110110E`) | confirmed |
| `0x2000004C` | char[30] | String 1, **battery serial number** (BatteryMonitor "Battery_SN"; ASCII 0xA2/0xA3; in Modbus FC04 0x0000 and Pylontech 0x60) | confirmed |
| `0x2000006A` | char[30] | String 2, **BMS / board serial number** (BatteryMonitor "BMS_SN"; only ASCII 0xA4/0xA5 on UART0). Both persist in flash block 4 (`0x29000`) | confirmed |
| `0x200000C8` | u16 | Remaining time of forced heating (ASCII 0x45 type 3, start value 3600) | confirmed |
| `0x200000E9` | u8 | (06.13) shadow of the system status for the off/on edge (binary 0xA2/0xA3) | confirmed |
| `0x200000F8` | u8 | Bit 2 = heater minimum charge current active (CCL ≥ packs × 10 A) | confirmed |
| `0x200012F6/F8/FA` | u16 | History: count / start / read pointer | confirmed |
| `0x20001634` / `0x20001627` / `0x2000161E` | struct | Master aggregates: extreme values / pack numbers of the extreme values / OR of all alarm events | confirmed |
| `0x200015E0` / `0x200015EC` | u32 | Coulomb counter: maximum (full capacity·3600) / current value (remaining capacity·3600) | confirmed |
| `0x200000AC` | u8 | **System status** (bit 0 discharging, 1 charging, 2 "Float" = internal "charge path active" flag, not a float charging mode, 3 never set, 4 standby, 5 off, 6 discharge current ≥ 3 A, 7 charge current ≥ 3.01 A (clears below 2.81 A); see [system status](states-and-triggers.md#charging--discharging--standby--off-system-status)) | confirmed |
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
| `0x20001300` | u16 ×60 | **Parameters 0…59**, see the [parameter reference](configuration-parameters.md#3-parameters-059) (06.13; up to 06.12 `0x200012F8`) | confirmed |
| `0x200013F0` | u8 ×27 | **Parameters 60…86**, see the [parameter reference](configuration-parameters.md#4-parameters-6086) (06.13; up to 06.12 `0x200013E8`) | confirmed |
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

ASCII `47` returns 60 × u16 parameters, 27 × u8 parameters, eight function-switch bytes and a 10-byte device name. In 16.06.13 the numeric blocks begin at `0x20001300` and `0x200013F0`; up to 16.06.12 they begin at `0x200012F8` and `0x200013E8`. BitGroup0–7 remain at `0x20000028…2F`.

[Configuration parameters and function switches](configuration-parameters.md) covers each field, raw units, RAM addresses, example values, event masks and evaluation order. Its [storage and XML section](configuration-parameters.md#1-storage-wire-layout-and-xml-exports) distinguishes positional `47`/`A1` wire decoding from BatteryMonitor XML import by numeric field name.

---

## 8. Protection and state logic

The one-second control block evaluates measurements and event masks before determining charge/discharge permission and system limits. Fast overcurrent, short-circuit and precharge paths run at 5 ms.

| Subject | Complete reference |
|---|---|
| Parameter units, addresses, event masks and function switches | [Configuration parameters](configuration-parameters.md) |
| Charge/discharge inhibits, recovery, logical off and supply shutdown | [Power and MOSFET behavior](power-on-off.md) |
| SOC, learning, remaining-capacity protection and persistent records | [SOC and capacity](soc-capacity-and-persistence.md) |
| Recharge waiting and soft/hard stop | [Intermittent recharge](intermittent-recharge-soft-vs-hard-stop.md) |
| System status, temperature, heating, balancing, limiting and overcurrent | [States and triggers](states-and-triggers.md) |
| GPIO pulse addressing and its event8 indication | [Internal address chain](../hardware/internal-address-chain.md) |
| Inverter aggregate and reported limits | [Modbus aggregate](../protocols/modbus-rtu.md#2-data-source-system-aggregate-0x2000164c), [CAN](../protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed) |

## 9. Firmware updates

Application update transport, bootloader frames, manufacturer entry instructions, timing, parameter retention and bench evidence are specified in the [bootloader/update reference](../protocols/bootloader-update-protocol.md). Application and bootloader baud rates require separate evidence; the common image header does not establish either.

## 10. Identifying the OEM firmware revision

**It cannot be read out directly.** The image contains only `0x10 0x06` (16.06), or `0x10 0x04` for 16.04. This value is returned by ASCII 0x51 (INFO bytes 10/11), Modbus `0x0001` block register 0x1C, Pylontech 0x51/0x60 and CAN 0x35F/0x320. *(confirmed)*

**It can be derived partially within the seven retained OEM images**, via version-specific functions. Unknown vendor builds and MAINT extensions can change these results; communication failure is not a version identification. All statements come from the code; this has not been tested on a real device.

| Test | Interface | Result → version | Intervention |
|---|---|---|---|
| ASCII **0x51**, bytes 10/11 | Pack bus (each pack) | `10 04` → 16.04.x; `10 06` → 16.06.x | none |
| ASCII **0xAA** (without INFO) to the pack | Pack bus (each pack) | immediate RTN 04 → **≤ 06.12**; no response → **06.13** | minor: with 06.13 and an active binary port, a tunnel request is sent to the connected device |
| Pylontech **0x60** to ADR 0x12 | Inverter RS485, master only | RTN 04 → **≤ 06.03**; response with "SH-EnergyTCH" → **≥ 06.04** | none |
| Pylontech **0x4F** to ADR **0x02** | UART1, **isolated master only**; a slave at address 2 also responds and invalidates this probe on a shared bank | no response → **≤ 06.11**; response → **≥ 06.12** | none |
| Modbus FC03 `0x1000` × 21 | Inverter RS485, master only | Exception 02 → **≤ 06.03**; data → **≥ 06.04** | none |
| Modbus FC04 `0x0000` × 21 | same | Exception → **≤ 06.05**; data → **≥ 06.11** | none |
| Modbus FC03 `0x9000` × 26 or `0x001F` × 9 | same | data → **06.13**; exception 03/02 → **≤ 06.12** | none |
| SP80 vs. 06.04 | Pack bus 0x44 | only detectable in the state "Intermittent recharge waiting" (event 6 bit 1): charge MOSFET (on-off bit 1) off → **SP80**, on → 06.04 | none, but the state must occur |

Result:
- **Via UART0 only**, with the host dispatcher available, 16.04, 16.06.03–06.12 and 06.13 can be distinguished.
- **With access to the master's inverter RS485**, all versions can be separated: 06.03 / 06.04–06.05 / 06.11 / 06.12 / 06.13.
- 06.04 and 06.05 (SP80) can only be distinguished by their behavior.
- Between 06.03 and 06.12, the pack bus commands are identical in content. The only difference (0xA3/0xA5 since 06.11) would only be measurable by writing a serial number string and is therefore not recommended.

## 11. Methodology and limitations

- The tools and commands are described in [tools/README.md](../../mod/docs/tools/README.md).
- The image contains no symbols. All function names are derived from data flow, constants and the protocol PDFs.
- **Not** contained in the image: bootloader, a table of default parameters (defaults are set in the code or kept in the parameter block in internal flash), texts of the BatteryMonitor tool.
- RAM addresses apply to 06.13. Older versions are partially shifted (see section 6).
