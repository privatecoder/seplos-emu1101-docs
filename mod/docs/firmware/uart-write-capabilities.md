# UART write capabilities: Original .13, MAINT 1.5.3 and MAINT 1.6.3

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101). These tables describe the named OEM 16.06.13
and MAINT images only. Determine each target's capabilities with 64/03;
command 51 reports the OEM base family and cannot identify the patch release.
Unknown images require separate analysis. The catalogue verifies current input
hashes, MNT04 metadata/template and build-ID digests against public release
JSONs without opening ports or rerunning native emulation.

| Firmware | Build ID | MNT04 image flags | .ehex file SHA-256 |
|---|---|---|---|
| Original16.06.13 | — | — | `0ea75c9834cf19789a58f58db8cde1a2bbd722a8f5a7bde7f00106f59b91ccf6` |
| 1.5.3 | `2b89286ed6c14604` | `0x3A` | `dee768334ad4227999b41efd0c4232c0b5c9f323c973cd392b5651a1b5f29325` |
| 1.6.3 | `baa01ecd5af4eb28` | `0xFE` | `99ea2cc5496358ec127300b55a4ca718acb1c4f6ee16f13edbe346f7aa4db062` |

SHA-256, where listed, covers the complete .ehex file. The OEM image has no
MAINT build ID or MNT04 reply. Published hashes bind the actual release files;
a different hard-stop build option produces a different image.

## Ports and conditions

| Port | Transport | Access |
|---|---|---|
| UART0 | ASCII, 19200 8N1 | Addressed local pack; pause master polling before host access to master or slaves. |
| UART1 | ASCII and binary 55…AA, 9600 8N1 | MAINT addressed operations can coexist with UART0 master polling. |
| UART2 | Binary 55…AA, 9600 8N1 | Requires Group7.Bit3=1. Acts on the physically connected board; received address is not checked as the target. |

A separately wired UART1 bus is required to reach all packs through UART1; a UART0
daisy-chain alone is insufficient. Coordinate external inverter/PC traffic:
only one requester should own a given bus.
[Ports and topologies](../../../analysis/hardware/ports-and-topologies.md)
shows which bus remains free for each inverter protocol. The manufacturer
specifies PC/FSU banks without a Seplos master; direct UART0 inverter use still
requires matching baud rate and Seplos payload support.
Commands and INFO bytes are hexadecimal; parameter, switch and pack numbers
are decimal. Pack 11 uses ASCII address 0B. Normal DIP addresses are 0–15;
MAINT addressed operations accept 0–21. These are local capabilities, without
a master proxy. A dash means no implemented route.

**[W]** Group0.Bit0=1 permits A1 writes through UART1.

**[P]** Requires image flag bit 1 and the release-specific Group0.Bit3 polarity
listed below. This permission covers power, restart and RTC writes through UART1;
UART0 uses its original path, and UART1 RTC reads need no power permission.

**[M]** Maintenance start requires master address 0, Group0.Bit2=1,
Group7.Bit5=0, a valid marker state and exact token 01 C3 5A.

**[X]** Extended off requires the release-specific Group0.Bit4 setting. A
stored individual lock remains active when this feature is disabled; addressed
on may release it independently of that setting.

## Complete write and action matrix

| Value / action | Command | Original .13 | MAINT1.5.3 | MAINT1.6.3 |
|---|---|---|---|---|
| All 87 configuration parameters P0–P86 | A1, whole block | UART0, UART2 | UART0, UART1[W], UART2 | UART0, UART1[W], UART2 |
| Function switches Group0–7, including display format | A1; exceptions below | UART0, UART2 | UART0, UART1[W], UART2 | UART0, UART1[W], UART2; bit 5 protected |
| Device name, 10 bytes | ASCII A1 | UART0 | UART0 | UART0 |
| Battery serial number / String1, up to 30 bytes | ASCII A3 | UART0 | UART0 | UART0 |
| BMS serial number / String2, up to 30 bytes | ASCII A5 | UART0 | UART0 | UART0 |
| CAN inverter protocol | UART0: ASCII A6; UART2: binary 63 | UART0, UART2 | UART0, UART2 | UART0, UART2 |
| Set learned full capacity and maximum charge | ASCII 49/3A | UART0 | UART0 | UART0 |
| Current remaining charge / SOC starting value | ASCII 49/3B | UART0 | UART0 | UART0 |
| Calibrate current zero | ASCII A0/00 | UART0 | UART0 | UART0 |
| Calibrate current gain | ASCII A0/01 | UART0 | UART0 | UART0 |
| Calibrate cell/port voltage gains | ASCII A0/02 | UART0 | UART0 | UART0 |
| RTC time / date | ASCII 4E | UART0 | UART0, UART1[P] | UART0, UART1[P] |
| Logical on/off | ASCII 45/04 | UART0 | UART0, UART1[P] | UART0, UART1[P] |
| Set or release the stored individual pack lock | Addressed ASCII 45/04 | — | — | UART0, UART1[P]; [X] |
| Local restart | ASCII 45/06 | UART0 | UART0, UART1[P] | UART0, UART1[P]; SOC checkpoint before reset, RTN08 on failure |
| Force heater / set timer to 3600 s or 0 | ASCII 45/03 | UART0 | UART0 | UART0 |
| Clear history, cycles and charge/discharge energy | ASCII 45/05 | UART0 | UART0 | UART0 |
| Start maintenance: pause master polling | ASCII 64 / 01 C3 5A | — | UART1[M], master 0 only | UART1[M], master 0 only |
| Clear maintenance marker / stop maintenance | ASCII 64 / 00 C3 5A | — | UART0: addressed pack; UART1: master 0 only | UART0: addressed pack; UART1: master 0 only |
| Replace firmware | UART0 bootloader, separate flash procedure | UART0 | UART0 | UART0 |
| Send six undecoded bytes to the display/dongle | ASCII AB → UART2-Tunnel | UART0 → UART2 | UART0 → UART2 | UART0 → UART2 |
| Save SOC before a planned restart | Automatic before addressed ASCII45/06 | — | — | UART0, UART1[P]; no separate write permission |
| Configure hard stop during recharge waiting | A1,Group0.Bits6/7 | — | — | UART0, UART1[W], UART2; write together |

A1 always transmits a complete valid parameter block. UART0 uses ASCII with 169
INFO bytes, including the device name. UART1/UART2 use binary with 158 DATA bytes,
without the name. Individual P values are not directly writable registers.

## Additional read and service operations

| Read operation | Command | Original .13 | MAINT1.5.3 | MAINT1.6.3 |
|---|---|---|---|---|
| Read parameters, switches and device name | 47 | UART0: ASCII; UART2: binary; UART1: — | UART0: ASCII; UART1/UART2: binary | UART0: ASCII; UART1/UART2: binary |
| Read battery serial number / String1 | A2 | UART0: ASCII; UART1/UART2: — | UART0: ASCII; UART1: binary; UART2: — | UART0: ASCII; UART1: binary; UART2: — |
| Read BMS serial number / String2 | A4 | UART0: ASCII; UART1/UART2: — | UART0: ASCII; UART1: binary; UART2: — | UART0: ASCII; UART1: binary; UART2: — |
| Read clock time / date | ASCII 4D | UART0; UART1/UART2: — | UART0, UART1; no power permission required | UART0, UART1; no power permission required |
| Read base device information | ASCII 51 | UART0, UART1; UART2: — | UART0, UART1; does not replace patch identity | UART0, UART1; does not replace patch identity |
| Read firmware identity / version / build / image flags | ASCII 64 / 03 | — | UART0, UART1: each addressed pack; UART2: — | UART0, UART1: each addressed pack; UART2: — |
| Read maintenance marker and effective slave count | ASCII 64 / 02 | — | UART0: addressed pack; UART1: master 0 only; UART2: — | UART0: addressed pack; UART1: master 0 only; UART2: — |
| Read extended storage diagnostics | ASCII64/04 | — | UART0, UART1; addressed pack, no permission required | UART0, UART1; addressed pack, no permission required |
| Read hard-stop selection and build default | 64/03,for configuration also read 47 | — | 64/03 image flag 0: fixed in image | 64/03 flag 80/bit 0 +47 Group0.Bits6/7 |

This complements the action matrix rather than replacing the telemetry
catalogue. UART1 47/A2/A4 and implemented 64/03/04 reads need no A1 permission.
UART2 A2/A3 are outbound power notifications, not serial-number read/write commands.

UART0 64/02 and UART0 64/00C35A address the local pack including slaves, independently
of Group0.Bit0/2/3. Foreign addresses and FF stay silent. Local UART0 start is
unsupported and returns RTN05. UART1 status/start/stop remain master-only; UART1 info
and implemented diagnostics support addressed slaves. Stop remains available
when start permission is disabled.

Clearing marker FFFFFFFF acknowledges without erase; 00000000 uses erase and
readback. Other values are not erased. Success returns RTN00 with five INFO
bytes: little-endian marker and currently effective slave count, LENGTH 600A.
Detected erase/readback/token errors return RTN05 with no INFO. An ACK does
not prove that polling has already finished changing. Clearing the marker
does not reset, alter parameters or release an individual pack lock.

UART0/UART1 64/03 returns identical MNT04 information for a given pack: 19 decoded
bytes, LENGTH 8026. Offsets 0–2 MNT, 3 format, 4–6 OEM base, 7–9 patch version,
10–17 build ID, 18 image flags. It contains no runtime marker or state fields.
Flag 0x10 identifies UART0 marker/info support.

## Version-specific rules

Both versions permit UART1 Power/RTC with Group0.Bit3=1. Image flag 0x08 identifies
positive polarity; Group0 FF therefore allows UART1 Power/RTC in both versions.
Extended off also requires image flag 0x04. Only 1.6.3 enables it with
bit 4=1; bit 5=0 indicates an individual lock. Disabling bit 4 does not release an existing lock. In 1.5.3 bits 4/5 remain
reserved. No new parameter is introduced by 1.5.3.

Both support UART0/UART1 64/04: freely readable addressed 0–21, foreign/FF silent,
format 01, ten INFO bytes, LENGTH B014. These check parameter/SOC shape, CRC
and differences without repair. 1.5.3 returns lock bytes 7/8=FF, byte 9=00
(no lock cache); this is unavailable state, not an unlocked-state claim.
Only 1.6.3 saves/verifies both original SOC copies before addressed UART0/UART1 45/06.
RTN08 prevents reset on storage/verification failure; FF does not checkpoint
or reset. UART1 still needs [P]. 1.5.3 retains the OEM UART0 45 broadcast paths.
MNT04 patch bytes are 01 05 03 / 01 06 03. Diagnostic image flag 0x20 is present
in both; checkpoint flag 0x40 only in 1.6.3. Published image flags are 3A / FE.
A static hard-stop 1.5.3 build uses 3B instead of 3A.

1.6.3 protects bit 5 even during malformed UART0/UART2 imports. Addressed UART0/UART1 on/off
returns RTN08 with LENGTH0000 on a persistence failure; matching RAM bit 5
does not turn it into success. Check uncertain outcomes with fresh reads
rather than automatically repeating writes.

### Configurable hard stop in MAINT 1.6.3

Image flag 0x80 marks configurability. Image flag bit 0 is the build default
for legacy parameters; explicit parameters take precedence. The published FE
image defaults to soft stop. Building with --hard-stop enable gives FF.

| Group0 & C0 hex | Meaning |
|---|---|
| 00 | Explicit soft stop |
| 40 | Explicit hard stop during recharge waiting |
| 80 or C0 | Follow 64/03 image flag bit 0 |

Bit 6 selects hard stop when bit 7=0. Write both bits together with
`new=(fresh_group0 & 0x3f) | (0x40 if enabled else 0)` to preserve lower bits.
Read Group0 immediately before composing the complete A1 block.
UART0/UART1/UART2 A1 stores the choice; UART1 needs [W], without a separate power permission.
Legacy FF follows the build default and stays soft stop in FE. Bit 7=0 alone
does not prove record age; old 00/40 values count as explicit choices and
must be assessed before adoption. No automatic NVM migration occurs.

This extends charge prohibition to intermittent recharge waiting. Original
Group5.Bit1 recharge logic must be enabled and Event6.Bit1 must actually occur.
This is neither immediate on/off nor an individual pack lock. Own discharge
above 10 A for about 10 s may release the charge path as before. Pack locks
win. The native charge-inhibit mask changes from 0x71 to 0x73, retaining
OVP/temperature priorities. It does not remove DCL. Configuration takes effect
live. 64/03 is static: read 47/Group0 for active configuration.


## Group0 rules

| Field | Original .13 | MAINT1.5.3 | MAINT1.6.3 | Write route / exception |
|---|---|---|---|---|
| Group0.Bit0 | Reserved, no OEM function | 1 = allow writes over UART1 | 1 = allow writes over UART1 | UART0/UART2; UART1[W] may disable itself 1→0. Re-enable only through UART0/UART2. |
| Group0.Bit1 | 1 = enable temperature sensor plausibility check | 1 = enable temperature sensor plausibility check | same as 1.5.3 | UART0, UART1[W], UART2 |
| Group0.Bit2 | Reserved, no OEM function | 1 = allow maintenance start over UART1 | same as 1.5.3 | UART0/UART2 only; a change through UART1-A1 returns E3 and rejects the entire block. |
| Group0.Bit3 | Reserved, no OEM function | **1 = allow Power/RTC over UART1**, 0 = blocked | **1 = allow Power/RTC over UART1**, 0 = blocked | UART0/UART2 only; a change through UART1-A1 returns E3 and rejects the entire block. |
| Group0.Bit4 | Reserved, no OEM function | Reserved, no function | **1 = enable extended off**, 0 = disabled | UART0, UART1[W], UART2; Disabling does not release an existing lock. |
| Group0.Bit5 | Reserved, no OEM function | Reserved, no function | **0 = individual pack lock active**, 1 = clear | 1.5.3: writable through UART0/UART1[W]/UART2. 1.6.3: status only; change only through addressed 45 on/off over UART0/UART1[P]. |
| Group0.Bit6 | Reserved, no OEM function | Reserved, no function | When bit 7=0: 1 hard stop, 0 soft stop | UART0, UART1[W], UART2; set both bits together. |
| Group0.Bit7 | Reserved, no OEM function | Reserved, no function | 0 explicit choice, 1 build default | Edit together with bit 6; legacy FF follows the build default. |

No automatic parameter polarity conversion or NVM migration is performed.
Interpret flags and bits against the exact image profile. An enable bit does
not itself create the associated alarm or operating state.

## Effects, persistence and error limits

P59/A1 changes the saved boot fallback, not current remaining charge. UART0 49/3B
sets remaining charge without changing P59; UART0 49/3A sets learned full capacity
and Qmax without changing P58. Neither immediately saves SOC block 6. There is
no separate host SOC-save command; checkpoint support is specified above.

If P58 differs from learned full capacity by at least 10 Ah, OEM A1 also
changes learned full capacity and Qmax to P58 and saves block 6, even for a
switch-only import. Otherwise A1 saves parameters, not current SOC.

UART0/UART2 apply switches, and UART0 applies the name, before parameter validation;
rejection may therefore leave RAM changes. UART1 validates before committing;
protected-bit changes reject the whole block with E3. ACK or active RAM
readback alone does not prove every physical NVM write completed.

The original SOC loader prefers valid primary data without an age comparison,
otherwise repairs from valid backup; no valid copy uses the P59/P58 fallback.
Conservative pack-lock recovery in supported cutoff releases is not a general
parameter transaction journal.

Soft off may be reversed by charging. Extended cutoff can inhibit charge MOSFET,
limiter, discharge MOSFET, precharge and charge wakeup, and exclude the charging
contribution. Applying its additional aggregate CCL limit also requires the
master to run the matching cutoff release. Off is not galvanic isolation;
on does not bypass real protection alarms.

Addressed master power retains the OEM slave broadcast; that broadcast does
not set or release individual slave locks. Control slaves locally. Restart is
local and has no ACK. UART1 45 supports types 4 and 6/00, not heater/history types
3/5. Clearing history resets cycles and energy, rather than saving SOC.

UART0 RTC writes retain the original calendar validation limits. UART1 validates years
2000–2099, date and time. UART2 64 is an inert stub, not an RTC or maintenance command.
CAN protocol resides in block 4, outside A1/P0–P86. UART0 A6/UART2 63 accept 1–20;
only 1–7 have names and 8–20 select protocol 1. Changing to/from 7 reinitializes
CAN. UART1 implements neither A6 nor binary 63.

UART1 restart does not transport firmware; flashing remains on UART0. UART0 AB relays six
undecoded bytes to UART2 and waits without timeout. UART2 AA/AB change a volatile relay
state, without a proven substitute for other configuration commands.

Allow UART1 200 ms idle since the last received byte before the next request.
New bytes are discarded while a completed UART1 receive buffer is occupied.
UART0/UART2 retain OEM overwrite behavior. UART1 is not parallel access to the same buffer.
See the [receive-gap analysis](../../../analysis/protocols/uart1-receive-gap-and-buffer-ownership.md).

## All 87 A1 parameters

The listed MAINT profiles use UART0, UART1[W], UART2; OEM .13 uses UART0 and UART2. Transfer the complete
valid block. Raw units differ from UI units; validation can couple fields.
P82 can be stored but has no reader in the analyzed base code. Parameter
relationships are described in the
[configuration reference](../../../analysis/firmware/configuration-parameters.md).

| Index | Value | Raw unit | OEM .13 RAM |
|---|---|---|---|
| P0 | Cell: high-voltage warning | mV | `0x20001300` |
| P1 | Cell: high-voltage warning recovery | mV | `0x20001302` |
| P2 | Cell: low-voltage warning | mV | `0x20001304` |
| P3 | Cell: low-voltage warning recovery | mV | `0x20001306` |
| P4 | Cell: overvoltage protection | mV | `0x20001308` |
| P5 | Cell: overvoltage protection recovery | mV | `0x2000130a` |
| P6 | Cell: undervoltage protection | mV | `0x2000130c` |
| P7 | Cell: undervoltage protection recovery | mV | `0x2000130e` |
| P8 | Balancing: start voltage | mV | `0x20001310` |
| P9 | Charge inhibition below cell voltage | mV | `0x20001312` |
| P10 | Pack: high-voltage warning | 0.01 V | `0x20001314` |
| P11 | Pack: high-voltage warning recovery | 0.01 V | `0x20001316` |
| P12 | Pack: low-voltage warning | 0.01 V | `0x20001318` |
| P13 | Pack: low-voltage warning recovery | 0.01 V | `0x2000131a` |
| P14 | Pack: overvoltage protection / basis for CVL | 0.01 V | `0x2000131c` |
| P15 | Pack: overvoltage protection recovery | 0.01 V | `0x2000131e` |
| P16 | Pack: undervoltage protection | 0.01 V | `0x20001320` |
| P17 | Pack: undervoltage protection recovery | 0.01 V | `0x20001322` |
| P18 | Charger: overvoltage protection | 0.01 V | `0x20001324` |
| P19 | Charger: overvoltage protection recovery | 0.01 V | `0x20001326` |
| P20 | Charge: high-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x20001328` |
| P21 | Charge: high-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000132a` |
| P22 | Charge: low-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x2000132c` |
| P23 | Charge: low-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000132e` |
| P24 | Charge: high-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001330` |
| P25 | Charge: high-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001332` |
| P26 | Charge: low-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001334` |
| P27 | Charge: low-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001336` |
| P28 | Discharge: high-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x20001338` |
| P29 | Discharge: high-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000133a` |
| P30 | Discharge: low-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x2000133c` |
| P31 | Discharge: low-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000133e` |
| P32 | Discharge: high-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001340` |
| P33 | Discharge: high-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001342` |
| P34 | Discharge: low-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001344` |
| P35 | Discharge: low-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001346` |
| P36 | Cell heating on | 0.1 K; °C = (raw−2731)/10 | `0x20001348` |
| P37 | Cell heating off | 0.1 K; °C = (raw−2731)/10 | `0x2000134a` |
| P38 | Ambient: high-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x2000134c` |
| P39 | Ambient: high-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000134e` |
| P40 | Ambient: low-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x20001350` |
| P41 | Ambient: low-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001352` |
| P42 | Ambient: high-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001354` |
| P43 | Ambient: high-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001356` |
| P44 | Ambient: low-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001358` |
| P45 | Ambient: low-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000135a` |
| P46 | Power stage: high-temperature warning | 0.1 K; °C = (raw−2731)/10 | `0x2000135c` |
| P47 | Power stage: high-temperature warning recovery | 0.1 K; °C = (raw−2731)/10 | `0x2000135e` |
| P48 | Power stage: high-temperature protection | 0.1 K; °C = (raw−2731)/10 | `0x20001360` |
| P49 | Power stage: high-temperature protection recovery | 0.1 K; °C = (raw−2731)/10 | `0x20001362` |
| P50 | Charge overcurrent warning / basis for CCL | 0.01 A; P52/53/55/56 signed | `0x20001364` |
| P51 | Charge overcurrent warning recovery | 0.01 A; P52/53/55/56 signed | `0x20001366` |
| P52 | Discharge overcurrent warning / basis for DCL | 0.01 A; P52/53/55/56 signed | `0x20001368` |
| P53 | Discharge overcurrent warning recovery | 0.01 A; P52/53/55/56 signed | `0x2000136a` |
| P54 | Charge overcurrent protection | 0.01 A; P52/53/55/56 signed | `0x2000136c` |
| P55 | Discharge overcurrent protection | 0.01 A; P52/53/55/56 signed | `0x2000136e` |
| P56 | Short-duration overcurrent protection | 0.01 A; P52/53/55/56 signed | `0x20001370` |
| P57 | Precharge / soft start: maximum duration | ms | `0x20001372` |
| P58 | Nominal capacity P58 | 0.01 Ah | `0x20001374` |
| P59 | Remaining capacity P59: boot fallback | 0.01 Ah | `0x20001376` |
| P60 | Cell difference fault | 10 mV | `0x200013f0` |
| P61 | Cell difference fault recovery | 10 mV | `0x200013f1` |
| P62 | Balancing: start spread | mV | `0x200013f2` |
| P63 | Balancing: per-cell difference from minimum | mV | `0x200013f3` |
| P64 | Idle balancing: time limit | h | `0x200013f4` |
| P65 | Cells in series | count | `0x200013f5` |
| P66 | Charge overcurrent protection: delay | s | `0x200013f6` |
| P67 | Discharge overcurrent protection: delay | s | `0x200013f7` |
| P68 | Short-duration overcurrent: delay | ms | `0x200013f8` |
| P69 | Overcurrent: release after | s | `0x200013f9` |
| P70 | Short-duration overcurrent/short-circuit lock after event count | count | `0x200013fa` |
| P71 | Current limiting after warning: duration | min | `0x200013fb` |
| P72 | Charge activation: window duration | min | `0x200013fc` |
| P73 | Charge activation: interval | h | `0x200013fd` |
| P74 | Charge activation: attempts | count | `0x200013fe` |
| P75 | History interval while operating | min | `0x200013ff` |
| P76 | History interval in standby | min | `0x20001400` |
| P77 | Standby shutdown after | h | `0x20001401` |
| P78 | SOC warning threshold | % | `0x20001402` |
| P79 | SOC protection threshold | % | `0x20001403` |
| P80 | Intermittent recharge: SOC release threshold | % | `0x20001404` |
| P81 | Cycle: accumulated discharge | % | `0x20001405` |
| P82 | Connection fault impedance: no code effect | 0.1 mΩ | `0x20001406` |
| P83 | Connector compensation 1: cell number | cell number | `0x20001407` |
| P84 | Connector compensation 1: resistance | 0.1 mΩ | `0x20001408` |
| P85 | Connector compensation 2: cell number | cell number | `0x20001409` |
| P86 | Connector compensation 2: resistance | 0.1 mΩ | `0x2000140a` |

## All 64 function-switch positions

A1 routes above apply with the Group0 exceptions. Group7.Bit3 enables UART2 and
Group7.Bit4 selects its frame format. Preserve unused bits.

| Group | Bit | Meaning |
|---|---|---|
| Group0 | 0 | Allow writes over UART1 |
| Group0 | 1 | Temperature sensor plausibility |
| Group0 | 2 | Allow maintenance start over UART1 |
| Group0 | 3 | Allow Power/RTC over UART1: 1 in both MAINT versions; reserved in OEM |
| Group0 | 4 | 1.6.3: extended off enabled at 1; 1.5.3 reserved |
| Group0 | 5 | 1.6.3: individual pack lock active at 0, status; 1.5.3 reserved |
| Group0 | 6 | 1.6.3: hard-stop selection when bit 7=0; Original/1.5.3 reserved |
| Group0 | 7 | 1.6.3:0 explicit choice, 1 build default; Original/1.5.3 reserved |
| Group1 | 0 | Cell high-voltage warning |
| Group1 | 1 | Cell OVP |
| Group1 | 2 | Cell low-voltage warning |
| Group1 | 3 | Cell UVP |
| Group1 | 4 | Pack high-voltage warning |
| Group1 | 5 | Pack-OVP |
| Group1 | 6 | Pack low-voltage warning |
| Group1 | 7 | Pack-UVP |
| Group2 | 0 | Charge high-temperature warning |
| Group2 | 1 | Charge high-temperature protection |
| Group2 | 2 | Charge low-temperature warning |
| Group2 | 3 | Charge low-temperature protection |
| Group2 | 4 | Discharge high-temperature warning |
| Group2 | 5 | Discharge high-temperature protection |
| Group2 | 6 | Discharge low-temperature warning |
| Group2 | 7 | Discharge low-temperature protection |
| Group3 | 0 | Ambient high-temperature warning |
| Group3 | 1 | Ambient high-temperature protection |
| Group3 | 2 | Ambient low-temperature warning |
| Group3 | 3 | Ambient low-temperature protection |
| Group3 | 4 | Power stage high-temperature protection |
| Group3 | 5 | Power stage high-temperature warning |
| Group3 | 6 | Cell heating / heater minimum CCL |
| Group3 | 7 | Severe-fault latch / relay |
| Group4 | 0 | Charge overcurrent warning |
| Group4 | 1 | Charge overcurrent protection |
| Group4 | 2 | Discharge overcurrent warning |
| Group4 | 3 | Discharge overcurrent protection |
| Group4 | 4 | Short-duration overcurrent detection |
| Group4 | 5 | Short-circuit detection |
| Group4 | 6 | Lock after short-duration overcurrent |
| Group4 | 7 | Lock after short circuit |
| Group5 | 0 | Charger overvoltage protection |
| Group5 | 1 | Intermittent recharge |
| Group5 | 2 | SOC warning |
| Group5 | 3 | SOC protection |
| Group5 | 4 | Charge inhibition for a low cell |
| Group5 | 5 | Reverse polarity: no producer in OEM code |
| Group5 | 6 | Output connection fault |
| Group5 | 7 | Current limiter feedback |
| Group6 | 0 | Balancing |
| Group6 | 1 | Balancing also while idle |
| Group6 | 2 | Balancing time limit |
| Group6 | 3 | Balancing inhibition by ambient temperature |
| Group6 | 4 | Automatic charge activation; suppresses low-cell charge inhibition |
| Group6 | 5 | Manual charge activation after power-on |
| Group6 | 6 | Active current limiting |
| Group6 | 7 | Current limiting after charge overcurrent warning |
| Group7 | 0 | External on/off switch |
| Group7 | 1 | Standby shutdown |
| Group7 | 2 | Reserved, no OEM effect |
| Group7 | 3 | Display port UART2 enabled |
| Group7 | 4 | Extended display format |
| Group7 | 5 | Automatic pulse addressing / slave count adjustment |
| Group7 | 6 | Treat pulse address 0 as 1 |
| Group7 | 7 | CCL-Modus |

## Values without direct write registers

CCL/DCL/CVL, individual measurements, temperatures, alarm state, arbitrary
cycle/energy counters, raw gains and SOH are not freely writable UART registers.
Limits derive from parameters and state; gain changes use calibration commands;
SOH is fixed at 100%. DIP address, master role and fixed slave count are not
P0–P86 fields. Group7.Bit5/6 control alternative automatic addressing;
maintenance temporarily changes effective slave count. UART1 Modbus FC03/04 is
read-only. Pylontech supplies no additional configuration write route here.

## Reproduction

Run `write_access.py` with --verify, --markdown or no option for JSON.
Verification uses current release input hashes and embedded MNT04 templates;
it needs no historical build reports and does not rerun native tests.
Use --out NEW_FILE to write without overwriting an existing file. Native emulator
checks model MCU behavior; they do not replace electrical hardware validation.
The current contracts are in mod/docs/firmware, and OEM analysis in analysis/.

The [standard-library generator](../../tools/firmware-analysis/write_access.py)
emits JSON by default; --markdown renders this document. Published native
validation counts and limits are recorded in the release summaries below.

See
[MAINT 1.5.3](../../docs/firmware/maint153-positive-power.md),
[MAINT 1.6.3](../../docs/firmware/maint163-configurable-hard-stop.md),
[storage and reset](../../docs/firmware/storage-and-reset.md), and
[OpenBMS monitor integration](../../docs/firmware/openbms-monitor.md).
