# Product, hardware and firmware identification

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

| Identification field | Value | Meaning |
|---|---|---|
| Seplos product generation | BMS 2.0 | Seplos' commercial generation name. |
| OEM platform | EMU1101 | SH Energy / Shanghai Energy Electronic Technology platform and board family. |
| Product variant | 1101-10E | Platform plus current-limiting/communication option code. |
| Hardware version | V16 | Physical board version, marked `EMU1101_PCBA-V16`. |
| OEM reference firmware | 16.06.13 | Complete OEM file version used as the behavioral reference; another installed image must be identified separately. |

Use **the BMS**, **the firmware** or **the patcher** in ordinary prose. When full
identification is useful, use **Seplos BMS 2.0 (EMU1101, hardware V16)** and state
the product variant and firmware separately. A reference firmware value is not
a claim about the firmware currently installed on every pack.

## Product number and option code

A complete product number such as `48150-1101-10E` includes the nominal voltage
class and current rating: `48` is the 48 V class and `150` is the 150 A product
configuration. The current token is amperes, not battery capacity in ampere-hours.
Other ratings in the family do not change this field's meaning or make a
particular board's current rating interchangeable.

The manufacturer explicitly splits the related EMU1101 product number
`24200-1101-10E-EJ01-08S` into fields in its
[internal model definition, PDF pp.5–6](https://www.enjiebms.com/uploads/file/20250427/emu1101-24v-24200-1101-10e-08s-v1-0-en.pdf#page=5):

| Token | Manufacturer field |
|---|---|
| `24` | Voltage class. |
| `200` | Current rating. |
| `1101` | Board/platform type. |
| `10` | 10 A current limiting; the English table calls this field “Infinite flow”. |
| `E` | Communication option; the table lists CAN and RS485. |
| `EJ` | Customer code. |
| `01` | Customer-specific model index. |
| `08S` | Series cell count. |

This is direct evidence for the manufacturer's model-code scheme in the EMU1101
family. That source describes a 24 V / 8S configuration; its wiring, ratings and
optional hardware must not be transferred to the examined board. The retained
[48150 specification](<../../vendor/docs/specs/Seplos BMS 48150-1101-10E (EN).pdf>)
and catalogue independently corroborate the 10 A limiter and communication
features. `10E` is an option/variant code, not evidence of hardware revision E.

`16S` means sixteen series-connected cells. Hardware `V16` is a separate field;
its number does not specify the configured cell count.

## Hardware version: V16

Three independent labels support the hardware interpretation:

1. The [retained board photograph](<../../vendor/images/PCB front and back.jpg>)
   carries `EMU1101_PCBA-V16` and `SH ENERGY TECH` in the silkscreen.
2. The [SH Energy catalogue, PDF p.11](<../../vendor/docs/oem catalog/SH Energy BMS-Catalog.pdf#page=11>)
   identifies EMU1101 and shows the same silkscreen plus sticker
   `1101-48100-10E-V16`. These markings are image content.
3. [TÜV SÜD report 085-282360233-000, PDF p.13](https://www.comp-gmbh.com/wp-content/uploads/2023/05/trf.pdf#page=13)
   identifies the BMS as `EMU1101 PCBA-V16`, explicitly separates hardware
   version `V16` from software version `16.04`, and lists the product variant
   `48100-1101-10E-BC17-16S`.

The report concerns its particular battery-system sample. It corroborates the
nomenclature; it does not establish certification of every Seplos board or
binary compatibility across all EMU1101 variants. Accessory boards have their
own hardware versions, which must not be substituted for the main BMS version.

## OEM firmware version

The retained file `CAN1101[V16.06.13_PN01_250607].ehex` identifies OEM firmware
16.06.13, built 2025-06-07. Its header literally contains
`EMU1101_10D_HW16`. `HW16` supports the hardware-line identification; the meaning
of the internal `10D` token remains unconfirmed. Preserve that literal header
rather than rewriting it to `10E`.

The filename scheme is interpreted as hardware line `16`, firmware line `06`
and release/patch `13`. The application itself stores/reports `16.06`; `.13`
is supplied by the file identity and must be established from the image or
other release-specific evidence. The two stored version bytes alone do not
identify the patch release. [Container and version evidence](../firmware/firmware-analysis.md),
[original image hashes](../firmware/original-images.md).

MAINT 1.5.4 and MAINT 1.6.4 are separate modification-release numbers. They are
based on OEM 16.06.13 and do not rename the physical hardware.

## Seplos generation, document and software versions

Seplos uses **BMS 2.0** as a product-generation name when distinguishing it from
BMS 3.0. [Manufacturer terminology](https://www.seplos.com/seplos-48v-100a-lithium-battery-bms-3.0-c.html).
That commercial name is a separate namespace from the OEM board version.

The 48150 specification's revision table lists document **V2.0**, dated
2022-07-25, with a note about V16 functions. This is the revision of that PDF;
it does not independently establish the Seplos generation or firmware version.
The catalogue's metadata date is likewise not a hardware or firmware release.

BatteryMonitor V2.1.12/V2.1.13 and Agreement profile names such as
`16S_V20_ADDR_EN.xml` identify PC software/profile formats. They do not identify
the board revision or replace a firmware compatibility check.

## Evidence scope

The 48150 specification is the board-level manual reference. Original vendor
files, product stickers, silkscreen labels and firmware headers retain their
literal names. Product identification by itself does not prove firmware
compatibility: validate the exact board, image and supported configuration.
The two additional online source PDFs, rendered decisive pages, hashes and
retrieval details are retained in the ignored local hardware evidence collection.
