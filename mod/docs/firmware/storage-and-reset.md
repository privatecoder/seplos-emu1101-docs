# Storage diagnostics and planned reset

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101) MAINT 1.5.3 and 1.6.3 support read-only ASCII64/04 on UART0 and UART1. Only 1.6.3 has lock/cache reporting and verified SOC saving before targeted45/06. Capability20 means diagnostics; capability40 separately means checkpoint before reset. A diagnostics flag alone must never imply saving.

## ASCII64/04 byte contract

Request exactly INFO04, LENGTH `E002`. The board answers its own address0–21, including slaves; foreign/FF requests are silent. No write, maintenance or power permission is required. Success is RTN00, ten decoded bytes, LENGTH `B014`. There is no corresponding UART2 command.

| Byte | Field | Values |
|---:|---|---|
| 0 | Diagnostic format | 01 |
| 1 | Parameter primary record | Record class |
| 2 | Parameter backup record | Record class |
| 3 | Parameter comparison | Comparison code |
| 4 | SOC primary record | Record class |
| 5 | SOC backup record | Record class |
| 6 | SOC comparison | Comparison code |
| 7 | Lock in primary parameter record | 1.6.3:00 unlocked,01 locked,FF unknown; 1.5.3:FF unavailable |
| 8 | Lock in backup parameter record | Same encoding as byte7 |
| 9 | Runtime lock cache | 1.6.3 flags below; 1.5.3:00 unavailable |

Record class0 means all256 record bytes areFF;1 means valid expected structure and CRC;2 means invalid. Parameter structure includes A0/171 and all four section markers; SOC structure is A0/20. Comparison0 means not comparable,1 both valid and identical,2 both valid and different. Comparison covers173 parameter bytes or22 SOC bytes, including CRC, and ignores unused word padding. Valid differences establish neither age nor which copy is newer.

On 1.6.3 byte9.bit0 indicates nonzero runtime latch, bit1 cached consistency equal to1, bit2 valid cache magicA6. Consistency is observed, not recomputed. Without bit2, runtime values are unconfirmed/null. Invalid parameter records have unknown recorded lock state. Example `01010101010101000006` means valid identical mirrors, recorded locks clear, valid consistent cache and runtime latch clear.

On 1.5.3 example `01010101010101FFFF00` means valid identical parameter/SOC mirrors and no lock/cache capability. **FF FF 00 does not mean unlocked.** Reserved Group0.bit5 can affect the complete parameter comparison but has no lock meaning on this profile.

The query reads flash directly without calling the repairing OEM reader. It never writes or repairs NVM, changes parameters or runtime cache, or borrows UART/display buffers. Existing IAP buffers are reused. Later ordinary loaders can still repair mirrors. Unknown formats/codes must not display as healthy. Diagnostics provides no historical reset cause, authoritative newer-copy selection, record age or current SOC percentage.

## Verified reset in 1.6.3

Targeted INFO `00 06 00` remains valid on UART0/UART1 45. The native UART0 updater form VER26 with INFO `01 06 00` is also supported. UART1 requires fresh Group0.bit3=1; denial returns RTN05 without saving. UART0 is independent of UART1 permission but needs stopped master polling. FF neither saves nor resets. Other foreign UART0 requests retain native failure handling without a new action.

Before reset, the original serializer produces the SOC/capacity record, writes primary block6 and verifies it, then writes/verifies backup. A final independent comparison checks both against intended data. Only then does the native watchdog-reset routine run. Success still has no ACK.

Recognized storage/readback failure returns **RTN08, LENGTH0000, no INFO and no reset** on both UART0/UART1. The previous RAM checkpoint is restored. A failed backup write may leave a new valid primary; complete rollback is not promised. Never turn RTN08 into success based on a matching RAM readback. Never automatically retry reset or a storage write.

Block6 contains remaining charge, learned full capacity, charge/discharge energy, cycles and energy remainder counters. The existing startup loader reads it and recomputes SOC. Saving preserves the latest native computed state, including only measurements already incorporated by that calculation. It does not force100%, calibrate SOC or restore an arbitrary historical percentage. P58/P59, UART0 49 and automatic save triggers retain their meanings. Power loss, other watchdog resets and logical on/off receive no new checkpoint.

The contextual hook recognizes the exact saved caller LR in the native serializer's guarded stack frame. Automatic saves keep the OEM IAP path. A short IRQ mask protects serialization; the original mask is restored before flash. OEM erase/program end with unconditional CPSIE, so there is no continuous interrupt mask during flash. The wrapper restores its caller's original mask before returning or resetting.

In 1.5.3 reset retains its native behavior and has no verified SOC checkpoint or new SOC-storage RTN08 contract. Ordinary native save triggers, including applicable A1 capacity correction, remain.

## Host and bootloader entry

Before planned reset record target identity, build, parameters and capacities. Send reset once and listen for errors. RTN08 aborts the operation before erase. Afterwards verify the same board/build and fresh capacity data; missing ACK alone proves neither reset nor saved state. Read64/04 when supported.

SOC saving adds unmeasured time before watchdog entry. One RFL exactly50 ms after reset is not a reliable entry strategy. Use one reset plus bounded read-only RFL probes. Finish collecting a fragmented response before another probe. Before any WFE/WFD, require complete RFB with valid length/checksum, bootloader address0 and data0100. Only a complete empty WFB is a write ACK; RFB is never one. Bootloader frames have no pack address. No repeated reset, erase or program is automatic.

The retained local boot-entry helper implements bounded probing; the separate OpenBMS updater was not modified in the firmware work and needs the same adaptation. Emulator checks establish no real millisecond bound. Keep UART1 transactions serialized with200 ms bus quiet. See [flashing](../tools/flashing.md).

## Evidence

Current mandatory suites execute actual Thumb paths with modeled IAP/UART hardware. The [service wrapper](../../firmware/patcher/seplos/service.s) defines the reset checkpoint and [diagnostic helper](../../tools/device/maintenance_client.py) defines host decoding. The inherited service checks cover record classes/CRC/structure, padding/cache, no diagnostic repair/writes, reset permissions and both UART0 forms, ABI, every storage-step failure, word-boundary interruptions in each mirror, IRQ-mask restoration and native boot restore. An initially valid alternate mirror survives the modeled interrupted programming cases. The model does not establish physical flash timing, brownout behavior, partial bits within a word, endurance or electrical load behavior. [Current profiles](README.md) · [Validation methods and limits](validation-methods-and-limits.md)
