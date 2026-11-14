# Configurable downward charge-current limit

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

**EMU1101-EXT Full 1.6.7 and later** provide a persistent downward CCL step of **1–20 A per online pack per aggregate update**. The default is **1 A**. The upward step remains **1 A per online pack per update**. Light and Full through 1.6.6 retain their fixed ordinary ramp. This is a bank charge-current-limit request, not an individual pack current regulator.

## Behavior

For online count N (the local master plus online slaves), the ordinary downward step is N × configured value. The firmware compares the remaining difference with the step before subtraction and writes the exact target when that difference is no larger than the step. No divisibility relationship between target and step is needed. An invalid runtime byte is treated as 1, never 0. The permitted range is a product constraint, not a measured optimum.

At twelve online packs, setting 10 gives a 120 A bank decrease per completed aggregate update. A 1560-to-10 A decrease takes 13 updates under constant inputs. These are not seconds: aggregation still requires a completed polling round and the native slow main pass. Early UART0 polling does not establish a fixed update frequency. The online count includes warning packs that remain online; it is distinct from the charge-eligible count.

Target calculation, existing immediate-zero branches, heating overrides and Full's separate Off/no-charge-path clamp retain their behavior. DCL is unchanged. Faster CCL reductions do not establish the inverter's current response or prevent all transient cell-voltage excursions. Physical Deye response and timing have not been tested. Setting 10 is an experimental candidate, not the shipped default.

Only the active master's aggregation uses this setting. Each BMS stores its own value; a slave's setting can become relevant if it becomes master. There is no automatic bank-wide replication.

[Calculated timing across OEM and EXT releases](early-polling.md#calculated-timing-across-firmware-versions) gives factors 1/2/3/5/10/20, several starting currents, pack-count examples and conditional one-/two-second update budgets. Larger factors reduce the number of downward updates; they do not shorten a polling round, guarantee a one-second cadence, accelerate the upward step or regulate each pack individually.

### Separate numeric setting, outside the OEM block

This is a persistent integer configuration value, not a Function bit, P87 or a live-current setpoint. The 87-value OEM block has a fixed layout and no established free field for this purpose. The unused flash-record trailer stores the EXT value without extending `47`/`A1` payloads or reassigning an existing parameter. Standard OEM XML exports therefore do not include it.

Applications should label it **EXT — CCL decrease step (master)** and use its own read/save workflow. In the ordinary bank UI, expose the control for the identified master only. Do not include it in “copy/apply parameters to all packs,” OEM XML imports/exports or background configuration replication. Firmware addressed access to slaves is supported, but it is not necessary for bank operation and must not imply that each slave limits its current by this value. On a master-role change, read the new master's own stored setting; do not copy a cached value automatically.

Validate integer 1–20 in the UI and backend, without rounding or coercing invalid input. The firmware independently enforces the range and exact payload length. Read capability/setting before enabling writes, use the normal UART1 parameter-write permission, send one explicit set, validate the reply, then read back. Do not treat an unavailable read as default 1, or replay writes after reconnect/restart. [OpenBMS and Home Assistant requirements](openbms-monitor.md#full-167-ccl-configuration) give the integration contract.

## Discovery and protocol

EXT05 remains 21 bytes. Capability bit 4 (`0010`) identifies this feature; the current Full capability mask is `001F`, while Light remains `000F`. Existing image flags and the original 87 numeric parameters/function-switch bytes remain unchanged.

| Operation | Addressed ASCII command | Request INFO |
|---|---|---|
| Read effective setting and limits | CID2 `64` | `07` |
| Set and persist | CID2 `64` | `08 vv`, where vv is a binary integer 1..20 |

Both operations support UART0 and UART1, own addresses 0–21. Foreign/FF requests remain silent. UART1 writes require **Group0.bit0=1**, the existing parameter-write permission; reads require no permission. UART0 uses local parameter access independently of that bit. UART0 host access still requires coordinated shared-bus ownership. UART2 has no new endpoint. Maintenance-marker mode is not a prerequisite on UART1.

Successful replies use RTN 00 and five decoded INFO bytes:

| Offset | Value |
|---|---|
| 0 | Format 01 |
| 1 | Effective downward factor, 1..20 A |
| 2 | Fixed upward factor 01 |
| 3 | Minimum 01 |
| 4 | Maximum 14 hex (=20) |

Invalid service arguments return RTN 05; a denied UART1 write returns 04; failed persistence returns 08. Transport-level bad headers, hex, lengths or checksums follow strict rejection/native error handling and never write the setting. A successful set verifies both programmed records and returns the active value. The next aggregate calculation uses it without restart. A missing response is ambiguous; read the setting before retrying.

The [client](../../tools/device/maintenance_client.py) prints frames without sending unless a transport is explicitly supplied:

```sh
python3 mod/tools/device/maintenance_client.py ccl-ramp --uart UART1 --address 0
python3 mod/tools/device/maintenance_client.py set-ccl-ramp --step 10 --uart UART1 --address 0
```

For an actual set, the client first reads 64/03 and requires capability 0010. OpenBMS Monitor should use the same capability check, expose an integer 1–20 field with unit **A / online pack / update**, and decode the returned value. Do not label it A/s. Set 1 explicitly to restore the original ordinary ramp.

## Persistence and failure handling

The separate field occupies bytes 173–175 of the existing 176-byte Full parameter record: `E7`, value, one's complement of value. Native payload bytes 0–170 and checksum 171–172 retain their exact format; the trailer has its own marker/range/complement validation. It is not part of the OEM checksum and is not a cryptographic integrity mechanism. No existing parameter or switch bit is repurposed. The fourth byte of the already reserved Full RAM cache stores the active value; no additional persistent RAM is allocated.

At boot both native-valid mirrors must contain identical valid trailers. Missing, invalid or disagreeing trailers select 1 without repair writes. This includes upgrade from older images. Normal parameter saves and persistent Off/On saves retain the active setting and write/verify the entire 176-byte record. Existing 64/04 diagnostics compare only the native 173-byte portion: “identical” there does not establish trailer agreement. Read 64/07 for the effective value.

If a set fails, the prior active value is restored and no success is reported. The flash transaction is not atomic across both mirrors: interrupted or failed writes can leave partial records. At reboot mismatching/invalid extensions select 1; a cut after both complete writes can retain the new value even without an ACK. Existing Full lock reconciliation remains independent. A later successful parameter save persists the then-active value.

Erasing parameter storage causes fallback 1. Older firmware may discard the extension when saving parameters; downgrade persistence is not guaranteed. No universal claim is made about third-party “factory reset” workflows; use 64/08 with value 1 for an explicit configuration reset.

## Implementation and validation

The source-bound hook replaces the native downward difference/comparison pair and preserves the native clamp/subtraction branches. Upward arithmetic is untouched. The largest tested byte-wide online count 255 gives a maximum raw step 51000 at setting 20, below 65536; subtraction occurs only when the difference exceeds the step. Intermediate arithmetic is 32-bit.

Mandatory actual-Thumb tests exercise all configured factors, boundary targets/counts, exact clamping, unchanged ascent, ABI, original direct overrides, addressed transports, malformed arguments, permission denial, legacy/corrupt/mismatched records, reboot, ordinary saves, Off/On, injected flash failures and power cuts. The parent publication gate independently re-derives OEM roles and rebuilds the complete candidate. Existing scheduler atomicity, protection, diagnostics and early-polling suites remain mandatory. These are bounded emulation checks, not physical flash, CAN timing or electrical validation.

[Full contract](ext-full.md) · [Release metadata](../../firmware/releases/ext-full.json) · [Early polling](early-polling.md) · [CCL aggregation](../../../analysis/protocols/can.md)
