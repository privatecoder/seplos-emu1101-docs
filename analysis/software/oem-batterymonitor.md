# OEM BatteryMonitor: application, profiles and protocol behavior

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

BatteryMonitor is the OEM monitoring and configuration application for Seplos BMS devices, including Seplos BMS 2.0/10E/V16 (EMU1101). The versions examined are **V2.1.12_20** and **V2.1.13_20**, including the latter’s 52 Agreement XML profiles.

The findings come from static .NET/CIL analysis, configuration files, XML comparisons and previously documented firmware behavior. The Windows application was not run for the V2.1.13 investigation; no BMS was accessed. A menu item or XML declaration is evidence of what the PC software offers, not proof that a particular firmware accepts the operation.

## 1. Application structure

BatteryMonitor is a Windows serial application built with **.NET Framework 4.5 and WPF**, with DevExpress 15.2 controls and SunnyUI dependencies. Other dependencies include log4net, Newtonsoft.Json and zxing for barcode handling. In the inspected V2.1.12 distribution, most of the approximately 117 MB installation consists of UI libraries; application logic resides in an approximately 2 MB executable.

Its behavior is divided between three sources:

| Source | Responsibility |
|---|---|
| Executable code | Serial connection, command IDs, frame construction/checksums, receive handling, UI workflows and conversion logic. |
| `Agreement/*.xml` | Declarative telemetry layouts, parameter definitions, status labels, function bits, calibration inputs, history layouts and protocol-selection lists. |
| Application settings and language resources | Serial configuration, saved profile path, selected packs, UI language/theme/layout and local login settings. |

The XML supplies a data schema to communication routines implemented in the executable.

The OEM application communicates through a **serial COM port**. No native raw-TCP gateway transport was identified. A network gateway would therefore need a suitable virtual serial-port layer to work with this application.

## 2. Startup, profile selection and connection

`MainWindow.PowerOnLoadProtocol` attempts to load the previously saved profile path if the file exists. The startup code also has a language-dependent fallback to a root 16S profile filename. That fallback branch sets the saved path without calling the same loader again in that branch. It must not be interpreted as reliable automatic profile loading in every first-start case.

The application does **not identify the connected BMS hardware and select a matching Agreement automatically**. A manual import is available through `LoadProtocol_Excecuted` while disconnected/not linking. It saves the chosen path and can select a UI language from the filename suffix, such as `_EN`, `_DE` or `_FR`. Consequently, manually reimporting the profile on every start is not inherently necessary, but choosing the correct family and cell count remains the user's responsibility.

`ProtocolFileTreatMain` parses the profile, builds local model lists and sets `ProtocolLoaded`. Loading the profile itself does not write a configuration block to the BMS.

Serial port, baud rate, data bits and parity come from application settings, not the root 16S Agreement. The inspected V2.1.12 configuration used 9600 baud as its default. This is an application default, **not proof of the baud rate required by every physical BMS port**.

The OEM user selects the number of packs manually through the “Pack total” / pack buttons, with UI choices up to 20. This UI range does not establish a V16 firmware address range. The application polls selected pack addresses and offers a rotating multi-pack tile display; the V2.1.12 configuration used a four-second `LoopDispDuty`. An XML `freshDuty` value of two seconds was also present, but the V2.1.13 `XmlGetBasic` routine does not read that field. A precise polling interval must therefore not be inferred from this XML element alone.

See [ports, protocols and bus ownership](../hardware/ports-and-topologies.md) before connecting: an active Seplos master occupies the UART0 pack bus while polling, and the PC's ability to create a command does not make that bus available.

## 3. Features exposed by the OEM application

| Area | Application behavior | Main command(s) |
|---|---|---|
| Connection | Serial configuration, connect/disconnect, connection status and TX/RX/error indicators. | Application settings. |
| Identification | Protocol/software information, manufacturer/device information. | `4F`, `51`. |
| Telemetry | Cell voltages, minimum/mean/maximum/difference; temperatures, current, pack voltage, capacities, SOC and cycles. Actual fields depend on the profile. | `42`. |
| Status | Balancing, operating status, warnings/protections and color-coded indications. | `44`. |
| Multiple packs | Per-address polling and rotating tiles showing online/status and key measurements. | `42`, `44` per pack. |
| Parameters | Read numeric parameters, function-switch bytes and device name; edit all or individual values; import/export parameter XML. | `47`, `A1`, `49`. |
| Controls | Offers MOSFET, current-limiter, heating, shutdown and factory-reset controls, subject to actual firmware support. | `45`. |
| Clock | Read/set BMS date and time. | `4D`, `4E`. |
| Calibration | Zero-current, current and voltage calibration inputs. | `A0`. |
| Serial strings | Read/write BMS and battery serial strings; barcode-assisted input after the serial-number login. | `A2`–`A5`. |
| Inverter selection | CAN profile dropdown; serial-protocol selection exists in code but the root 16S profile supplies no options. | `A6`, `A7`. |
| History | Read first/next/all alarm-history entries and save results. | `4B`. |
| Recording | Live recording and scheduled start/end/interval settings; communication log with timestamps and frame details. | Cyclic telemetry/status requests. |
| Update | Launch a separate `FirmwareUpdate.exe`. | Separate update protocol. |

`ProtocolCommand` contains the command constants, including `90` for pack count. The generic enum also reuses an `A2` value for a scheduling alias; this does not change the meaning of a BMS serial-string request by itself. The application command catalogue must always be checked against the target handler and port.

Gauges and status coloring use definitions from the profile. Temperature display can use Celsius, Fahrenheit or Kelvin. UI language resources include English and Chinese; additional profile translations exist, but their technical content is not equivalent, as described below.

## 4. What Agreement XML defines

An Agreement has root element `protocolConfig` and `filetype=Protocol`. It describes **how the PC interprets and displays BMS data**; it contains neither firmware nor a complete set of settings to install on a battery.

| Section | Meaning |
|---|---|
| `basicConfig` | Profile name/version, temperature conventions, key measurement labels and some parser/display flags. Not every declared element is consumed. |
| `teleMeter_Group` | Measurement groups, count-field behavior, order, widths, units and scales. |
| `teleSignal_Group` | Alarm/status byte and bit labels, with links to displayed measurements. |
| `int_para_Group` | Numeric parameter names, indices, raw widths, units, scales and optional minimum/maximum/value fields. |
| `bit_para_Group` | Base index, number of switch bytes and labels for byte/bit positions. |
| `teleControl_Group` | Controls offered by the UI; firmware implementation must be checked separately. |
| `adjust_para_Group` | Calibration input definitions and preset input values. |
| `warnHistory` | History data and bit descriptions. |
| `canProtocol` | CAN dropdown labels and numeric selection IDs. |
| `serialPortProtocol` | Serial protocol dropdown entries; empty in the root 16S profile. |

For example:

```xml
<int_para>
  <Name>Battery rated capacity</Name>
  <UnitName>Ah</UnitName>
  <ParaIndex>3A</ParaIndex>
  <ByteNum>2</ByteNum>
  <Scale>0.01</Scale>
</int_para>
```

`3A` is hexadecimal index `0x3A`, decimal **P58**. A two-byte raw value of 28000 is displayed as 280.00 Ah. This is a synthetic conversion example, not an installation setting. The index is a logical protocol index, not a RAM or flash address.

The profile version `2.0` is not a BMS firmware version or proof of its on-wire version. The application obtains the remote protocol version separately from a BMS response.

## 5. Receive decoding and parameter writes

The relevant decompiled methods include `MainWindow.XmlNodeGetIntParaVar`, `XmlGetBitPara`, `TreatRcvFrame`, `ParaManageDialog.SetAllParamsFrame` and `ParaIntVar.ConvertFill/ConvertBack`.

### Index and conversion rules

- `ParaIndex` and `bitParaStartIndex` are parsed as **hexadecimal**.
- `ByteIndex` and `BitIndex` are parsed as decimal.
- `bitParaStartIndex=58` therefore means `0x58` = decimal 88, **not P58**.
- Scaling is applied when reading and inverted when writing. Signed values and temperature conversions also depend on executable code; `Scale` alone does not fully define the data type.
- Some numeric conversion uses culture-dependent `decimal.Parse` rather than explicit invariant parsing.

### Positional decoding

The application uses counts supplied by a response together with the field order and widths in the selected XML. For numeric parameter reads (`47`), the schema determines how bytes populate the local parameter list. The parser is not matching on transmitted parameter names.

All 52 inspected profiles have the same numeric map after decimal-separator normalization:

| Part | Layout |
|---|---|
| Numeric parameters | 87 entries, indices `0x00`–`0x56`: 60 two-byte and 27 one-byte values. |
| Function switches | Eight bytes, logical indices `0x58`–`0x5F`. |
| Device name | Ten bytes in the corresponding complete parameter block. |

Matching counts do not prove matching switch meanings or hardware support.

### Complete and individual writes

ASCII `A1` serializes the current PC model in this order:

```text
pack index
word count + 60 × 2-byte numeric values
byte count + 27 × 1-byte numeric values
switch count + 8 switch bytes
10-byte device name
```

That V16 layout contains **169 INFO bytes**. An unsuitable profile can therefore affect the structure of a write, not just the screen labels. ASCII `49` uses the selected profile's parameter/group index for individual writes. A generated request is not evidence that every index is implemented by the connected firmware.

The hard-coded framing and command handling are described in the [Seplos ASCII analysis](../protocols/seplos-ascii.md). Port-specific write permissions are documented in the [UART capability matrix](../../mod/docs/firmware/uart-write-capabilities.md).

## 6. Parameter exports are a different file type

| File | Root / discriminator | Purpose |
|---|---|---|
| Agreement profile | `protocolConfig`, `filetype=Protocol` | Definitions used to interpret frames and build UI models. |
| Parameter export | `paraGroup`, `filetype=Parameter` | Saved numeric values, function-switch groups and device name. |

Each inspected Agreement contains exactly three literal `Value` entries, all calibration inputs: **0.00 A, −25.00 A and 3.300 V**. They are not measured values or a bank of default SOC/capacity/protection settings.

When importing a parameter export, `LoadParamValueFile` matches numeric entries to loaded fields by **name string**. Renaming a field or using a differently translated profile can leave entries unmatched. This differs from positional wire decoding and is an important compatibility limitation.

Generic exports are provided under [BatteryMonitor configuration exports](../examples/batterymonitor-config-exports/); their [annotated example](../examples/batterymonitor-config-exports/parameter-export-example-annotated.xml) explains the file rather than defining a protocol profile. See also [configuration parameters](../firmware/configuration-parameters.md).

## 7. Selecting a profile for Seplos BMS 2.0/10E/V16 (EMU1101)

For 16S EMU1101, the root `Agreement/16S_V20_ADDR_EN.xml` and Chinese `Agreement/16S_V20_ADDR.xml` are the appropriate starting points. This is supported by the known V16 layout, not the filename alone. A profile change does not change the physical hardware or its firmware capabilities.

| Profile family | Temperature definitions | Important distinction |
|---|---|---|
| Root / EMU1101 | Six: four cell probes, ambient and power stage. | Group7.Bit5 is automatic addressing on the examined V16. |
| EMU1102 | Eight: six cell probes, ambient and power stage. | Not interchangeable merely because the numeric parameter count matches. |
| EMU1201 | Four without, six with current limiter. | Group7.Bit5 is labelled “Multi-channel extension contact”. |
| EMU1204 | Five, including limiter temperature. | Group7.Bit5 is labelled as series mode. |

These are profile differences; the other families were not all checked against their own firmware.

### English and Chinese root profiles expose different telemetry

Their common parameter indices, widths and scales agree. However, the last counted telemetry block has **six definitions in English and ten in Chinese**. The Chinese profile additionally defines:

| OEM label | Raw width / scale | Firmware-based interpretation |
|---|---|---|
| `温漂电流` | 2 bytes / 0.001 A | Reference/drift current. |
| `零点电流` | 2 bytes / 0.001 A | Offset-corrected idle current. |
| `充电能量` | 2 bytes / 0.1 kWh | Charged energy. |
| `放电能量` | 2 bytes / 0.1 kWh | Discharged energy. |

OEM 16.06.13 announces ten values in that final block (`0x0478`, `movs r3,#0xA`). The generic PC parser processes at most the number of definitions available in the profile and skips remaining counted values. This explains why the English schema does not expose four values already supplied by the firmware. It is a static code/layout conclusion, not a new Windows UI test.

### Translations can change available functions

The German profile omits Group7.Bit6 and Bit7 definitions. On the examined V16 these relate to automatic role/address formation and a CCL calculation variant. All six European profiles also contain an older five-entry CAN list instead of the root profile's seven, with some incorrect labels for OEM .13: for example, ID5 is labelled “Luxpower” while the firmware uses **GINLONG**.

The root list provides IDs 1–7: PN-GDLT, GRWT, VCTR, SMA-SF, GINL, STUD and MUST. Firmware-based interpretation takes precedence over a stale dropdown label.

### Locale-specific copies

The folder `英文操作系统` means “English operating system”. For four directly comparable 15S/16S files, including `16S_V20B_ADDR_EN.xml`, the parsed contents differ from the root counterparts only by dot-to-comma substitutions in text values. This is not a claim that every raw file byte is obtained by replacement; XML declarations are outside that comparison.

Together with culture-dependent numeric parsing in the executable, these files indicate a locale workaround, not a proven different hardware or firmware family called “V20B”. Machine-readable numbers should be parsed independently of UI locale in a replacement.

## 8. Local logins and recording

In the inspected V2.1.12 configuration, the local username/password are stored in plaintext as `admin` / `admin`; `SnLogin=888888` gates serial-number functions. These are OEM application defaults, not credentials collected from an installation. `LoginDialog` compares configured values locally and sets `Administor`. This is a **PC-side UI permission**, not authenticated access enforced by the BMS.

Telemetry can be recorded to files named `RealTimeRecord/<timestamp>_Pack_<n>.xls`. The V2.1.12 recording format is tab-separated text using ISO-8859-1, rather than an Excel workbook. Fields include pack number, date/time, mode, warnings, cells, temperatures, current, voltage and capacities. The communication log separately records transmitted/received frames with direction, time, representation and annotations. A replacement should treat the `.xls` extension as a legacy naming convention and inspect the actual content when importing it.

## 9. Firmware updating is a separate application

BatteryMonitor launches `FirmwareUpdate.exe`; the Agreement XML does not define flash programming. The V2.1.12 updater sends an ASCII `45/06` restart followed by a 50 ms wait and the updater's `:::: … \r\r\r\r` bootloader frames: query package size (`R F L`), enable flash (`W F E`), send blocks (`W F D`) and start (`W F G`).

Checksum boundaries, response validation and block sizing are covered in the [bootloader/update protocol analysis](../protocols/bootloader-update-protocol.md), which distinguishes static updater findings, historical measurements and assumptions. The application-port baud rate must not be used to infer a bootloader baud rate without evidence.

## 10. Firmware truth and MAINT extensions

Profiles are useful evidence of OEM intent, but not a complete specification of firmware behavior. For example, P82 “Connection fault impedance” is declared in XML without a demonstrated evaluation path in the examined OEM .13. Some switch labels also differ from the code's behavior.

MAINT preserves the underlying V16 parameter and telemetry formats, but OEM profiles do not describe its additional permissions, persistent pack lock or maintenance/diagnostic commands. Old Group0 labels must not be applied to those new meanings.

For an MAINT-aware monitor:

- Determine capabilities per addressed pack using `64/03` format and image flags; use `64/04` for the corresponding extended diagnostics.
- Apply firmware-specific bit semantics and freshly read runtime permissions.
- Keep UART0 (RS485-1/2), UART1 (RS485 pair in the CAN socket) and UART2 (local display) distinct.
- Distinguish Seplos-ASCII requests from addressed MAINT binary requests on UART1. Loading an Agreement adds neither a binary transport nor new handlers to an OEM slave.

Use the [current capability matrix](../../mod/docs/firmware/uart-write-capabilities.md), [ASCII protocol](../protocols/seplos-ascii.md) and [port topology analysis](../hardware/ports-and-topologies.md) for actual access conditions.

## 11. What is useful for OpenBMS Monitor

The strongest reusable idea is a **central typed field model** shared by decoding, labels, units, validation, help and import/export. OEM XML can seed or verify that model, but technical identity should use stable IDs rather than translated names. Parameter index, wire position, display name, hardware family and firmware capabilities must remain separate concepts.

For an application focused on Seplos BMS 2.0/10E/V16 (EMU1101), a reviewed internal model or an offline XML import during development may provide the benefit without a freely loadable runtime XML engine. A generic runtime loader becomes useful only if multiple hardware families are genuinely supported and separately validated. Existing OpenBMS models/generators should be checked before adding another schema layer.

Useful concrete follow-ups are to check support for the four extra Chinese-profile telemetry fields, correct stale OEM labels against firmware evidence, use stable IDs for exports, and separate UI translation from capabilities. Evaluate these changes against the existing application before adding a new UI or XML loader.

## 12. Provenance and repeatable inspection

The V2.1.13_20 executable examined for the Agreement analysis has SHA-256:

```text
8c82f5415c9d51b6ecde84fa350ccf5b0f0b6b0a5e19fec3f493fd4394a133f3
```

Its size is 2,288,128 bytes. The .NET metadata identifies runtime `v4.0.30319` and MVID `2bd010d2-8c29-4da9-aed4-4c50e37b0b89`. These identify the inspected artifact, not all BatteryMonitor releases.

The reusable [Agreement inventory tool](../../mod/tools/firmware-analysis/batterymonitor_agreement.py) uses only the Python standard library. It inventories profiles, hashes and layout differences without executing the OEM application or opening a serial port. The default input is the vendor BatteryMonitor ZIP. `--agreement` also accepts another ZIP or an extracted Agreement directory; XML is inspected without executing the OEM application.

From a neutral working directory, using generic paths:

```sh
cd /private/tmp
python3 -I '/path/to/project/mod/tools/firmware-analysis/batterymonitor_agreement.py' \
  --agreement '/path/to/extracted/BatteryMonitor/Agreement' \
  --out '/path/to/new-agreement-catalogue.json'
```

No venv or additional packages are needed. `--out` exclusively creates a new file and refuses to overwrite one. This inventory checks declarations and file identity; it does not validate BMS handlers.

Detailed evidence is retained in the ignored Agreement evidence directory (`OEM-BatteryMonitor-Agreement-2026-10-26`, local reference, not published), including the complete XML catalogue, hashes, comparison results, selected decompiled classes and REA metadata. Dated monitor-design proposals (`monitor-design`, local reference, not published) remain separate from the OEM application analysis. These supporting records are not part of the public repository. Original vendor distributions remain under [vendor software](../../vendor/software/).

The complete running Windows UI, every special UI path and every supported hardware family's firmware have not been verified. Version-specific findings above must not be generalized into a guarantee that every displayed action succeeds on every BMS.
