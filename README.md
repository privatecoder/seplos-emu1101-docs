# Seplos BMS V2.0 (10E / EMU1101, SH Energy ETECH): firmware and protocol documentation

The Seplos BMS V2.0 (boards "10C/10E", BMS module EMU1101, hardware revision 16; manufacturer string in the firmware: "SH-EnergyTCH Co.,Ltd") ships without changelogs and with only a partial protocol description. This project reconstructs both from the firmware itself: seven firmware images from **16.04.06 (2022)** to **16.06.13 (2025)** were disassembled and compared function by function.

Everything here is derived from the firmware code unless marked otherwise. It is unofficial and not affiliated with Seplos or SH Energy.

## Contents

| Path | Content |
|---|---|
| [firmware/](firmware/README.md) | The seven vendor firmware images (`.ehex`) with SHA-256/MD5 hashes, file name scheme, version overview |
| [docs/firmware-changelog.md](docs/firmware-changelog.md) | **Unofficial changelog** of all versions, including the SP80 special build |
| [docs/firmware-analysis.md](docs/firmware-analysis.md) | `.ehex` format, memory layout, hardware and interfaces, function map, **RAM map**, **parameter and function switch tables**, protection logic, persistence, update procedure |
| [docs/states-and-triggers.md](docs/states-and-triggers.md) | **What happens when?** Conditions, durations and prerequisites for SOC jumps (98.2 % hold, 23/70/90/98/100 %, 10 %, 0 %), capacity learning, intermittent recharge, charge/discharge lock, current limiter, standby shutdown, CVL/CCL/DCL; comparison with the Seplos specification |
| [docs/intermittent-recharge-soft-vs-hard-stop.md](docs/intermittent-recharge-soft-vs-hard-stop.md) | **Intermittent recharge: soft stop vs. hard stop.** What a full pack does in the standard firmware and in SP80, five situations with examples, when the SP80 behaviour is the better one, and how to apply it to later versions |
| [docs/configuration-parameters.md](docs/configuration-parameters.md) | **Guide to the BatteryMonitor parameter export**: structure, translation errors, every parameter and every function switch bit with its effect |
| [docs/protocols/seplos-ascii.md](docs/protocols/seplos-ascii.md) | **Firmware-based description of the "MODBUS-ASCII" protocol** (YD/T 1363.3 style): ports, baud rates, framing, checksums, addressing, all commands, bit fields, balancing |
| [docs/protocols/undocumented-commands.md](docs/protocols/undocumented-commands.md) | Everything the vendor documentation leaves out: ASCII commands 0x45, 0x47, 0x49, 0x4B, 0x4D/4E, 0x51, 0xA0–0xA6, 0xAA/0xAB, deviations in 0x42/0x44, binary (display) protocol |
| [docs/protocols/intra-pack.md](docs/protocols/intra-pack.md) | **Multi-pack communication (CID2 0x5A)**, fully decoded, with captured frames |
| [docs/protocols/can.md](docs/protocols/can.md) | **What is sent to the inverter via CAN**: all 7 protocols (Pylontech/Deye, Victron, SMA, Growatt, Ginlong, Studer, MUST), limit calculation, send timing |
| [docs/protocols/modbus-rtu.md](docs/protocols/modbus-rtu.md) | Undocumented **Modbus RTU slave** on the inverter-side RS485 bus: all register blocks |
| [docs/protocols/pylontech-rs485.md](docs/protocols/pylontech-rs485.md) | Undocumented **Pylontech ASCII protocol** (0x60–0x63) on the inverter-side RS485 bus |
| [config/](config/) | Example BatteryMonitor parameter export and an annotated copy (comments for every parameter) |
| [specs/](specs/) | Vendor documents referenced by the docs (Seplos protocol V2.0, PACE Modbus V1.3, Seplos battery specification) |
| [tools/](tools/README.md) | Scripts used for the analysis (ehex → bin, disassembly helpers, cross references) and `hardstop.py` (SP80 behaviour for later versions) |

## Key findings

1. **Format:** `.ehex` = 256-byte header (`SWM181RCT6_64_M0` / `EMU1101_10D_HW16` / `RS485Y19200N9600`) + plain Intel-HEX. Not encrypted, not signed. MCU: Synwit SWM181 (Cortex-M0, 48 MHz), built with Keil.
2. **Version number:** the image only knows "16.06". Patch level and build date exist only in the file name; the patch level can be derived from features (see firmware analysis).
3. **Interfaces and protocols (far more than documented):**
   - RS485-1/2 sockets (UART0, **19200 baud**, 16.04.06: 9600): Seplos ASCII with all commands, including intra-pack 0x5A and control commands. A master pack (DIP address 0 with slaves) polls its slaves there and **never answers requests on this bus**.
   - RS485 pair in the CAN socket (UART1, **9600 baud**): 0x42/0x44/0x51 of every pack at its DIP address, plus **Modbus RTU** (read only) and **Pylontech ASCII** (master only).
   - RS232/TTL (UART2): **binary protocol**, probably for the LCD display.
   - CAN: 7 protocols, transmit only, master only, all frames once per second.
4. **Almost all inverter-facing data are system values computed by the master** (DIP 0) over all online packs (exceptions: e.g. the CAN cycle count is the master's own).
5. **Pylontech/Deye CAN:** CVL = pack over-voltage protection parameter (fixed); CCL = charge over-current warning ÷ 2 (or − 10 A) × chargeable packs, 10 A total when all packs have a charge warning, 0 when a cell exceeds OVP + 30 mV, with ramp; DCL = discharge over-current warning − 10 A × packs; SOH always 100.
6. **SOC logic:** coulomb counting with a hold at 98.2 % until a cell reaches the cell high-voltage warning, voltage-based recalibration (100 % after 30 min at ≥ N × cell high-voltage warning with < 3 A per pack), capacity learning only over a full charge-to-empty discharge.
7. **SP80 (16.06.05)** differs from 16.06.04 by exactly one byte (charge MOSFET also off during "intermittent recharge waiting"); not carried into later versions.
8. **Most important improvements:** 16.06.11 MUST protocol and cleaner charge-enable/CCL logic; 16.06.12 temperature-hysteresis bug fix and "active" CCL mode for multi-pack systems; 16.06.13 Modbus current fix. ⚠ 16.06.13 changes Modbus `0x9000` from 21 to 26 registers; masters reading 21 get exception 03.

## Confidence tags

- **confirmed** = read directly from the code
- **probable** = inferred from data flow or context, or the code is clear but the hardware behind it is not
- **assumption** = interpretation, e.g. mapping register blocks to inverter brands

Addresses refer to firmware 16.06.13 unless stated otherwise.

## Open points

Not derivable from the firmware:
- whether the self-hold output (GPIO `0x50001000` bit 1) really cuts the BMS supply after shutdown, and which current the hardware current limiter allows
- the wiring of the pulse-chain auto addressing (GPIO 7/8/9)
- the exact gap between CAN frames within a burst (calculated ≈ 2.8 ms)
- which inverter brands the various Modbus blocks were written for
- the purpose of the 6 bytes in the 0xAA/0xAB tunnel
- location and function of the bootloader

## Disclaimer

The firmware images are the vendor's files, provided unchanged for reference and verification (see hashes). Flashing firmware or changing BMS parameters is at your own risk. Vendor PDFs in `specs/` are the property of their respective owners.
