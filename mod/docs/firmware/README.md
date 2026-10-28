# MAINT firmware contracts

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101) current profiles:

- [MAINT 1.5.3](maint153-positive-power.md): lightweight diagnostics and positive UART1 power/RTC permission.
- [MAINT 1.6.3](maint163-configurable-hard-stop.md): persistent pack lock, verified reset and configurable hard stop.
- [UART capability matrix](uart-write-capabilities.md): all read, write and action paths on UART0/UART1/UART2.
- [OpenBMS Monitor integration](openbms-monitor.md): transport, addressing, firmware identity, parameters, power and maintenance.
- [Storage diagnostics and planned reset](storage-and-reset.md): exact 64/04 layout, mirror classification and reset failure handling.
- [Build and validation](build-and-validation.md): environment, profiles, output and verification limits.
- [Validation methods and limits](validation-methods-and-limits.md): current checks and separate historical probe scope.

[Release metadata](../../firmware/releases/README.md) binds exact images to checksums and build IDs. [Release history](../../firmware/CHANGELOG.md) records version differences. OEM parameters and protocols remain in [analysis](../../../analysis/README.md).
