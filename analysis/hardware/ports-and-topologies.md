# Ports, inverter protocols and bus ownership

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Updated 2026-10-26. This guide covers simultaneous inverter, monitor and service
connections for Seplos BMS 2.0/10E/V16 (EMU1101) packs. The reference is **OEM 16.06.13**, with current
patch alternatives **MAINT 1.5.3 and 1.6.3**. Older OEM differences are explicit.

**Practical rule:** An inverter on actual CAN leaves UART1 available to a monitor.
An inverter on UART1 leaves UART0 available only when no Seplos master polls UART0. Two
RJ45 sockets or extra transparent gateways do not create an independent bus.

Evidence labels: **code** means the identified firmware; **emulator** means
original Thumb instructions with synthetic inputs; **manufacturer** means an
explicitly documented arrangement. **Conditional** marks a technically possible
connection without a demonstrated inverter implementation. Neither a firmware
profile name nor a manual compatibility claim guarantees every inverter model.
This investigation used no devices. Earlier laboratory tests establish individual
communication paths, not new end-to-end tests of every topology with current images.

## 1. Physical ports and their protocols

| Label | Connection | OEM .13 application | Main restriction |
|---|---|---|---|
| **UART0** | UART0, RS485-1/RS485-2, two access points to the same pack bus | 19200 baud, 8N1; Seplos ASCII, PC write commands and intra-pack 0x5A polling | The polling Seplos master does not answer host requests here. |
| **UART1** | UART1, RS485 pair inside the CAN socket: 1/8=B, 2/7=A, 3/6=GND | 9600 baud, 8N1; individual-pack ASCII, Pylontech-style system ASCII and read-only Modbus RTU; MAINT adds addressed commands | One coordinated requester per segment. Reaching all packs requires their UART1 wires to be connected separately. |
| **CAN** | Other wires of that socket: 4=CAN-H, 5=CAN-L | Selected master CAN profile; 500 kbit/s except MUST at 100 kbit/s | Only address 0 transmits; almost all dynamic fields are aggregates, with some local/fixed exceptions. |
| **UART2** | UART2, local display/Bluetooth port | Binary 55…AA at 9600 baud; local display, parameters and CAN profile selection | No addressed slave proxy or established incoming power/reset command. |

OEM .13 dispatchers: UART0 `0x1132`, UART1 ASCII `0x2AF2`, UART1 Modbus `0x45AC`, UART2 `0x8288`,
CAN send selection `0xAEBA`. Selecting a CAN profile does not select a different
UART0/UART1 command set. CAN and UART1 can operate simultaneously on their separate wires,
provided the cable/breakout actually connects the intended contacts.

Pins 4/5 of the **UART0 sockets**, sometimes labelled internal communication, are
different from pins 4/5 of the **CAN socket**. They are candidates for the GPIO
address chain, not a documented bridge to UART1. Exact MCU wiring remains open.
See [internal address lines](internal-address-chain.md).

## 2. What protocol can the inverter use?

| Inverter connection/protocol | BMS behavior | Conditions and evidence |
|---|---|---|
| **CAN** | Address 0 transmits its selected CAN profile; no useful incoming CAN control path | Matching inverter battery profile, pins and bit rate. Pack-wide aggregates require master polling on UART0. |
| **UART1: system ASCII 60–63** | Master 0 only; .13 target alias **02 or 12, not 00** | Matching Pylontech-style system layout/addressing. Command 60 was introduced in 16.06.04. |
| **UART1: Modbus RTU** | Master 0 only, ID 1, FC03/04, fixed supported register starts/counts | Inverter must match the actual register map/response format. Some blocks use a nonstandard 16-bit byte count. No general Modbus write access. |
| **UART0: Seplos ASCII 42/44 etc.** | Individual-pack responses; no 60–63 system commands in .13 | **Conditional for an inverter:** matching pack-bus baud, Seplos payloads and any necessary aggregation. No concrete direct-UART0 inverter has been established here. |
| **UART1: individual ASCII 42/44/51** | Each addressed pack returns its own data | Practical for a PC/monitor. Conditional for an inverter that polls every pack and aggregates the results itself. |

Actual CAN profiles in the OEM .13 image:

| Number | Image profile name | Bit rate |
|---|---|---|
| 1 | PNG_DYE_Luxp_TBB; Pylontech-style family, Deye/Luxpower/TBB according to its name | 500 kbit/s |
| 2 | Growatt_SPF_SPH | 500 kbit/s |
| 3 | Victron | 500 kbit/s |
| 4 | SMA_SOFAR | 500 kbit/s |
| 5 | GINLONG | 500 kbit/s |
| 6 | Studer | 500 kbit/s |
| 7 | MUST, 29-bit IDs; from 16.06.11 | 100 kbit/s |

Names are not a model-by-model compatibility certificate. The 100A manual also
names Pylontech, Growatt and SRNE for RS485; that does not establish direct use
of today's UART0 bus. The expressly documented inverter arrangement uses
**CAN/RM485 on the master**. Similar ASCII framing does not prove general
Pylontech compatibility of the Seplos 42/44 payloads. No primary Pylontech
protocol specification was available in the local source collection.
See [CAN](../protocols/can.md), [system ASCII](../protocols/pylontech-rs485.md) and
[Modbus maps](../protocols/modbus-rtu.md).

**What UART0 actually answers in OEM .13:** `42/44` return pack data, `51` device
info and `4F` an empty success reply (RTN00). It also supports
`45/47/49/4B/4D/4E/5A/A0–A6/AA/AB`; `60–63` return RTN04. UART0 has no Modbus RTU
receiver in .13. Evidence: dispatcher `0x1132` and retained native UART0 probes.
The older .04 exception is described in section8.

## 3. Master role, DIP switches and aggregation

With normal DIP addressing, **Group7.bit5=0**:

```text
local address == 0 AND effective slave count > 0:
    UART0 master branch: poll slaves with 0x5A; no host dispatcher
otherwise:
    UART0 host dispatcher available
```

**Code, .13:** branch `0x6264–0x628A`. A pause between polling rounds is not a
host-response window. DIP1–4 give the address; DIP5–8 give the slave count.
For address≠0, `0x21CA–0x21D2` clears the slave count. The one-second sequence
rereads these values. No restart is required for a normal DIP change, but wait
for the change to take effect and for bus silence before sending host requests.

- **Address 0, zero slaves:** UART0 can answer a host while CAN/UART1 system protocols
  remain available. Their aggregate contains only that pack.
- **Packs 1…N without pack 0:** each answers on UART0; no BMS builds a CAN/UART1 system
  aggregate. The external PC must aggregate individual readings.
- **One physical board, configured slaves:** it still takes the master branch
  and polls missing packs. Physical count and configured role differ.
- **Automatic addressing, Group7.bit5=1:** GPIO pulses can determine the address
  and slave count instead of DIP; bit 6 can turn auto-address 0 into 1. DIP5–8 OFF
  then does not establish a free UART0 bus. MAINT maintenance start is blocked.

**Code/emulator, .13:** `0x944C` clears the old online mask for pack 0/zero slaves;
`0x12E2` inserts the local pack; `0x99BA` computes a one-pack aggregate. Other
physically connected packs are not counted. The UART1/CAN master enable is cleared
for nonzero local addresses at `0x9A44–0x9A52`.

## 4. Manufacturer RS485 and CAN DIP arrangements

The setup sheets are **DIP matrices**, not complete wiring diagrams: The [Seplos CANBUS V1.0 comparison](../protocols/can.md#manufacturer-can-specification-scope-and-differences) supplies another master/slave DIP table with the expected slave-count encoding; it does not establish a UART1 cable chain.

- [RS485 DIP ADDRESS SETUP](<../../vendor/docs/address%20setup/RS485%20DIP%20address%20setup.pdf>), p.1:
  2P–15P use addresses 1…N with DIP5–8 OFF. **The 1P exception is all OFF/address0.**
- [CAN DIP ADDRESS SETUP](<../../vendor/docs/address%20setup/CAN%20DIP%20address%20setup.pdf>), p.1:
  master 0 with its slave count, then slaves 1…N−1, up to 16P.
- [Vendor ASCII protocol](<../../vendor/docs/protocol%20specs/Seplos%20BMS%20Modbus-ASCII%20Protocol%20RS485%20V2.0%20%282019-10-15%29.pdf>),
  PDF p.3, §1.2/1.3 explicitly shows FSU/PC polling BMS 1…15 without a Seplos
  DIP 0 master. This establishes the external-PC/FSU topology.
- [100A manual](<../../vendor/docs/manuals/Seplos%20BMS%20V16%20100A%20Manual.pdf>), PDF p.7, §2.11:
  PC at the RS485 chain or master connected to the inverter through CAN/RM485;
  pp.30–32 give pins and the UART0 chain. Contents and body section numbers differ.
- [UART1 RS485 wiring](<../../vendor/docs/wiring%20diagram/Seplos%20BMS%20UART1%20RS485%20Wiring%20Diagram.pdf>), p.1:
  UART1 socket to USB-RS485 adapter and PC, not evidence of a preconnected UART1 chain.

A PC/FSU polling an UART0 chain without a Seplos master is an intended arrangement.
A directly polling UART0 inverter remains conditional on its concrete protocol.

## 5. Connection cases and monitor access

“Occupied” means another requester must not independently initiate traffic;
it does not mean continuous utilization or an electrical lock. The DIP assumptions
below require automatic addressing to be off.

| Case | Inverter/external requester | UART0 owner | UART1 owner | Active monitor | UART0 maintenance/flash | Assessment |
|---|---|---|---|---|---|---|
| 1a: single pack 0, zero slaves | Inverter via matching CAN profile | None | None | UART0 or UART1 | UART0 available | Practical standard; OEM UART1 reads, MAINT extends it. |
| 1b: single pack | Inverter on UART0, Seplos ASCII and matching baud | Inverter | None | UART1 | Pause inverter requests | Conditional; no concrete inverter established. |
| 1c: single pack 0, zero slaves | Inverter on UART1, system ASCII 02/12 or Modbus ID 1 | None | Inverter | UART0 | UART0 available | Manufacturer CAN/RM485 route; matching inverter protocol required. |
| 2a: Seplos-managed chain | Master0 polls UART0; inverter uses CAN | Seplos master | None | UART1 wired to all targets | Stop master polling | Practical standard for inverter plus monitor. |
| 2b-PC: addresses 1…N, zero slave counts | PC/FSU reads individual packs on UART0 | PC/FSU | None | Same coordinated requester or separate UART1 | Pause/coordinate external queries | Manufacturer-established; PC aggregates. |
| 2b-inverter: same DIP arrangement | Inverter reads individual packs on UART0 | Inverter | None | UART1 | Pause inverter | Conditional; it must support payloads, baud and aggregation. |
| 2c: no UART0 polling | Inverter reads individual UART1 42/44/51 data | None | Inverter | UART0 | UART0 available | Practical for a PC; no concrete inverter established. System 60–63/Modbus do not replace individual polling. |
| 2d: Seplos-managed chain with RS485 inverter | Master polls UART0; inverter uses UART1 system ASCII or Modbus | Seplos master | Inverter | No independent free UART0/UART1 bus | Pause inverter UART1 and stop master UART0 | Regular inverter route; extra transparent gateways do not free a bus. |
| PC only, no inverter | One PC reads UART0 or UART1 | PC if using UART0 | PC if using UART1 | Same requester or other free bus | Coordinate any existing UART0 polling | Practical; choose DIP role/aggregation intentionally. |

For 2a/2b, one UART1 monitor reaches all targets only with their **UART1 A/B wires actually
connected**. The UART0 chain does not provide that connection. In 2b/2c, a pack 0
without UART0 slaves serves only its own aggregate; without pack 0 there is no UART1 system
master. In 2d, passive listening or a local UART2 connection may still be useful.
Passive listening yields existing traffic, not complete parameter access; the UART0
master does not publish its own data as a slave 0x5A reply. A deliberately engineered
bus mediator could coordinate requests; a transparent TCP gateway is not automatically
such an arbiter.

## 6. Multiple responders and separate systems

**Code/emulator, .13:** two independent requesters can collide. A **single**
requester can also cause multiple answers:

- UART0/UART1 42/44/51 accept FF. It is not a safe multi-pack discovery query. UART0 replies
  carry each pack's own address; UART1 from 16.06.12 echoes the requested address.
- UART1 4F at 02 can reach **master 0 and pack 2** from 16.06.12. Alias 12 can similarly
  conflict with auto-address 18. An isolated-master version probe is possible;
  on a shared UART1 bus it is ambiguous.
- UART1 60–63 at 02/12 are master-only; pack 2 stays silent. Modbus ID 1 is master-only too.
- MAINT parameter/serial queries and 64/03/04 use the individual target address;
  do not replace them with FF scans.

A 200 ms UART1 receive gap is not arbitration. Each physical RS485 segment needs one
requester or explicitly coordinated access. RS485-1 and RS485-2 are not separate
channels for competing hosts.

Independent Seplos masters must not share UART0. On shared UART1, duplicated pack addresses,
system aliases and Modbus ID 1 conflict. Shared CAN IDs can carry different systems'
data. Keep independently aggregated systems in separate communication domains.
A PC may group uniquely addressed slaves in software on one shared bus; that
remains one communication domain, including the effects of broadcasts.

## 7. Maintenance, flashing and permanently attached gateways

Flashing and the full OEM PC command set use **UART0**: device/serial-string writes,
calibration, history, 49 capacity commands and forced heating. UART2 supports selected
local parameter functions. OEM UART1 reads; MAINT extends it as described in the
[capability matrix](../../mod/docs/firmware/uart-write-capabilities.md). Patching only the master does
not extend OEM slaves' UART1 commands.

Current MAINT 1.5.3/1.6.3 also support UART0 64/02, marker clear, 64/03 and 64/04.
Maintenance start remains **UART1 to master 0**, with its permission and automatic
addressing disabled. It stops only Seplos polling, not an external PC/inverter.
UART1 64/02/start/stop remain master 0 services; 03/04 work per target. A free-UART0 single
pack or externally polled UART0 chain needs no maintenance start.

Before active UART0 service, pause external requesters and stop any Seplos master
using its marker or DIP5–8 OFF. Wait for state adoption and bus silence. Packs
remain electrically connected while CAN/UART1 system values cease representing the
whole chain. CCL can retain old values during its ramp (`0x995C–0x9986`). Plan
the window without requested battery power. When master polling resumes, OEM
on/off broadcasts to slaves apply again; effective slave count 0 also disables
the broadcast sender `0x13F6`.

A permanently attached UART0 gateway is usable if:

- It transfers transparent bytes at the application's pack-bus baud, with no
  unsolicited heartbeat, Modbus polls or receive/transmit loop.
- Its transmitter stays silent during Seplos polling; host operations are
  coordinated through maintenance or a single requester.
- Termination is at actual line ends, accounting for extra built-in bias/terminators.
- Direction control releases the bus after sending and during reset/power loss.
  This is an adapter property, not a guarantee from the BMS firmware.
- Reference potential and any required galvanic isolation suit the installation.
  Transmit silence alone does not prove electrical compatibility.

<a id="8-application-baud-rates-and-the-historical-r-exception"></a>

## 8. Application baud rates and the historical UART0 exception

These are **code findings for the seven available OEM images**. UART0 always uses
call 015E and baud construction 0138–013C: `75<<7=9600` in 16.04.06, otherwise `75<<8=19200`.
Addresses in the table are hexadecimal.

| OEM | UART0 application | UART1 application | UART1 init | UART1 baud construction / UART call |
|---|---|---|---|---|
| 16.04.06 | 9600 | 9600 | 2974 | 29D0–29D4 /29F6 |
| 16.06.03 | 19200 | 9600 | 22A4 | 2300–2304 /2326 |
| 16.06.04 | 19200 | 9600 | 22A4 | 2300–2304 /2326 |
| 16.06.05 | 19200 | 9600 | 22A4 | 2300–2304 /2326 |
| 16.06.11 | 19200 | 9600 | 2330 | 238C–2390 /23B2 |
| 16.06.12 | 19200 | 9600 | 2330 | 238C–2390 /23B2 |
| 16.06.13 | 19200 | 9600 | 23DC | 2438–243C /245E |

No configurable UART0/UART1 baud parameter was found in these initializers; the driver
reads the fixed config structure, e.g. .13 `0xB9AC`. 16.06.03 is the first available
19200 build; unknown intermediate builds are not dated by this finding.

Mixed UART0 application baud rates do not form a working pack chain. Actual error
frames/collisions of a mixed physical bus were not measured. UART1 stays at 9600,
so supported individual UART1 queries can still work despite that UART0 difference.
Matching baud alone does not establish inverter compatibility.

**16.04.06 only:** a separate FC03/Modbus-like CRC read path exists on UART0 alongside
ASCII (`0x52FE→0x1AEE→0x19C6`). Native replay:

```text
030300010001D428 → 030300020000E5E8
030300010001D429 → no response
```

The valid response uses a **two-byte count 0002**, not the normal Modbus answer
format. This UART0 path is absent from 16.06.03; the same requests stay silent.
Today's UART1 Modbus register map must not be applied to it.

**Bootloader:** the baud of the bootloader paired with the available 16.04.06
9600 image remains unknown. The app does not contain the bootloader; existing
19200 handshakes used another laboratory build. Neither app baud nor the
`RS485Y19200N9600` header alone establishes bootloader baud.

## 9. Evidence and remaining limits

Original-image identities, initializer and dispatcher excerpts,175 protocol/address replays, single-pack aggregate counterexamples, manufacturer images and legacy-UART0 probe results are retained under the ignored `local/research/topologies/evidence/Anschluesse-Topologien-2026-10-26/` directory.
No firmware image was changed. Remaining questions are actual inverter tests for
1b/2b-inverter/2c, primary Pylontech payload comparison, physical UART1 wiring per board,
exact internal-UART0 contact mapping and the 16.04.06 bootloader baud.
