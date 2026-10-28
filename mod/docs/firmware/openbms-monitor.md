# OpenBMS Monitor integration

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101) current firmware profiles are MAINT 1.5.3 and MAINT 1.6.3. Both provide addressed parameter and identity access, maintenance services, UART0 marker access, UART1 power/RTC and storage diagnostics. Only 1.6.3 adds persistent individual pack lock, verified SOC saving before planned reset and configurable recharge-waiting hard stop. The same cumulative image supports master and slaves; each board needs its own compatible firmware. A patched master does not supply patch features to older slaves.

## Ports, addressing and transactions

| Label | Connection | Protocol and conditions |
|---|---|---|
| UART0 | UART0, RS485-1/2 pair | ASCII, 19200 8N1 on the current OEM base; firmware update port. Stop master polling before host access to either master or slaves. |
| UART1 | UART1, RS485 pair in CAN socket | ASCII and binary, 9600 8N1. Addressed MAINT services work while UART0 polling continues. This is not CAN traffic. |
| UART2 | UART2, local display/BT | Binary, 9600 8N1; Group7.bit3 and a compatible format are required. Local board only; incoming address is not checked. |

UART1 and UART2 are separate paths. UART1 requires neither a display nor LCD permission. A UART0 daisy-chain alone does not connect the UART1 sockets of all packs. See [ports and topologies](../../../analysis/hardware/ports-and-topologies.md).

Use one coordinated requester, one outstanding transaction and one shared port/gateway lock for binary, ASCII and Modbus traffic. A transparent TCP–RS485 gateway carries the same bytes as a cable. Assemble TCP fragments under one total response deadline; the reference client uses three seconds. Skip an exact request echo without resending. Send each frame contiguously and collect the entire reply. UART1 needs a practical 200 ms quiet interval after the last received byte before another request. The nominal RX timeout is 104.17 ms; 100 ms can concatenate frames. MAINT protects a completed UART1 buffer and drops arriving bytes while occupied. It does not add pipelining, a second buffer or a worst-case main-loop latency guarantee. Gateway buffering can change the physical gap.

Target the board's own address 0–21; ordinary DIP addresses are 0–15. For example, address11 decimal is byte0B hex. Keep these distinct from a Modbus slave ID. Current addressed MAINT queries ignore foreign/FF addresses. Existing UART0 OEM command broadcast behavior is not globally replaced by that rule. UART1 maintenance status/start/stop are master0-only; UART0 marker read/clear is addressed per board.

Identify every board independently using fresh A4 and 64/03. Compare the expected 30-byte BMS_SN before a write and after reconnect/target changes. Preserve raw SN bytes; trim trailing spaces/NUL only for display. Empty, placeholder or duplicate serials are not unique identities. Device name/51 is not a unique identity. Identity coordination is a host responsibility, not firmware authentication. Never use a write or reset as a capability probe.

## Transport ambiguity and result classification

These are host integration requirements. The retained command-line clients do not implement every framing-recovery or continuous-quiet-time policy described here; their presence does not establish a complete monitor transport implementation.

Frame validation must establish both structural validity and transaction ownership. A valid-looking frame inside a plausible, incomplete outer response or request echo is not an independent acknowledgement. Keep incomplete framing state until the declared boundary, deadline or a justified rejection of the outer candidate.

| Synthetic receive case | Required host interpretation |
|---|---|
| A plausible47 response is truncated and its payload contains a valid E2 frame. | The nested bytes do not prove a rejection. At EOF/deadline report incomplete reception unless a separate unambiguous reply is established. |
| An A1 request echo is truncated and its switch bytes contain a valid zero-length A1 ACK. Further bytes differ from the remaining request prefix. | Prefix mismatch alone does not free the nested ACK. The unfinished echo range remains ambiguous; do not report write success. A genuine reply beyond that range can be considered separately. |
| A read is retried and two indistinguishable delayed responses arrive. | Do not assign a response or RTT sample to a particular attempt without evidence. Keep stale read responses out of a following action transaction. |
| An ASCII47 response has RTN00 and the correct address while an empty45 action reply is expected. | Require the exact command-specific reply layout:45 success has empty INFO/LENGTH0000. RTN00 plus address alone is insufficient. |
| A deadline, EOF or disconnect occurs after a write may have reached the pack. | Treat the action result as unknown/incomplete and perform fresh state verification. Do not turn a nested frame, subsequent disconnect or blind retry into success. |

Only a complete, correctly addressed, CRC/checksum-valid and unambiguous rejection with the required empty DATA/INFO is a confirmed error reply. Exact full request echoes may be skipped. A plausible started echo must also be tracked when it is incomplete; payload bytes can contain complete-looking frames. For47, validate3C/1B/08 section markers at the defined offsets before relying on a candidate's interpretation. Recover from impossible prefixes without ignoring an otherwise valid separate reply, and run a final framing pass at deadline/EOF.

These cases specify host robustness requirements, not extra firmware responses or a claim about a particular OpenBMS implementation. Transport tests belong with the host parser and should use synthetic bytes.

### Bus quiet time and scans

The practical UART1 pause is a continuous idle interval measured from the **last received byte**, including discarded noise and traffic arriving during the wait. Restart the idle timer whenever another byte arrives. Bound the total pre-transmit wait separately so a busy bus cannot hang the operation indefinitely.

If this bound expires before transmission, classify the request as **not sent / bus busy**. It is neither an unanswered request nor evidence that a pack is missing. Do not begin reset-outage observation or mark a write ambiguous when nothing was transmitted. A later state-check failure after a transmitted action is a different outcome.

An interrupted or bus-blocked scan is incomplete. Preserve the previously known pack list or expose a partial result explicitly; do not replace an authoritative polling list with only the addresses that happened to be queried. Avoid RTT learning from retried or otherwise ambiguously matched replies. Coordinate all protocols through the same physical-port lock.

## Binary parameter and identity frames on UART1

```text
55 ADR CMD LEN DATA[LEN] CRC_HI CRC_LO AA
```

Total length is LEN+7. CRC-16/XMODEM covers ADR through the last DATA byte: polynomial 1021, initial 0, no reflection, xor-out 0; CRC is big endian. Validate address, command, exact length, CRC and terminator. Payload may contain 55/AA/CR: read by LEN, not delimiter guesses.

| CMD hex | Request DATA bytes | Reply DATA bytes | Meaning |
|---|---:|---:|---|
| 47 | 0 | 168 | Parameters, switches and device name |
| A1 | 158 | 0 | Complete parameter/switch write |
| A2 | 0 | 30 | String1 / Battery_SN, raw bytes |
| A4 | 0 | 30 | String2 / BMS_SN, raw bytes |

Pack1 requests: `55 01 47 00 A3 6B AA`, `55 01 A2 00 4C 2C AA`, `55 01 A4 00 E6 8A AA`. Pack11 decimal A4: `55 0B A4 00 21 4B AA`. There is no repeated address in DATA.

47 DATA offsets:

| Offset | Size | Meaning |
|---|---:|---|
| 0 | 1 | 3C marker: count of u16 fields |
| 1–120 | 120 | 60 raw big-endian u16 values, P0–P59 |
| 121 | 1 | 1B marker |
| 122–148 | 27 | 27 u8 values, P60–P86 |
| 149 | 1 | 08 marker |
| 150–157 | 8 | Group0–7 switches |
| 158–167 | 10 | Device name, read only on this path |

A1 sends exactly bytes 0–157. It changes neither name nor serial numbers. Preserve all untouched raw values and bits, including temperature encodings. UART0 ASCII A1 is a different 169-byte INFO format including the name. UART1 has no ASCII A1/A2/A4 and no A3/A5 serial-writing extension. See [configuration parameters](../../../analysis/firmware/configuration-parameters.md).

A valid binary rejection replaces CMD with the error code, LEN0, with normal address/CRC:

| Code hex | Meaning |
|---|---|
| 81 | Unknown or unsupported command, including A3/A5 |
| 83 | Incorrect parameter section markers |
| 87 | Wrong DATA length for command |
| E2 | Native parameter validation rejected the block |
| E3 | UART1 write denied or a protected Group0 bit was changed |

Bad CRC, malformed/truncated frames and foreign addresses are discarded silently. An error code carrying DATA is not a valid rejection.

## Stored permissions and A1 workflow

All new controls occupy existing Group0, `function_switches[0]`, DATA offset150. There are no new Modbus registers or P87+ fields.

| Group0 bit | Current meaning | UART1 editing |
|---|---|---|
| 0 | 1 permits UART1 A1 | May clear itself; old active value authorizes the write. Re-enable through UART0/UART2. |
| 1 | Existing sensor plausibility function | Preserve unless intentionally edited. |
| 2 | 1 permits UART1 maintenance start | Protected: change through UART0/UART2 only. |
| 3 | 1 permits UART1 on/off, reset and RTC setting in both current profiles | Protected: change through UART0/UART2 only. |
| 4 | 1 enables extended off in 1.6.3; reserved in 1.5.3 | Ordinary writable bit only when capability04 is present. |
| 5 | 0 means individual lock active in 1.6.3; reserved in 1.5.3 | Read-only lock status; protected in 1.6.3. |
| 6/7 | Combined hard-stop selection in 1.6.3; reserved in 1.5.3 | Preserve low six bits and edit the pair together. |

UART1 A1 changing protected bits is rejected atomically with E3 before partial adoption. A denied write cannot unlock itself by setting bit0 in its payload. Bits0/2/3 are independent permissions; bit2 does not start maintenance. Bit3 does not authorize A1. Group0=FF permits UART1 A1, maintenance start and power/RTC in both current profiles. In 1.6.3 it also enables extended off, leaves the lock clear and inherits the image's hard-stop default. No parameter conversion occurs.

For an allowed write: acquire the shared lock, verify A4 at the target address, read 47 fresh, check bit0 and preserve protected bits. Ensure imported file/address belongs to the selected board. Send A1 once. Only a valid A1/LEN0 reply is ACK. Read 47 fresh and compare all 158 written bytes. An ACK plus matching RAM data does not independently prove flash persistence. Definitive rejection gets no automatic retry; missing/bad ACK leaves the outcome unknown, so read separately before considering another action.

An accepted A1 can reset learned full capacity and Qmax to P58 when they differ by at least 10 Ah, even if P58 was unchanged in a switch-only import. That branch also saves SOC block6 and can change displayed SOC. Rejected UART1 A1 does not reach it. P59 is a stored boot fallback, not a live SOC setter; 49/3A and 49/3B remain UART0-only.

UART0/UART2 adopt ordinary switches before native validation; UART0 also adopts the name. A rejected import can therefore change RAM without saving. In 1.6.3 protected bit5 is restored even on these failures. Use complete valid blocks and verify actual outcomes. If UART1 writing and maintenance start are both denied on a polling master, UART1 cannot unlock them; UART0 needs manual bus/DIP release or a functioning local UART2 path.

## Firmware identity: ASCII64/03

Use Seplos ASCII VER20, CID1=46, CID2=64, INFO03, request LENGTH `E002`. Validate the normal ASCII checksum and LENGTH check nibble, reply ADR, RTN00, exact decoded INFO length and recognized format. Current UART0/UART1 replies are MNT04, 19 decoded bytes, LENGTH `8026`, 56 ASCII frame bytes. The reply describes only the addressed board. Command51 identifies the OEM product/base, not a patch build.

| INFO offset | Size | MNT04 value |
|---|---:|---|
| 0–2 | 3 | ASCII MNT |
| 3 | 1 | Format04 |
| 4–6 | 3 | Binary OEM version, e.g. 10 06 0D = 16.06.13; FF third component means unknown |
| 7–9 | 3 | Binary patch version: 01 05 03 or 01 06 03 |
| 10–17 | 8 | Immutable concrete-image build ID |
| 18 | 1 | Image capability flags |

| Image flag hex | Meaning |
|---|---|
| 01 | Static hard stop; with MNT04 capability80, inherited build default instead |
| 02 | UART1 power/RTC commands and Group0.bit3 permission |
| 04 | Persistent pack lock, extended off and master CCL clamp |
| 08 | Positive polarity for supported Group0.bits3/4 |
| 10 | Addressed UART0 marker status/clear and firmware info; no UART0 start |
| 20 | Addressed UART0/UART1 storage diagnostics |
| 40 | Verified SOC checkpoint before targeted planned reset |
| 80 | Configurable hard stop; combine build default and fresh Group0 |

Published 1.5.3 flags are 3A (3B with static hard stop), build `2b89286ed6c14604`; 1.6.3 flags are FE (FF with inherited hard default), build `baa01ecd5af4eb28`. Flags are capabilities/image properties, not runtime permission, lock state, marker state or live MOSFET output. See [release metadata](../../firmware/releases/README.md).

Older MNT03 is exactly eighteen bytes, LENGTH `A024`, two patch-version bytes at7–8, build ID at9–16 and flags at17. MNT02 is seventeen bytes without image flags: report hard stop as unknown, not false. MNT01 has a different 22-byte layout and is rejected by the current client. Reject unknown formats/lengths and retain raw reserved bits. Patch version and INFO format are independent version fields. RevisionFF displays as unknown; `--base-revision` is a caller declaration in the build report.

Earlier 1.5 MNT02 build `909a604e60e9225b` and first MNT03 build `262dc7f549956de9` answered only as master0. Format03 alone does not prove addressed identity. Other old 1.5 images lack power/RTC. Older inverse-polarity images use bit3=0 for power permission; positive capability08 is required before interpreting bit3=1 as permitted. Extended off needs capability04 in addition to polarity08. A timeout, RTN04 unknown command or RTN05 unknown subcommand is not version info and does not prove that all older 47/A1/A2/A4 features are absent. Probe each board without a write.

## UART1 power and RTC

Offer these controls only with a recognized format and capability02. Current profiles additionally need fresh Group0.bit3=1 for changing power/RTC. Reads remain unrestricted. Send one unicast transaction; never use FF for these UART1 commands.

| CID2 | Raw INFO hex | Request LENGTH | Successful result |
|---|---|---|---|
| 45 | 00 04 10 | A006 | On; RTN00/LENGTH0000 |
| 45 | 00 04 1F | A006 | Off; RTN00/LENGTH0000 |
| 45 | 00 06 00 | A006 | Local watchdog reset; no ACK |
| 4D | Empty | 0000 | RTC read; seven bytes/LENGTH200E |
| 4E | Year BE16, month, day, hour, minute, second | 200E | RTC set; RTN00/LENGTH0000 |

UART1 RTC set validates year2000–2099, calendar date and time. For 2026-10-18 14:30:59 the bytes are `07 EA 0A 12 0E 1E 3B`. There is no timezone or NTP field. Use a consistent local-time convention and read4D afterwards, allowing for a seconds tick. RTC I2C failure returns RTN08; denied/invalid data returns RTN05; the OEM parser can reject earlier with RTN02/03. UART1 45 supports type4 and type6/00, not heating type3 or history-clear type5.

Master0 on/off retains the OEM slave broadcast and is a bank action. Its ACK confirms master acceptance, not delivery to every slave. Check slaves independently. Slave-unicast on/off and reset are local. Send reset once, listen for a possible failure, then verify return of the same serial/build. A timeout is not proof of reset; never replay automatically. The persistent maintenance marker and parameters survive restart. Only 1.6.3 adds the [verified SOC checkpoint](storage-and-reset.md).

1.5.3 off is OEM soft off: discharge is inhibited, charging may remain possible and detected charging can clear off. Do not present it as complete power-path disconnection.

## Individual pack lock in 1.6.3

Capability04 plus fresh Group0.bits4/5 identifies supported behavior. With bit4=1, targeted45-off records and verifies the individual latch in both parameter mirrors. Charge MOSFET, current limiter, discharge and precharge remain off; charge/port-voltage wakeup does not release it. Diagnostics remain reachable. Disabling bit4, reset, power interruption, old-parameter imports and master FF-on do not release a stored lock. Only targeted45-on verifies persistent clearing. On still obeys real protections and does not force the MOSFETs on.

Targeted on/off storage or verification failures return RTN08 on UART0 and UART1, LENGTH0000, no INFO. RAM stays or becomes locked. Successful RTN00 follows confirmed state; identical consistent commands avoid extra flash cycles. A matching RAM bit5 does not turn RTN08 into success: after failed off, RAM can be locked even if persistence failed and a reset would lose the latch. Timeout is unknown. Check fresh47, physical status and, for persistence, mirror diagnostics/restart. Damaged or disagreeing lock mirrors cause conservative locking; targeted on may repair them. Two fully empty copies are defaults, not retained lock evidence.

Normal FF-off does not create individual slave latches; FF-on may start unlocked slaves but cannot clear a latch. On to master0 does not unlock another board. The master clamp limits CCL to remaining charge-capable packs, including heater minimum and ramp; all blocked gives CCL0. DCL follows native real discharge-path evaluation. Effects require successful polling, not just ACK. The master also needs a compatible full profile for the clamp. Mixed banks require per-board checks. There is no individual CCL setter or galvanic isolation.

Host flow: lock transport, verify A4, read64/03+47, check bit3 permission; enable bit4 through normal A1 if needed while preserving bits2/3/5. Read back, send one targeted power command, require its proper result, then query bit5 and MOS/pack state. Explain protection-caused off states after successful unlock. Present bit5 as status only. Unlock deliberately before downgrading to firmware that lacks this state contract.

## Configurable hard stop in 1.6.3

Require MNT04 capability80 and read64/03 plus fresh47 to determine effective hard stop. Present one switch, preserve unrelated Group0 bits and distinguish runtime selection from the image default. Group5.Bit1 must enable recharge waiting. The [hard-stop contract](maint163-configurable-hard-stop.md) defines exact bit-pair encoding, update expression and native recovery/priority limits. It is separate from persistent pack off.

## Maintenance marker and polling

ASCII64 INFO commands:

| INFO hex | UART1 target | UART0 target | Meaning |
|---|---|---|---|
| 03 | Own pack0–21 | Own pack0–21 | Immutable firmware identity |
| 04 | Own pack0–21 | Own pack0–21 | Read-only storage diagnostics |
| 02 | Master0 only | Own pack0–21 | Marker and effective slave count |
| 01 C3 5A | Master0 only | Unsupported | Start maintenance |
| 00 C3 5A | Master0 only | Own pack0–21 | Clear known marker / stop maintenance |

Own-address UART0 maintenance-start requests return RTN05 without starting or writing; foreign/FF requests remain silent. UART0 clear is idempotent for an already erased FFFFFFFF marker and verifies readback after erasing a known active00000000 marker. Unknown words are left unchanged.

64/02 and successful start/clear return five decoded bytes, LENGTH `600A`: little-endian marker word at0–3, effective slave count at4. MarkerFFFFFFFF means inactive,00000000 active; any other value is unresolved and must not display as active success. Current clients reject old two-byte status replies. Unknown marker or recognized erase/readback failure returns RTN05 without INFO; the response alone does not identify the cause.

The persistent marker is at0x23000. Active maintenance forces the master's effective slave count to0, stops its UART0 polling and makes its native host path reachable. Aggregation then uses the local pack, including current limits. Stop restores the physical DIP slave count. Start requires Group0.bit2=1, valid token/marker and Group7.bit5=0 (automatic address/slave detection disabled). Stop does not need start permission. UART0 read/clear also needs no UART1 permission. Neither marker clear path releases a pack lock.

Immediate ACK can show the new marker and the previous effective count. Confirm with fresh64/02: start requires marker0/count0; stop requires FFFFFFFF and expected DIP count. When expected count is0, wait at least one full DIP cycle; the reference client uses1.1 s. UART0 clear is verified marker persistence, not proof that DIP/polling has completed. Verify physical UART0 bus silence before an update. Normal UART1 parameter/SN access needs no maintenance. Slaves need no separate maintenance mode.

## Updates and evidence limits

UART1 is not a bootloader/update port. A physical UART0 connection remains necessary. With a polling master, start maintenance on UART1, confirm fresh status and UART0 silence, then update one isolated bootloader target using the [flash procedure](../tools/flashing.md). Bootloader frames have no pack address. For current full firmware, account for SOC-save delay before reset; validate RFB0100 completely before any write and accept only WFB write acknowledgements. No automatic reset/erase/program retry. The separate OpenBMS updater needs this host behavior; its implementation was not changed by the firmware releases.

Current 1.5.3/1.6.3 evidence is offline actual-Thumb execution with modeled peripherals, unit/corpus checks and independent review. It does not establish real flash timing, interrupt latency, electrical isolation, current sharing, slave broadcasts or a physical multi-pack bank. Historical isolated-master evidence applies only to the inverse-polarity 1.6 build `18daf61d8a93671d`; it is not a current-profile hardware result.
