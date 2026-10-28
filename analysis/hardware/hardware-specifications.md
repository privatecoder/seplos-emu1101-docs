# Hardware specifications and manufacturer documentation

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The 48150 and 48200 product specifications describe 10E hardware, wiring and accessories. Manufacturer specifications are not measurements or proof that every 10E board has the same optional components.

## Sources and page numbers

- **H150:** [Seplos BMS 48150-1101-10E (EN).pdf](<../../vendor/docs/specs/Seplos%20BMS%2048150-1101-10E%20%28EN%29.pdf>), 35 PDF pages. Revision table V2.0,
  2022-07-25; cover marked 48V150A; PDF metadata date 2022-10-20. SHA256:
  `410da133d8b23d7d93057d1f3ee972c53e331b3ad56bd4c905024f5eb73fe116`.
- **H200:** [EEL 48200-1101-10E (EN).pdf](<../../vendor/docs/specs/EEL%2048200-1101-10E%20%28EN%29.pdf>), **40 actual PDF pages** despite printed
  “of 35” footers and inconsistent numbering. EEL/48200 cover; revision table
  V1.0, 2022-06-16; PDF metadata date 2023-02-09. SHA256:
  `0fde48df73c9307a55fa7c265def2c62904294b184d61b7b6d57e58813cf05d9`.

All page references below are actual PDF pages, starting at 1. Both sources
predate OEM .13. Text, metadata, page mapping and selected rendered pages are retained under the ignored `local/research/hardware/evidence/Handbuchabgleich-2026-10-24/` directory.

## Additional specifications and accessory evidence

| Topic | Source | Additional information and limits |
|---|---|---|
| Cell voltage accuracy | Both p.6, §3.1 | ±10 mV at 0–45 °C; ±30 mV at −20–70 °C. Manufacturer limits, not measured. A 1 mV display increment does not imply 1 mV accuracy. |
| Cell thermistors | Both p.6, §3.2 | 10 kΩ, B=3435; temperature deviation within ±2 °C. Resistance reference temperature and B interval are unspecified; do not assume this describes every internal sensor. |
| Current and SOC accuracy | Both p.6, §3.3/3.5 | Claimed better than ±1% current and ±5% SOC; percentage reference and full conditions unspecified. No automatic 5%-deviation correction command follows from this claim. |
| Hardware current rating | H150 p.11; H200 p.10 | H150 continuous charge/discharge 150 A typical,160 A maximum; H200 200 A typical. Both output resistance <2 mΩ and operating current <40 mA. Firmware replacement does not upgrade the hardware rating. Nominal current is distinct from configurable overcurrent protection. |
| Operating environment | H150 p.11; H200 p.10 | Operating voltage 40–59 V versus 41–59 V; −20–70 °C. H150 storage −40–85 °C and humidity10–85%. These are BMS specifications, not cell charging permissions. |
| Alarm contacts | H150 p.8, §3.17 | Two optional dry-contact alarm channels with different event groups, detailed below. No GPIO mapping, pinout, rating or proof of installation on any particular board; these specifications do not establish remotely controlled relays. |
| Aerosol contact | H150 p.8, §3.18 | Optional contact causes a BMS fault alarm. It does not establish fire-extinguisher actuation, polarity, connector or event-bit mapping. |
| Bluetooth feature scope | H150 pp.8–9, §3.19 | Data/alarms, parameter and switch editing, inverter configuration and individual-battery selection in parallel installations. No wire-protocol definition or proof of a master proxy to other packs. |
| Actual display models | H150 pp.32–34; H200 pp.38–39 | LCD003_PCBA-V11 pictured. H200 p.38 explicitly shows LCD003 without Bluetooth and **LCD004_PCBA-V12 with Bluetooth**. H150 text also names LCD005. The LCD004 evidence is in the image, not the extracted text. Do not assume LCD003/004/005 share a protocol format without capture evidence. |
| Display dimensions | H150 p.33; H200 p.39 | Drawing: board105×55 mm, mounting centres100×50 mm, display area66.3×38.3 mm. Accessory-specific, not universal case dimensions. |
| Automatic address chain | H150 pp.10/31, §3.22/10.5 | Optional automatic DIP addressing, COM OUT/COM IN chain drawing, default limit16 units. Supports the firmware interpretation but does not identify exact GPIO-to-RJ45 wiring. Firmware still admits21 slaves. |
| RM485 in the CAN socket | H150 p.27, §10.1 | Explicit9600-baud RS485 interface with pinout. Additional written evidence for UART1 already used in practice. H200 does not document this populated interface. |
| Separate cell-group taps | H150 pp.24–26; H200 pp.31–32 | Harness A ends at CELL8+; B begins separately at CELL9−. H150 explicitly relates the two taps to measurement accuracy. Four cell thermistors split across the harnesses. This adds a physical connection drawing to the documented P83–P86 connector compensation; it does not permit an arbitrary connection order. |
| Connection and use constraints | H150 pp.26/35; H200 pp.32/40 | Assembly order B−,harness A,harness B,B+,then charger/load; disconnect load and switch off before reverse disassembly. No series-connected BMS; external switch input must not be connected to other equipment without compatibility confirmation. The100 V component rating is not a100 V operating rating. |
| LED patterns | H150 pp.18–19; H200 pp.24–25 | Blink on/off pairs0.25/3.75 s,0.5/0.5 s,0.5/1.5 s; SOC bands25/50/75%; highest active SOC LED flashes while charging. Intended behavior, not a newly verified implementation of the LED driver. |

### Socket variants

H150 p.27: **1/8 RS485-B,2/7 RS485-A,4 CAN-H,5 CAN-L,3/6 GND**.
RM4859600 baud; CAN500 kbit/s in this manual. The firmware's MUST100 kbit/s
exception is not described here.

H200 **PDF p.33 / printed p.28** also has CAN-H4 and CAN-L5, but labels
1/2/7/8 unconnected. H150 p.28 labels UART0 pins4/5 internal communication;
H200 p.33 labels them NC. Different documentation/board variants must be
distinguished. A separate Mason230 Ah specification gives CAN-H/L in the opposite order; that table must not be attributed to these two PDFs. Pinout evidence does not expand OEM
command permissions.

### Optional dry contacts

H150 §3.17 channel1: SOC alarm, temperature alarm/protection, undervoltage
alarm/protection and charge/discharge overcurrent alarm/protection. Overvoltage
is explicitly excluded. Channel2: temperature-sensor failure, short circuit,
cell voltage above cell OVP+30 mV, cell-difference fault and transient overcurrent.
Open/closed behavior, contact rating, connector and OEM .13 implementation
are unspecified. This is not proof that AA/AB commands directly drive these
two alarm contacts.

## Firmware behavior and specification differences

Firmware conditions for P81 cycle counting, SOC corrections/protection, recharge waiting, connection compensation, current limiting, standby shutdown, charge activation, precharge and master broadcasts are covered in [states and triggers](../firmware/states-and-triggers.md),
[original power behavior](../firmware/power-on-off.md), and
[SOC, capacity and persistence](../firmware/soc-capacity-and-persistence.md). “At least300 history
records” is a minimum specification; the firmware supports500×128-byte records.
The SOH claim does not establish a working SOH estimator: documented firmware
outputs remain fixed100%.

| Manual statement | Interpretation against existing evidence |
|---|---|
| Cycle increment after80% discharge in H150,20% in H200. | Configurable P81, not a new algorithm or a universal default. |
| H150 OVP discharge release >10 A and UVP charge release >3 A; H200 >1 A. | OEM .13 uses >10 A for about10 s and a≥3 A UVP charge path. Do not import H200 thresholds into .13. |
| OVP recovery requires voltage and SOC<96%. | Firmware separates OVP hysteresis and intermittent-recharge inhibition. |
| Charger detection at port>pack+0.5 V. | The analyzed .13 path uses+1.0 V with its MOSFET conditions; another path has separate hysteresis. |
|6-second button in H150; H200 §7.8 says3 seconds but §3.9 says6. | Inconsistent within H200. Firmware's documented>3-second detection remains authoritative for the analyzed version. |
| H150 p.30/H200 pp.35–36 master table sets DIP8 ON for2–8 units. | Visually confirmed table error; conflicts with examples on the same pages. DIP5–8 encode slave count; two units use DIP5 ON,DIP8 OFF. |
| H150 §9.1 calls CELL15+ B+. | Conflicts with its16S diagram and CELL16+ row; do not use as wiring advice. |
| H150 says three display types but names only LCD003/LCD005. | Incomplete text; H200 image additionally identifies Bluetooth LCD004. |
| H150 describes ambient protection stopping both directions; H200 describes an ambient alarm without stopping. | Distinguish warning from protection. This does not mean ambient temperature never inhibits current; the actual masks and priorities are documented from code. |
| Passive limiter current can be set. | P71 sets duration; current findings indicate a hardware-defined limiting current. No additional configurable physical limiter-current register is established. |
| Sleep table maximum50 µA,typical0; prose says zero consumption. | Undefined measurement/supply conditions; not proof of zero drain or RTC/SOC retention. |
| Block diagram draws MOSFETs in the B+→P+ branch. | Not a circuit schematic or sufficient evidence for actual high-/low-side placement,body-diode behavior or isolation. |

Neither source provides MAINT functions, a 64 service command, a new SOC write
route, RTC setting over actual CAN, or a universal 55…AA display frame format. The [capability matrix](../../mod/docs/firmware/uart-write-capabilities.md) defines the implemented MAINT access paths.

Useful future checks are accessory model identification,passive display captures,
thermistor measurements and tracing automatic address-chain wiring. Alarm/aerosol
contacts need the matching populated board and connection documentation first.
No hardware access,parameter modification or firmware update was performed.

A focused [internal-address-line audit](internal-address-chain.md) adds50 actual-Thumb
checks. Exact RJ45-to-GPIO wiring remains unproven. The original PDFs are in the [specifications directory](<../../vendor/docs/specs>).


## SH Energy catalogue: EMU1101 product family

[SH Energy BMS-Catalog.pdf](<../../vendor/docs/oem%20catalog/SH%20Energy%20BMS-Catalog.pdf>) has 25 PDF pages; its file metadata gives a creation/modification date of 2024-07-08, not a printed catalogue revision. SHA-256: `5ff105d56f292bb91c902f74a96dab440a28a1aca422896f75bef3407163fe74`. All references below use actual PDF pages, starting at 1.

Page 11 identifies **EMU1101** in the heading and explicitly shows a **10E/V16** board in the lower photograph:

- PCB silkscreen: **`EMU1101_PCBA-V16`**.
- Product sticker: **`1101-48100-10E-V16`**.
- Manufacturer silkscreen: **`SH ENERGY TECH`**.

These markings are part of the photograph, not searchable PDF text. They provide direct manufacturer-image evidence linking EMU1101, 10E and V16 for the pictured board. The photograph does not identify its firmware build, explain the shared firmware header's literal `10D`, establish every populated option across variants, or prove binary compatibility by itself.

| Catalogue evidence | Meaning for the examined BMS and limits |
|---|---|
| p.11 explicitly describes positive-side protection and a common charge/discharge port. p.6 describes a shared negative reference. | Direct manufacturer evidence for the advertised topology, beyond the manual's block drawing. It is not a circuit schematic, a component-level trace of the examined revision, or proof of electrical isolation when logically off. |
| pp.8/11 list 8–16 series cells and 100/150/200 A variants; p.11 highlights 15/16S. | Family ratings and supported product configurations. The 300×100×30 mm entry on p.8 spans EMU1101/EMU1102. These are catalogue dimensions, not a mounting drawing or permission to change cell count/wiring or upgrade a board's current rating through firmware. |
| pp.8/11 specify integrated 10 A current limiting with active/passive modes. | Primary-source corroboration of the nominal hardware limiter and both operating modes. It does not add an adjustable limiter-current parameter; P71 is duration. Active current limiting does not mean active cell balancing. |
| p.11 lists charging and standby balancing. | Consistent with Group6.bits0–2 and P64 in the [parameter reference](../firmware/configuration-parameters.md). No balancing-current value or active energy-transfer balancer is specified for EMU1101 here. |
| p.11 names RS485, CAN and RM485, parallel operation and automatic addressing. | Corroborates the two RS485 roles and optional address chain. It supplies no RJ45 pinout, UART numbering, electrical levels, GPIO mapping or proof that UART1 pairs are interconnected between packs. |
| p.11 lists optional 200 W heating, an adapter board exposing communication/reset/LED/address-switch functions, 4.3-inch LCD and Bluetooth. | Additional accessory/expansion evidence. It does not identify the installed display model, prove its 55…AA format, or establish that heating/adapter hardware is fitted. The 200 W figure is a catalogue option rating. |
| p.11 advertises sleep consumption below 10 µA; p.6 gives a generic 1 µA claim. | Conditions, supply point and fitted accessories are unspecified. These are not measurements and do not override the different sleep-current limits in H150/H200. |
| p.11 advertises more than 40 compatible inverter models. | Marketing scope, not 40 firmware protocol builders or a model-by-model certificate. OEM .13 has seven named selectable CAN families, with aliases/default fallbacks; see [CAN protocols](../protocols/can.md). |

The separate **ELPS48-ABG** controller on p.14 advertises a combined display, one-key bank switching, automatic group addressing, touchscreen, Bluetooth/Wi-Fi and app access to pack parameters. It is an accessory/controller lead for further investigation, not proof that an ordinary EMU1101 display or Bluetooth module proxies other packs. This page supplies no matching V16 firmware, connector pinout, protocol or confirmed compatibility path.

The catalogue's other product pages describe different hardware. EHVS500 relay channels, its BMU passive-balancing current, and active-balancer features elsewhere must not be transferred to EMU1101. The general AFE/harness, certification, power-saving and current-limiting claims on p.6 do not establish revision-specific wiring instructions, certification coverage or the exact firmware state machine.

The catalogue belongs under `vendor/docs/oem catalog/`: it is an original multi-product manufacturer source. The Seplos CAN specification belongs under `vendor/docs/protocol specs/`; its [firmware comparison](../protocols/can.md#manufacturer-can-specification-scope-and-differences) describes what applies to OEM .13.

## Mason230 Ah specification: configuration and firmware boundaries

The [Mason 280 Specification.pdf](<../../vendor/docs/specs/Mason%20280%20Specification.pdf>) has a **SEPLOS 51.2V 230AH** cover despite its filename. It contains 29 PDF pages; metadata gives 2023-03-13, not a printed document revision. SHA-256: `29c6ce1be61daca2a06a71e56573bb329f27e4ddb3ec4edbe5c6f8a59b4d9958`. All references here use actual PDF pages, starting at 1.

Its BMS tables list cell high-voltage warning 3.50 V (p.7), pack OVP 57.6 V (p.8), and a cycle threshold of 20% plus BMS nominal-capacity setting 200 Ah (p.14). The pack specifications give 230 Ah (p.6), so the BMS table value must not be presented as the pack rating or a universal firmware default.

Its limiter names map to Group6.Bit6 (“Active”, current≥10 A) and Bit7 (“Passive”, charge-overcurrent warning); P71 determines duration. The SOC, power and limiter implementation is defined in the [parameter reference](../firmware/configuration-parameters.md), [SOC reference](../firmware/soc-capacity-and-persistence.md), [power reference](../firmware/power-on-off.md) and [states](../firmware/states-and-triggers.md).

| Specification statement | OEM16.06.12/16.06.13 behavior |
|---|---|
| UVP keeps communication for one minute and shuts down. | Normal discharge inhibit comes first; UVP/empty without charging or pending activation asserts logical off after60 s. Supply shutdown has additional conditions. |
| Effective current ±1.0 A with0.7 A recovery. | Pack charging detection is+0.60/+0.50 A and discharge−0.50/−0.40 A, doubled with ambient warnings. These differ from system-aggregate thresholds. |
| Charger detection at port≥pack+0.5 V. | The immediate voltage path uses+1.00 V and its MOSFET condition; another path uses port≥pack−0.20 V with debounce. |
| UVP release at charge current≥1 A. | Current-status Bit7 at3.01 A takes the discharge-recovery path; otherwise P7/P17 recovery applies. |
| OVP release requires recovery voltage and SOC<96%. | OVP hysteresis and recharge waiting are separate; discharging>10 A for about10 s also invokes recovery. |
| CAN socket1/2/7/8 NC;4 CAN-L,5 CAN-H. | That table differs from the examined hardware and H150 pinout. Firmware alone does not establish physical pins. |
| RS485 pins4/5 internal communication (NC). | Automatic GPIO pulse addressing is a supported interpretation; exact physical mapping remains unproven. |
| Connection compensation positions9/13. | P83–P86 correct the selected cell measurement, corresponding to its preceding connector; this is not a different compensation algorithm. |

The CAN table on PDF p.16 assigns pin4=CAN-L and pin5=CAN-H, opposite to H150/H200. This is a documented variant discrepancy, not a replacement pinout for an examined 10E/V16 board. The quoted settings and wiring apply only within this manufacturer document's scope; the code comparisons above are bounded to OEM 16.06.12/16.06.13.
