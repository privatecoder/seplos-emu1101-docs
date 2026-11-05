# MAINT 1.6.4: full diagnostics and configurable hard stop

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

MAINT 1.6.4 is a cumulative firmware profile based on OEM 16.06.13, with positive UART1 power permission, persistent individual pack lock, storage diagnostics and verified SOC saving before planned reset. One stored setting selects hard stop during intermittent-recharge waiting. The same image supports master and slaves.

Both current profiles add addressed UART1 history, active/stored calibration and persisted-capacity/live-energy snapshots without new permission bits. MNT05 is 21 bytes with appended big-endian capability mask 000F. Existing 64/04 remains ten bytes. [Remote diagnostics](remote-diagnostics.md) defines the exact layouts, snapshot limits, shared history cursor and retry semantics. UART2 display behavior is unchanged.

The [release metadata](../../firmware/releases/maint-full.json) binds the exact image filename, build ID, MNT05 INFO, flags and EHEX/application SHA-256.

There are 21 existing OEM hook sites. The four-byte lock cache is unchanged; the new reads add no persistent RAM. The image has 59,236 application bytes, a 6,144-byte appendix and 233 update blocks. Build ID is `a8676b52bae281ff`; EHEX SHA-256 is `3a5ebf37197320ef6ba0ef5aba85daa981fe829ef312d9d84fc5ac0062c6bf3f` and application SHA-256 is `cd4ce64e20bf04c37e81da37daa170be53cf9380a589dd3d76c12972374d2f14`.

## Stored selection and image default

MNT04/MNT05 image flag `80` identifies configurable hard stop. With that flag, bit 0 describes the immutable image default for inherited parameters. It is not live state. Published flags `FE` mean default soft; `--hard-stop enable` produces flags `FF`, default hard. Preserving an already static-hard-stop input also preserves its default. Explicit parameter selections override either default. Formats without this capability retain their static bit 0 meaning.

| Group0 & 0xC0 | Selection |
|---|---|
| 0x00 | Explicit soft stop |
| 0x40 | Explicit hard stop |
| 0x80 or 0xC0 | Inherit image default |

Bit 6 is the positive choice; bit 7=0 marks an explicit setting and bit 7=1 inherits. Existing Group0=FF therefore remains soft in the published FE image. No automatic NVM migration occurs. Arbitrary older bit 7=0 values cannot be distinguished from explicit new settings; inspect existing 00/40 encodings before adopting them.

Expose one UI toggle. Read 47 fresh, preserve the lower six bits, write the complete validated A1 block, then read it back:

```python
new_group0 = (fresh_group0 & 0x3F) | (0x40 if enabled else 0)
```

Starting from FF gives 7F for hard and 3F for soft; those bytes are examples, not replacements for other configurations. Preserve protected lock-status bit 5. UART0/UART2 may persist the setting; UART1 requires the existing bit 0 write permission. UART1 power/RTC bit 3 does not gate A1. Protected bits 2/3/5 and ordinary validation remain. UART2 requires Group7.bit3 and a compatible display format. A RAM readback or ACK alone does not prove every physical flash write. Changes take effect on the next charge-path evaluation, without reset or a new command.

## Charge behavior and native hook

Group5.bit1 must enable intermittent recharge and its waiting event must be set. Hard stop adds Event6.bit1 to the native charge-inhibit mask: `71` soft, `73` hard. Configuration enabled does not mean the charge MOSFET is currently off. Original OVP, temperature and other checks retain their order. Discharge above 10 A for about 10 s can still permit charging. Persistent individual pack lock and extended off retain priority. Waiting packs remain dischargeable; current sharing with the charge MOSFET off is not established by emulation.

The new hook replaces `movs r4,#71/73; ldrb r3,[r3]` immediately before native TST/BNE, selects the mask and loads the same event byte. It neither temporarily changes events nor overrides GPIO afterwards. r0/r1/r2, r5–r12, SP and C/V are preserved; r3/r4 and N/Z match the displaced instructions. It uses sixteen temporary stack bytes. Native LDRB/STRB relationships identify the recovery counter: .11 uses C5, .12/.13 use C4. The underlying hard-stop contracts cover 1.6-compatible .11/.12/.13 inputs and their hard-stop variants; current builds also require proven remote-diagnostic layouts. Older gate forms and unknown read layouts remain refused. The lightweight profile supports its documented OEM input contracts. Hard-stop selection remains a setting of a current MAINT build.

## Host and verification

Build with `--maint-version 1.6.4 --base-revision 13`; `--hard-stop enable` selects the inherited default. The decoder reports `configurable_hard_stop=True`, `hard_stop_default=False`, `hard_stop=None` for the published image. After fresh 47, use `hard_stop_state(group0, flags, info_format=5)`; `hard_stop_group0(old, enabled)` preserves the other bits. The parameter helper does not send writes. The client also offers the new explicitly selected read commands.

The [OpenBMS integration contract](openbms-monitor.md) describes lock and power behavior. [Storage and reset](storage-and-reset.md) specifies verified SOC saving and RTN08 abort. Reset success has no ACK; updater entry must use one reset, bounded read-only RFL probes, complete RFB0100 validation before writes and WFB-only write ACKs. No automatic reset/write retries. The separate OpenBMS updater was not changed by this firmware release.

The [hard-stop builder](../../firmware/patcher/seplos/configurable_hardstop.py) resolves the native hook; [client helpers](../../tools/device/maintenance_client.py) decode and compose the parameter choice.

Image publication requires every mandatory actual-Thumb suite, including all 65,536 Group0/Event6 combinations, native GPIO/recovery/protection, ABI, persistence, lock-priority and remote diagnostic cases. The actual current image passed 293 mandatory groups and rebuilt byte-identically. The history model injects UART1 RX at the EEPROM transfer boundary; full concurrent UART0 polling, timer and protection execution has not been tested. Unit/corpus regressions and independent review supplement them. No current image was flashed or hardware-tested. [Metadata](../../firmware/releases/maint-full.json) · [Capability matrix](uart-write-capabilities.md)
