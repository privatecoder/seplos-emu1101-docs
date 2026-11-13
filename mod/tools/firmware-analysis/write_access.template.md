# EMU1101-EXT UART access capabilities

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The versioned feature baselines are **Light 1.5.3+** and **Full 1.6.3+**.
Shared remote reads are available from Light 1.5.4+ / Full 1.6.4+, and atomic
scheduler cleanup from Light 1.5.5+ / Full 1.6.5+. The tables compare the exact
OEM 16.06.13, Light 1.5.5 and Full 1.6.5 images listed below. Determine each target's capabilities with 64/03;
command 51 reports the OEM base family and cannot identify the patch release.
Unknown images require separate analysis. The catalogue verifies current input
hashes, EXT05 metadata/template and build-ID digests against public release
JSONs without opening ports or rerunning native emulation.

@PROFILES@

SHA-256, where listed, covers the complete .ehex file. The OEM image has no
EMU1101-EXT build ID or EXT05 reply. Published hashes bind the actual release files;
a different hard-stop build option produces a different image.

## Ports and conditions

| Port | Transport | Access |
|---|---|---|
| UART0 | ASCII, 19200 8N1 | Addressed local pack; pause master polling before host access to master or slaves. |
| UART1 | ASCII and binary 55…AA, 9600 8N1 | EMU1101-EXT addressed operations can coexist with UART0 master polling. |
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
EMU1101-EXT addressed operations accept 0–21. These are local capabilities, without
a master proxy. A dash means no implemented route.

**[W]** Group0.Bit0=1 permits A1 writes through UART1.

**[P]** Requires image flag bit 1 and Group0.Bit3=1; 0 denies access in every versioned release. This permission covers power, restart and RTC writes through UART1;
UART0 uses its original path, and UART1 RTC reads need no power permission.

**[M]** Maintenance start requires master address 0, Group0.Bit2=1,
Group7.Bit5=0, a valid marker state and exact token 01 C3 5A.

**[X]** Extended off requires Full capability and Group0.Bit4=1. A
stored individual lock remains active when this feature is disabled; addressed
on may release it independently of that setting.

## Complete write and action matrix

**Bold UART names** in the EMU1101-EXT columns mark interfaces newly available for that operation compared with Original .13.

@MATRIX@

A1 always transmits a complete valid parameter block. UART0 uses ASCII with 169
INFO bytes, including the device name. UART1/UART2 use binary with 158 DATA bytes,
without the name. Individual P values are not directly writable registers.

## Additional read and service operations

@READS@

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

UART0/UART1 64/03 returns identical EXT05 information for a given pack: 21 decoded
bytes, LENGTH 402A. Offsets 0–2 EXT, 3 format, 4–6 OEM base, 7–9 patch version,
10–17 build ID, 18 image flags, 19–20 capability mask u16 BE 000F. It contains no runtime marker or state fields.
Flag 0x10 identifies UART0 marker/info support.

From Light 1.5.4+ / Full 1.6.4+, read-capability bits 0/1/2/3 mean UART1 history, calibration pages, persisted SOC contents and full-width live energy. Discover support through the explicit mask; never infer it from a version or image flag. Reads require no master role, marker or Group0 enable flag. UART1 RX injection at the EEPROM transfer boundary is model-tested; deterministic native cases cover timer/protection/CMP execution and concurrent UART0 reception, while complete multi-pack polling and physical timing remain untested. Existing 64/04 is unchanged. [Remote diagnostics](../../docs/firmware/remote-diagnostics.md) defines exact layouts, shared-cursor rollback and snapshot/boot limits. UART2 is unchanged.

## Availability and variant rules

The table above compares the concrete current `.5` images. Feature availability
in the versioned release lines begins as follows; earlier development steps are
listed separately in the [changelog](../../firmware/CHANGELOG.md).

| Feature | Light | Full |
|---|---|---|
| Addressed access, UART0 marker/identity, UART1 power/RTC access control and storage diagnostics | Light 1.5.3 onward | Full 1.6.3 onward |
| Persistent individual lock and verified SOC checkpoint before reset | Unavailable | Full 1.6.3 onward |
| Runtime hard-stop selection | Unavailable | Full 1.6.3 onward |
| UART1 history, calibration pages, persisted SOC contents and full-width energy reads | Light 1.5.4 onward | Full 1.6.4 onward |
| Atomic scheduler cleanup | Light 1.5.5 onward | Full 1.6.5 onward |

Both variants permit UART1 Power/RTC with Group0.Bit3=1. Image flag 0x08
records this standard rule and is set in every versioned release. Group0 FF
therefore allows UART1 Power/RTC.
Extended off requires Full capability 0x04 and bit4=1; bit5=0 reports an
individual lock. Disabling bit4 does not release an existing lock. Light
reserves bits4/5. The scheduler fix introduces no new parameter.

Storage diagnostics are freely readable at own addresses 0–21 on UART0/UART1;
foreign/FF remain silent. Format01 has ten INFO bytes, LENGTH B014, and reads
parameter/SOC shape, CRC and differences without repair. Light returns lock
bytes7/8=FF and byte9=00: unavailable state, not confirmed unlocked. Full saves
and verifies both original SOC copies before addressed UART0/UART1 45/06.
RTN08 prevents reset on storage/verification failure; FF does not checkpoint or
reset. UART1 still needs [P]. Light retains the OEM UART0 45 broadcast paths.

The four buildable profiles use EXT05. EXT05 patch bytes are 01 05 05 / 01 06 05 in the current Light/Full builds. Diagnostic flag0x20 is present in both; checkpoint flag0x40
is Full-only. Current soft-default image flags are3A/FE; a static hard-stop
Light build uses3B. Full protects bit5 even during malformed UART0/UART2 imports.
Addressed UART0/UART1 on/off returns RTN08/LENGTH0000 on a persistence failure;
matching RAM bit5 does not turn failure into success. Check uncertain outcomes
with fresh reads rather than automatically repeating writes.

### Configurable hard stop from EMU1101-EXT Full 1.6.3

Image flag 0x80 marks configurability. Image flag bit 0 is the build default
when Group0.bit7=1; explicit parameter choices take precedence. The published FE
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
Group0=FF follows the build default and selects soft stop in an FE image.
Stored upper-bit values 00/40 select explicit modes. Read Group0 before
changing the setting; no automatic NVM migration occurs.

This extends charge prohibition to intermittent recharge waiting. Original
Group5.Bit1 recharge logic must be enabled and Event6.Bit1 must actually occur.
This is neither immediate on/off nor an individual pack lock. Own discharge
above 10 A for about 10 s may release the charge path as before. Pack locks
win. The native charge-inhibit mask changes from 0x71 to 0x73, retaining
OVP/temperature priorities. It does not remove DCL. Configuration takes effect
live. 64/03 is static: read 47/Group0 for active configuration.


## Group0 rules

@GROUP0@

No automatic parameter conversion or NVM migration is performed.
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

The listed EMU1101-EXT profiles use UART0, UART1[W], UART2; OEM .13 uses UART0 and UART2. Transfer the complete
valid block. Raw units differ from UI units; validation can couple fields.
P82 can be stored but has no reader in the analyzed base code. Parameter
relationships are described in the
[configuration reference](../../../analysis/firmware/configuration-parameters.md).

@PARAMETERS@

## All 64 function-switch positions

A1 routes above apply with the Group0 exceptions. Group7.Bit3 enables UART2 and
Group7.Bit4 selects its frame format. Preserve unused bits.

@BITS@

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
Verification uses current release input hashes and embedded EXT05 templates;
it needs no historical build reports and does not rerun native tests.
Use --out NEW_FILE to write without overwriting an existing file. Native emulator
checks model MCU behavior; they do not replace electrical hardware validation.
The current contracts are in mod/docs/firmware, and OEM analysis in analysis/.

The [standard-library generator](../../tools/firmware-analysis/write_access.py)
emits JSON by default; --markdown renders this document. Published native
validation counts and limits are recorded in the release summaries below.

See
[Light 1.5.3+ contract](../../docs/firmware/ext-light.md),
[Full 1.6.3+ contract](../../docs/firmware/ext-full.md),
[storage and reset](../../docs/firmware/storage-and-reset.md), and
[OpenBMS monitor integration](../../docs/firmware/openbms-monitor.md).
