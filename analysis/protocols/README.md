# Communication protocols

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

- [binary display protocol (`0x55 … 0xAA`, UART2)](binary-display-protocol.md)
- [FirmwareUpdate.exe: bootloader protocol and update sequence](bootloader-update-protocol.md)
- [CAN inverter protocols](can.md)
- [response fields that carry a current limit or enable](current-limits-and-enables.md)
- [Intra-Pack Communication (CID2 0x5A)](intra-pack.md)
- [Modbus RTU (inverter port), undocumented](modbus-rtu.md)
- [Pylontech RS485 (ASCII) on the inverter port](pylontech-rs485.md)
- [RS485 ASCII protocol ("MODBUS-ASCII"), reconstructed from the firmware](seplos-ascii.md)
- [UART1 receive gap and buffer ownership](uart1-receive-gap-and-buffer-ownership.md)

The [CAN reference](can.md#manufacturer-can-specification-scope-and-differences) compares the original Seplos CANBUS V1.0 PDF with OEM .13, including heartbeat, alarm fields and the `0x70`/`0x370` discrepancy.

These references cover the original V16.04.06–V16.06.13 images, with version-specific qualifications. UART1 receive ownership also compares the explicitly identified historical MAINT builds; current MAINT service extensions are documented in the [UART write-capability matrix](../../mod/docs/firmware/uart-write-capabilities.md).
