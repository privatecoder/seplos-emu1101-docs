# Firmware flashing and verification

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Firmware updates use **UART0 at RS485-1/2**. UART1 on the CAN socket's RS485 pair is not an update port. Use a complete offline-validated EHEX and its exact build report or release metadata. [Build instructions](../firmware/build-and-validation.md) create the image; [device tool help](../../tools/device/README.md) defines each retained updater's arguments.

**Experimental firmware:** MAINT 1.5.3 and 1.6.3 have offline validation only and have not been flashed or hardware-tested. Incorrect firmware, wiring or interrupted programming can leave the BMS unusable and compromise battery protection. Use at your own risk; project-authored software is provided "AS IS", without warranty, under the [license](../../../LICENSE).

Use a prepared device interpreter such as `SEPLOS_TOOLS_PY="$HOME/.local/share/seplos-firmware-tools/venv/bin/python"` for serial helpers; it must supply the dependencies listed in the [device setup](../../tools/device/README.md). The separate `SEPLOS_PYTHON` patcher interpreter stays at `~/.local/share/seplos-oem-patcher/venv/bin/python`.

## Before a write

1. Identify the physical board, DIP role/address and wiring. Obtain fresh serial numbers and parameters while the application is reachable. Save the complete baseline under `local/`; the bootloader cannot back them up.
2. Compare the selected image's complete EHEX SHA256, build ID, flags and size with its report. Use fresh logs/output paths. A generic patcher report is not interchangeable with a fixed historical regression manifest.
3. Stop a polling master's UART0 traffic before host access to any board. If supported and permitted, start master0 maintenance on UART1, confirm marker0/effective slaves0 with fresh64/02, then confirm physical UART0 silence. If permissions or the initial OEM master prevent this, use the established manual bus/DIP release procedure.
4. Isolate exactly one bootloader target. Bootloader frames contain no pack address; a local/fixed-address flasher is not a multi-pack updater. Use the device tool whose documented assumptions match this topology.

Current applications use UART0 19200; UART1 remains at 9600. The older OEM04.06 application used UART0 9600, but its bootloader rate has not been established. Do not infer bootloader settings for a different image from its application alone. See [bootloader protocol](../../../analysis/protocols/bootloader-update-protocol.md).

## Reset and bootloader entry

Send application reset once to the correct target. Successful reset has no ACK. Full-profile MAINT1.6.3 saves/verifies SOC before reset; recognized save failure returns RTN08 without reset. Abort on that error. Flash-save time is unmeasured, so a single RFL exactly50 ms after reset is not a reliable strategy.

Use bounded read-only RFL probes after the one reset. Fully collect a fragmented reply before another probe. Require valid RFB framing, length/checksum, bootloader address0 and data0100 before any WFE/WFD. A write ACK must be a complete empty WFB; an RFB response is never a write acknowledgement. No automatic reset, erase or program retries. The importable `boot_entry.py` module handles bounded entry through `enter(port, address=N, timeout=3)`; it has no standalone CLI. `flash_gap.py` uses that module and selects the application address with `--address N`. `flash_gap.py PORT IMAGE GAP_MS NEW_LOG --address N` checks a valid51 response, resets and checks application return at addressN (decimal0–21); omitted `--address` retains address0 for compatibility. The bootloader transfer itself still has no pack addressing. Both flash helpers reject invalid/gapped/checksum-invalid EHEX before opening the device and refuse an existing log.

For an already reachable bootloader, use read-only RFL first; no functioning application or additional ASCII reset is required. A valid RFB0100 establishes the known256-byte bootloader. A generic communication error alone does not establish that state. The retained recovery helper requires the independently checked SHA256 of the selected image and a fresh log, validates response length/checksum/content, uses the same stream as the regular local flasher and sends no write retries. Its documented350 ms post-ACK gap is a host policy, not a measured universal flash-time guarantee.

## After programming

Verify the application at its actual DIP address. Query fresh51,47,A2/A4 and64/03 where supported. Compare parameter/SN baseline, exact build ID and flags with the chosen image, including current MNT04/19-byte layout. A sequence of acknowledged bootloader blocks does not replace application verification. Without a pre-flash baseline, parameter preservation cannot be proved.

For a multi-pack bank, restore the application and confirm its identity before proceeding to another isolated target. When all intended work is complete, stop maintenance, confirm markerFFFFFFFF and the expected effective DIP slave count, then confirm normal polling. A clear ACK alone does not prove polling has resumed; allow the full DIP update cycle when the expected count is0.

Before a downgrade from a lock-capable profile, deliberately release any individual lock and verify its persistence: older firmware does not understand that state contract. Restoring parameters or clearing the maintenance marker does not unlock a pack. Enabling configurable hard stop is separate from pack off and requires a fresh47 plus64/03 interpretation.

The current1.5.3 and1.6.3 releases have not been flashed or hardware-tested. Historical inverse1.6 bench/recovery results apply to their exact build and isolated-master conditions, without electrical gate/current or real multi-board evidence. The [changelog](../../firmware/CHANGELOG.md) preserves those qualifications.


## Gateways and interrupted transfers

A host must reassemble fragmented TCP replies, but successful TCP reassembly does not establish contiguous UART transmission. Even one complete TCP write can be packetized or delayed by a gateway. Its serial framing/flush policy and actual bus gaps need separate evidence; transport-buffer boundaries are not UART frame boundaries.

WFB has no block sequence identifier. If a connection fails after transmission, the host may not know whether that block was programmed. A delayed ACK must not be assigned blindly to another block, and an uncertain program operation must not be retried automatically. Historical RFL recovery establishes only its tested entry condition; it does not prove that a bootloader survives every possible power interruption or invalid application.

The retained `flash_gap.py`/`flash_recovery.py` are local serial helpers. A gateway updater must satisfy these additional transport conditions independently. Use fresh logs and [storage/reset semantics](../firmware/storage-and-reset.md) to distinguish a rejected pre-reset checkpoint from an update whose programming outcome is unknown.
