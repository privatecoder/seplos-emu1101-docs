# Addressed read-only remote diagnostics

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

MAINT 1.5.4 and 1.6.4 add UART1 history, active/stored calibration, persisted capacity contents and full-width live energy. Reads require the board's own address 0–21, with ordinary DIP addresses 0–15. Foreign and FF requests are silent. No master role, maintenance marker or Group0 permission is required. UART0 host access still requires coordinated bus ownership. UART2 display behavior is unchanged.

Each request has one response. These endpoints do not calibrate, repair mirrors, save a checkpoint, change permissions, set the RTC or reset. Existing ten-byte 64/04 diagnostics and five-byte 64/02 status remain unchanged. UART1 destructive 45/05 remains unsupported. UART0 OEM 4B retains its original addressing and shared-history behavior.

## MNT05 capability discovery

ASCII 64 with INFO 03 returns 21 decoded bytes, LENGTH `402A`, 60 total ASCII frame bytes. Offsets 0–18 retain the MNT04 positions; the format and patch version change explicitly.

| INFO offset | Width | Value |
|---|---:|---|
| 0–2 | 3 | ASCII `MNT` |
| 3 | 1 | Format 05 |
| 4–6 | 3 | Binary OEM major/minor/revision; revision FF means unknown |
| 7–9 | 3 | Patch 01 05 04 or 01 06 04 |
| 10–17 | 8 | Concrete-image build ID |
| 18 | 1 | Existing image flags; default 3A light / FE full |
| 19–20 | 2 | Capability mask, unsigned big endian; current value 000F |

| Mask bit | Capability |
|---|---|
| 0 / 0001 | Addressed UART1 history 4B |
| 1 / 0002 | Active/stored calibration 64/05 pages |
| 2 / 0004 | Persisted SOC/capacity contents in 64/06 |
| 3 / 0008 | Full-width live energy in 64/06 |

Offer a read only when its explicit capability is present. Version text, a previous 64/04 flag or an ACK does not establish these capabilities. The reference client rejects unknown formats, wrong lengths and unknown capability bits. Historical MNT03/MNT04 are still decoded without inferring new capabilities. Image flags remain distinct from runtime permissions and the appended read-capability mask.

## History: ASCII 4B on UART1

Request INFO is exactly two bytes: byte 0 unused, byte 1=00 oldest or any nonzero value next. The reference client sends 0000 or 0001. Empty ring returns RTN00 with empty INFO. EEPROM read failure returns RTN08 with empty INFO. Invalid parseable requests return RTN05 with empty INFO; unparseable or foreign requests may remain silent.

A nonempty RTN00 reply preserves the original 97-byte layout, LENGTH `20C2`, 212 ASCII frame bytes:

| INFO offset | Width | Meaning |
|---|---:|---|
| 0 | 1 | Format 01 |
| 1 | 1 | Last-record flag 00/01 |
| 2–3 | 2 | Year, unsigned big endian |
| 4–96 | 93 | Original EEPROM record bytes 1–93 unchanged |

The [OEM history layout](../../../analysis/protocols/seplos-ascii.md#56-cid2-0x4b-read-history) defines the timestamp tail, status, cells, temperatures, capacities and events. There are 500 slots of 128 bytes; each native read transfers 94 bytes. Change-triggered records can contain previous event bytes, so their timestamps are not necessarily exact event transition times.

UART0 and UART1 share the OEM cursor. Do not interleave independent readers. UART1 restores its saved cursor after a reported EEPROM read failure so a subsequent next request retries the same logical entry. A missing response remains ambiguous: a completed request can already have advanced the cursor. Host retry policy must account for that. Concurrent writes can move ring contents/count; no full-ring atomic snapshot is promised.

At 9600 8N1 the 212-byte response takes 220.83 ms on the wire; the 22-byte request adds 22.92 ms. A practical 200 ms quiet allowance gives 443.75 ms before EEPROM, scheduler and gateway latency. About 0.5 s per record and 4 min for 500 are planning estimates, not measured hardware guarantees. The model injects UART1 RX at the EEPROM transfer boundary. Full concurrent UART0 polling, timer and protection execution has not been tested. Physical timing, real I2C fault duration, scheduler latency and traffic saturation remain unmeasured. Keep protection and UART0 polling active during UART1 reads.

## Calibration: ASCII 64/05

INFO 05 alone or 0500 selects active RAM. INFO 0501 selects the stored primary record and 0502 the backup. Other lengths/pages return RTN05. The response begins format 01 and page 00/01/02.

### Active snapshot: 72 bytes

All multibyte values are big endian. Snapshot capture briefly saves/restores PRIMASK and makes no hardware calls while interrupts are masked.

| INFO offset | Width | Meaning |
|---|---:|---|
| 0 | 1 | Format 01 |
| 1 | 1 | Page 00, active |
| 2 | 1 | Event8 &1C: invalid voltage/current-gain/current-zero bits |
| 3 | 1 | Cell count |
| 4–35 | 32 | Sixteen unsigned 16-bit cell gains |
| 36–37 / 38–39 | 2 each | Unsigned 16-bit voltage gains, stored-record offsets 35/37 |
| 40–41 / 42–43 | 2 each | Unsigned 16-bit current gains A/B |
| 44–47 / 48–51 | 4 each | Signed 32-bit raw zero bases A/B |
| 52–53 / 54–55 | 2 each | Unsigned 16-bit primary conversion references A/B |
| 56–59 / 60–63 | 4 each | Signed 32-bit raw samples A/B |
| 64–67 / 68–71 | 4 each | Signed 32-bit converted current A/B, mA |

Raw zero bases are not amperes. Differences in gain or one current observation alone do not prove physical accuracy or a hardware fault.

### Stored page: 58 bytes

| INFO offset | Width | Meaning |
|---|---:|---|
| 0 | 1 | Format 01 |
| 1 | 1 | Page 01 primary / 02 backup |
| 2 | 1 | Strict class: 00 erased, 01 expected A0/51 shape plus CRC, 02 invalid |
| 3 | 1 | Native CRC acceptance boolean 00/01: declared length ≤ 250 plus CRC |
| 4 | 1 | Declared record length |
| 5–57 | 53 | Raw prefix in native little endian, including expected CRC positions |

The raw stored prefix has marker at 0, length at 1, invalid flags at 2, cell gains at 3+2i for i 0–15, voltage gains at 35/37, current gain A at 39, signed zero A at 41, gain B at 45, signed zero B at 47 and expected CRC at 51. Expected logical length is 51 before the two CRC bytes. The raw prefix alone cannot independently validate a record with an anomalous declared length greater than 51.

Strict shape and native CRC acceptance are separate. A malformed CRC-accepted record remains invalid in strict diagnostics. Stored gain B can differ from active 62000 because the OEM loader forces the active value. CRC acceptance does not prove coefficient plausibility. Stored reads use raw flash through existing IAP buffers; they avoid the repairing loader, saver and A0 actions. There is no arbitrary flash-address interface.

## Persisted capacity and live energy: ASCII 64/06

Request INFO must be exactly 06. The response is 68 bytes, format 01. The live group is a coherent snapshot; raw stored records remain native little endian.

| INFO offset | Width | Meaning |
|---|---:|---|
| 0 | 1 | Format 01 |
| 1 / 2 | 1 each | Strict primary/backup class: 00 erased, 01 expected A0/20 plus CRC, 02 invalid |
| 3 | 1 | Comparison: 00 not both healthy, 01 same 22 bytes, 02 different |
| 4 | 1 | Native CRC acceptance mask: bit 0 primary, bit 1 backup |
| 5 | 1 | Observed boot choice: 00 fallback, 01 primary, 02 backup |
| 6–7 | 2 | Live P58 full capacity, unsigned BE, 0.01 Ah |
| 8–9 | 2 | Live P59 remaining capacity, unsigned BE, 0.01 Ah |
| 10–13 / 14–17 | 4 each | Live charged/discharged energy, unsigned BE, 0.1 kWh |
| 18–19 / 20–21 | 2 each | Live remaining/full capacity, unsigned BE, 0.01 Ah |
| 22–23 | 2 | Live SOC, unsigned BE, 0.1 percentage point |
| 24–45 | 22 | Raw primary record |
| 46–67 | 22 | Raw backup record |

Each stored 22-byte record uses native little endian:

| Record offset | Width | Meaning |
|---|---:|---|
| 0 / 1 | 1 each | Expected marker A0 / length 20 excluding CRC |
| 2 / 4 | 2 each | Remaining/full capacity, 0.01 Ah |
| 6 / 10 | 4 each | Charged/discharged energy total, 0.1 kWh |
| 14 | 2 | Cycles |
| 16 | 2 | SOC-cycle reference, 0.1 percentage point |
| 18 | 2 | Accumulated SOC decrease for cycles, 0.1 percentage point |
| 20 | 2 | CRC16/Modbus |

A native CRC-accepted wrong-shape record can be selected by boot while strict diagnostics reports invalid. The client preserves its raw bytes and does not decode it as expected fields. Primary wins if accepted; otherwise backup wins if accepted; otherwise boot uses fallback. This reports snapshot selection, not a guaranteed next-boot SOC. Automatic saves, full-profile reset checkpoints, parameter changes or later storage faults can intervene. P58/P59 are labelled live; they are not a promise of the future boot fallback. No read repairs either mirror or forces a save.

Q and Qmax are reconstructed from stored capacities; they are not independent stored fields. The final u16 values are cycle bookkeeping, not fractional energy remainders. Live energy is full unsigned 32-bit: raw 65000 means 6500.0 kWh. Existing 42 output is unchanged: at raw 65000 or above it emits fallback 6500, meaning 650.0 kWh. Neither 650.0 kWh from 42 nor persisted energy alone determines the full live counter.

## Client and validation

The [device tools](../../tools/device/README.md#read-only-remote-diagnostics) list offline commands. `maintenance_client.py` sends only with an explicit serial/TCP transport and performs one exchange per new read. New decoders return JSON-compatible dictionaries; raw stored data remains hexadecimal with separate strict classification and native CRC acceptance.

Mandatory native validation covers emitted code, own/foreign addresses, both diagnostic ports, malformed requests, record shapes/CRC, failures, ABI, no repair/write side effects, history cursor rollback and UART1 RX injection at the EEPROM transfer boundary. Full concurrent UART0 polling, timer and protection execution has not been tested; physical timing remains unmeasured. Offline host tests cover explicit capability discovery, endian/signed fields, unsigned energy beyond 65000 and one-request behavior. The actual light/full releases passed 214/293 mandatory native execution groups and rebuilt byte-identically. Build IDs are `80112d861b8329c4`/`a8676b52bae281ff`; [release metadata](../../firmware/releases/README.md) binds their exact EHEX/application hashes. `hardware_tested` remains false; no current profile was flashed or tested on hardware. See [validation limits](validation-methods-and-limits.md).
