# MAINT 1.6.3: configurable hard stop

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101), cumulative OEM 16.06.13-based profile with positive UART1 power permission, persistent individual pack lock, storage diagnostics and verified SOC saving before planned reset. One stored setting selects hard stop during intermittent-recharge waiting. The same image supports master and slaves.

The [release metadata](../../firmware/releases/maint163-configurable-hard-stop.json) defines the exact image filename, build ID, MNT04 INFO, flags and EHEX/application SHA-256. The [generated capability matrix](uart-write-capabilities.md) renders current identities directly from that metadata.

The image contains 57,948 application bytes, a 4,856-byte appendix and 228 update blocks. There are 21 OEM hook sites. This release adds 36 code bytes and one hook; the existing four-byte lock cache is unchanged and there is no additional persistent RAM.

## Stored selection and image default

Only MNT04 flag `80` identifies configurable hard stop. With that flag, bit0 describes the immutable image default for inherited parameters. It is not live state. Published flags `FE` mean default soft; `--hard-stop enable` produces flags `FF`, default hard. Preserving an already static-hard-stop input also preserves its default. Explicit parameter selections override either default. Formats without this capability retain their static bit0 meaning.

| Group0 & 0xC0 | Selection |
|---|---|
| 0x00 | Explicit soft stop |
| 0x40 | Explicit hard stop |
| 0x80 or 0xC0 | Inherit image default |

Bit6 is the positive choice; bit7=0 marks an explicit setting and bit7=1 inherits. Existing Group0=FF therefore remains soft in the published FE image. No automatic NVM migration occurs. Arbitrary older bit7=0 values cannot be distinguished from explicit new settings; inspect existing 00/40 encodings before adopting them.

Expose one UI toggle. Read 47 fresh, preserve the lower six bits, write the complete validated A1 block, then read it back:

```python
new_group0 = (fresh_group0 & 0x3F) | (0x40 if enabled else 0)
```

Starting from FF gives 7F for hard and 3F for soft; those bytes are examples, not replacements for other configurations. Preserve protected lock-status bit5. UART0/UART2 may persist the setting; UART1 requires the existing bit0 write permission. UART1 power/RTC bit3 does not gate A1. Protected bits2/3/5 and ordinary validation remain. UART2 requires Group7.bit3 and a compatible display format. A RAM readback or ACK alone does not prove every physical flash write. Changes take effect on the next charge-path evaluation, without reset or a new command.

## Charge behavior and native hook

Group5.bit1 must enable intermittent recharge and its waiting event must be set. Hard stop adds Event6.bit1 to the native charge-inhibit mask: `71` soft, `73` hard. Configuration enabled does not mean the charge MOSFET is currently off. Original OVP, temperature and other checks retain their order. Discharge above 10 A for about 10 s can still permit charging. Persistent individual pack lock and extended off retain priority. Waiting packs remain dischargeable; current sharing with the charge MOSFET off is not established by emulation.

The new hook replaces `movs r4,#71/73; ldrb r3,[r3]` immediately before native TST/BNE, selects the mask and loads the same event byte. It neither temporarily changes events nor overrides GPIO afterwards. r0/r1/r2, r5–r12, SP and C/V are preserved; r3/r4 and N/Z match the displaced instructions. It uses sixteen temporary stack bytes. Native LDRB/STRB relationships identify the recovery counter: .11 uses C5, .12/.13 use C4. Only existing 1.6-compatible .11/.12/.13 inputs and their hard-stop variants are admitted; older gate forms remain refused. The lightweight profile supports its documented OEM input contracts. Hard-stop selection remains a setting of a current MAINT build.

## Host and verification

Build with `--maint-version 1.6.3 --base-revision 13`; `--hard-stop enable` selects the inherited default. The decoder reports `configurable_hard_stop=True`, `hard_stop_default=False`, `hard_stop=None` for the published image. After fresh 47, use `hard_stop_state(group0, flags, info_format=4)`; `hard_stop_group0(old, enabled)` preserves the other bits. No sending action was added to the client.

The [OpenBMS integration contract](openbms-monitor.md) describes lock and power behavior. [Storage and reset](storage-and-reset.md) specifies verified SOC saving and RTN08 abort. Reset success has no ACK; updater entry must use one reset, bounded read-only RFL probes, complete RFB0100 validation before writes and WFB-only write ACKs. No automatic reset/write retries. The separate OpenBMS updater was not changed by this firmware release.

The [hard-stop builder](../../firmware/patcher/seplos/configurable_hardstop.py) resolves the native hook; [client helpers](../../tools/device/maintenance_client.py) decode and compose the parameter choice.

The release passed 273 mandatory actual-Thumb groups, including all 65,536 Group0/Event6 combinations per MAINT build, native GPIO/recovery/protection, ABI, persistence and lock-priority cases. Unit/corpus regressions and independent review supplement them. There was no flashing or hardware test. [Metadata](../../firmware/releases/maint163-configurable-hard-stop.json) · [Capability matrix](uart-write-capabilities.md)
