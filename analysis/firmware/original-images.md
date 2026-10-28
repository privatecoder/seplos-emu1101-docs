# Firmware images

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seven firmware images for the Seplos BMS 2.0/10E/V16 (EMU1101) (manufacturer photograph confirms an EMU1101 10E/V16 board). The files in [`vendor/firmware/`](../../vendor/firmware) are the unmodified vendor `.ehex` files, as extracted from the ZIP archives in which the vendor distributes them. Use the hashes below to check that a file you got elsewhere is identical.

## Hashes

`.ehex` = the vendor file. "Image" = the decoded flash image (Intel-HEX records after the 256-byte header, gaps filled with `0xFF`, starting at address 0), produced with [`ehex2bin.py`](../../mod/tools/firmware-analysis/ehex2bin.py).

| File | Version | Build date | Suffix | .ehex size (bytes) | .ehex SHA-256 | .ehex MD5 | Image size (bytes) | Image SHA-256 |
|---|---|---|---|---|---|---|---|---|
| `CAN1101[V16.04.06_PN01_220924_9600].ehex` | 16.04.06 | 2022-09-24 | 9600 | 136024 | `2b00410571fcb9dac04c4cb8640a84ab583ee7536ab562a594325b45752f6198` | `d788d6ae486e6466f8b9d00a321bc269` | 48096 | `fa38fbd4dba02eb4bc759612802b61b26582a6c3d49da80f36acae86bd5d5890` |
| `CAN1101[V16.06.03_PN01_230412].ehex` | 16.06.03 | 2023-04-12 | – | 135701 | `246e1eca5637bcc1e16c27f64501c2024c57726ebd84d4a413dcb3e71b813d9e` | `585ed8c9aa7ca94eaab2cb6298cf519a` | 47980 | `689d3819eb9f73e12473764094843acfd619a58e5ec0c7b1da76724dac364706` |
| `CAN1101[V16.06.04_PN01_230613].ehex` | 16.06.04 | 2023-06-13 | – | 141101 | `d69f27c1650e31cf24260988945ed11631ea1ae0afd450dae823310457cca5f6` | `382fd2239fb058228655ac3d93a6371d` | 49900 | `390299c85aae21b1d26194d304a85bd31f26b9c51f28e74bf145ba232d5e8c2c` |
| `CAN1101[V16.06.05_PN01_230916_SP80].ehex` | 16.06.05 | 2023-09-16 | SP80 | 141101 | `c8f0560b7d32df305b1115c21aa2016aa7c3f85e669a8c9c3ae4922a1bb5c240` | `df46fe55d626bb859020b880802a1c2e` | 49900 | `a2abc282abf9d34412c3b5e359077d81762187a0c9d5113a9c56c33b02e328a2` |
| `CAN1101[V16.06.11_PN01_240713].ehex` | 16.06.11 | 2024-07-13 | – | 148285 | `2dae963fd5aa11aa3eb6b97e20528e62fd0475d9964a5dae1f6284af711653a0` | `06936453b5e7b72e2231ad6950967893` | 52452 | `b686b69e69878390fddf24f54cb2ab6569ce305c2c52b300e9a67b533fd99747` |
| `CAN1101[V16.06.12_PN01_241209].ehex` | 16.06.12 | 2024-12-09 | – | 148338 | `46d25a5f565ae01445d34d05c35d5202d5fbe46dcf7dc474895e6a2c84109506` | `43ee66be561e9b087c9326869ed972e9` | 52472 | `f487ac4bc3b89c5f9afde647aa1acd8c1e7b260e6b20a1a286123abe4cf607a2` |
| `CAN1101[V16.06.13_PN01_250607].ehex` | 16.06.13 | 2025-06-07 | – | 150085 | `0ea75c9834cf19789a58f58db8cde1a2bbd722a8f5a7bde7f00106f59b91ccf6` | `b2830bc660218b9515de2c58a426d440` | 53092 | `5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95` |

Verify:

```sh
shasum -a 256 vendor/firmware/*.ehex
```

## File name and header

- File name: `CAN1101[V<HW>.<Major>.<Patch>_PN01_<YYMMDD>[_Suffix]].ehex`, e.g. `V16.06.13` = hardware line 16, firmware 06, patch 13, built 2025-06-07. The firmware itself only knows `16.06` (`0x10 0x06`); the patch number exists only in the file name (see [firmware analysis](firmware-analysis.md)).
- All images share the same 256-byte header (16 pseudo Intel-HEX records): `SWM181RCT6_64_M0` (MCU Synwit SWM181, Cortex-M0), `EMU1101_10D_HW16`, `RS485Y19200N9600`, padded with `0x55`.
- `_9600` (16.04.06): RS485-1/2 run at 9600 baud instead of 19200.
- `_SP80` (16.06.05): special build, one byte different from 16.06.04 (charge MOSFET also off during "intermittent recharge waiting").

The [manufacturer catalogue photograph](../hardware/hardware-specifications.md#sh-energy-catalogue-emu1101-product-family), PDF p.11, shows PCB silkscreen `EMU1101_PCBA-V16` and a product sticker `1101-48100-10E-V16`. It directly documents a 10E/V16 board in the EMU1101 family. The header string remains literally `EMU1101_10D_HW16`; the reason for its `10D` token is not established by the photograph.

## Which version?

| Version | Short summary |
|---|---|
| 16.04.06 `_9600` | baseline |
| 16.06.03 | new 16.06 line |
| 16.06.04 | Pylontech 0x60, Modbus `0x1000` block |
| 16.06.05 `_SP80` | special build of 16.06.04 |
| 16.06.11 | CAN protocol MUST, new charge logic, many Modbus blocks |
| 16.06.12 | temperature-hysteresis bug fix, CCL "active" mode for multi-pack, Pylontech ADR 0x02 |
| 16.06.13 | Modbus fixes and additions, ASCII/binary tunnel 0xAA/0xAB; no change to battery logic or CAN protocol 1 |

Details: [firmware changelog](firmware-changelog.md). How to determine the running patch level: [firmware analysis](firmware-analysis.md) (patch derivation).

The vendor update instructions use the FirmwareUpdate tool over UART0/RS485. The
bench setup used 19200 baud; the bootloader rate specifically paired with the
16.04.06-9600 image remains unverified. See the
[bootloader/update protocol](../protocols/bootloader-update-protocol.md).

## Archive provenance and patcher input

The table above identifies the seven canonical EHEX payloads by complete file and decoded-image hashes.
`Seplos update doc.docx` was extracted from the original16.06.11 ZIP and is
retained with the [vendor update documents](../../vendor/docs/batterymonitor).
The complete original ZIP archives, including macOS metadata, remain in the
ignored local backup collection. Duplicate download copies are also retained
locally rather than alongside the canonical OEM files.

Pass an original EHEX to the [offline patcher](../../mod/firmware/patcher).
Already MAINT-patched inputs are deliberately rejected. Raw backups and
locally generated patch images are not included in a fresh public checkout.
