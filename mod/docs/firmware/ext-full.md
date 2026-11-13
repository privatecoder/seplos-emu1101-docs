# EMU1101-EXT Full 1.6.3 and later: full diagnostics and configurable hard stop

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT Full provides addressed parameter/identity access, maintenance services, UART0 marker access, UART1 power/RTC access control, storage diagnostics, persistent individual pack lock, verified SOC saving before planned reset and stored hard-stop selection during intermittent-recharge waiting from Full 1.6.3. Permission bits use 1=enabled and 0=denied in every versioned release. The current published image is Full 1.6.5, based on OEM 16.06.13. The same image supports master and slaves.

Addressed UART1 history, active/stored calibration and persisted-capacity/live-energy snapshots are available from Full 1.6.4 and Light 1.5.4, without new permission bits. EXT05 is 21 bytes with appended big-endian capability mask 000F. Existing 64/04 remains ten bytes. [Remote diagnostics](remote-diagnostics.md) defines the exact layouts, snapshot limits, shared history cursor and retry semantics. UART2 display behavior is unchanged.

The [release metadata](../../firmware/releases/ext-full.json) binds the exact image filename, build ID, EXT05 INFO, flags and EHEX/application SHA-256.

The current Full 1.6.5 image has 22 guarded OEM hook sites and a four-byte lock cache. The atomic scheduler cleanup introduced in Full 1.6.5 adds a short saved-PRIMASK critical section with no new persistent RAM. The image has 59,260 application bytes, a 6,168-byte appendix and 233 update blocks. The release metadata records the exact build ID and EHEX/application SHA-256.

## Stored selection and image default

Firmware identity flag `80` identifies configurable hard stop from Full 1.6.3. With that flag, bit 0 describes the immutable image default for inherited parameters. It is not live state. Published flags `FE` mean default soft; `--hard-stop enable` produces flags `FF`, default hard. Preserving an already static-hard-stop input also preserves its default. Explicit parameter selections override either default. Profiles without this capability retain the static bit 0 meaning.

| Group0 & 0xC0 | Selection |
|---|---|
| 0x00 | Explicit soft stop |
| 0x40 | Explicit hard stop |
| 0x80 or 0xC0 | Inherit image default |

Bit 6 selects hard stop; bit 7=0 marks an explicit setting and bit 7=1 inherits. Existing Group0=FF therefore remains soft in the published FE image. No automatic NVM migration occurs. Stored upper-bit values 00/40 select explicit soft/hard modes. Read the current Group0 value before changing the setting.

Expose one UI toggle. Read 47 fresh, preserve the lower six bits, write the complete validated A1 block, then read it back:

```python
new_group0 = (fresh_group0 & 0x3F) | (0x40 if enabled else 0)
```

Starting from FF gives 7F for hard and 3F for soft; those bytes are examples, not replacements for other configurations. Preserve protected lock-status bit 5. UART0/UART2 may persist the setting; UART1 requires the existing bit 0 write permission. UART1 power/RTC bit 3 does not gate A1. Protected bits 2/3/5 and ordinary validation remain. UART2 requires Group7.bit3 and a compatible display format. A RAM readback or ACK alone does not prove every physical flash write. Changes take effect on the next charge-path evaluation, without reset or a new command.

## Charge behavior and native hook

Group5.bit1 must enable intermittent recharge and its waiting event must be set. Hard stop adds Event6.bit1 to the native charge-inhibit mask: `71` soft, `73` hard. Configuration enabled does not mean the charge MOSFET is currently off. Original OVP, temperature and other checks retain their order. Discharge above 10 A for about 10 s can still permit charging. Persistent individual pack lock and extended off retain priority. Waiting packs remain dischargeable; current sharing with the charge MOSFET off is not established by emulation.

The configurable hard-stop hook introduced in Full 1.6.3 replaces `movs r4,#71/73; ldrb r3,[r3]` immediately before native TST/BNE, selects the mask and loads the same event byte. It neither temporarily changes events nor overrides GPIO afterwards. r0/r1/r2, r5–r12, SP and C/V are preserved; r3/r4 and N/Z match the displaced instructions. It uses sixteen temporary stack bytes. Native LDRB/STRB relationships identify the recovery counter: .11 uses C5, .12/.13 use C4. The underlying hard-stop contracts cover Full-profile-compatible OEM .11/.12/.13 inputs and their hard-stop variants; current builds also require proven remote-diagnostic layouts. Older gate forms and unknown read layouts remain refused. The lightweight profile supports its documented OEM input contracts. Hard-stop selection remains a setting of a current EMU1101-EXT build.

## Host and verification

Build with `--ext-version 1.6.5 --base-revision 13`; `--hard-stop enable` selects the inherited default. The decoder reports `configurable_hard_stop=True`, `hard_stop_default=False`, `hard_stop=None` for the published image. After fresh 47, use `hard_stop_state(group0, flags, info_format=5)`; `hard_stop_group0(old, enabled)` preserves the other bits. The parameter helper does not send writes. The client also offers the explicitly selected read commands.

The [OpenBMS integration contract](openbms-monitor.md) describes lock and power behavior. [Storage and reset](storage-and-reset.md) specifies verified SOC saving and RTN08 abort. Reset success has no ACK; updater entry must use one reset, bounded read-only RFL probes, complete RFB0100 validation before writes and WFB-only write ACKs. No automatic reset/write retries. The separate OpenBMS updater was not changed by this firmware release.

The [hard-stop builder](../../firmware/patcher/seplos/configurable_hardstop.py) resolves the native hook; [client helpers](../../tools/device/maintenance_client.py) decode and compose the parameter choice.

Image publication requires every mandatory actual-Thumb suite, including all 65,536 Group0/Event6 combinations, native GPIO/recovery/protection, ABI, persistence, lock-priority and remote diagnostic cases. The current build passes 339 mandatory groups, including the atomic scheduler regression. The EXT05 Full 1.6.4 reference has its own identity and passes 333 mandatory groups. The history model injects UART1 RX at the EEPROM transfer boundary; deterministic native cases cover enabled timer/protection/CMP handlers and concurrent UART0 reception with deferred parsing, while a complete multi-pack UART0 polling system remains untested. Unit/corpus regressions and independent review supplement them. No current image was flashed or hardware-tested. [Metadata](../../firmware/releases/ext-full.json) · [Capability matrix](uart-write-capabilities.md)
