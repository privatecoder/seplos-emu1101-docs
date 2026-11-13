# EMU1101-EXT firmware contracts

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT means **EMU1101 Extended Firmware**. Custom firmware for Seplos
BMS 2.0 (EMU1101, hardware V16). EMU1101 identifies the OEM platform independently
of product generation and hardware revision. EXT covers access control,
diagnostics, persistence and correctness fixes, including future extensions.

Current published profiles are **Light 1.5.5** and **Full 1.6.5**. Firmware contracts:

- [EMU1101-EXT Light 1.5.3 and later](ext-light.md): lightweight diagnostics and UART1 power/RTC access control.
- [EMU1101-EXT Full 1.6.3 and later](ext-full.md): persistent pack lock, verified reset and configurable hard stop.
- [UART capability matrix](uart-write-capabilities.md): all read, write and action paths on UART0/UART1/UART2.
- [EMU1101-EXT version comparison](ext-version-comparison.md): release differences for identical flag values, queries and reset conditions.
- [OpenBMS Monitor integration](openbms-monitor.md): transport, addressing, firmware identity, parameters, power and maintenance.
- [Remote diagnostics](remote-diagnostics.md): EXT05 capabilities, one-record history, active/stored calibration and persisted-capacity/live-energy snapshots.
- [Storage diagnostics and planned reset](storage-and-reset.md): exact 64/04 layout, mirror classification and reset failure handling.
- [Build and validation](build-and-validation.md): environment, profiles, output and verification limits.
- [Validation methods and limits](validation-methods-and-limits.md): current checks and separate historical probe scope.

## Feature availability

Versioned Light releases start at 1.5.3; versioned Full releases start at 1.6.3. Every versioned release uses 1=enabled and 0=denied for permissions. The table gives the first versioned release containing each function. The [changelog](../../firmware/CHANGELOG.md) records development history.

| Feature | First Light release | First Full release |
|---|---|---|
| Addressed UART1 parameters and serial identity; maintenance services | 1.5.3 | 1.6.3 |
| Addressed firmware identity; UART0 marker status/clear | 1.5.3 | 1.6.3 |
| UART1 power/RTC access control | 1.5.3 | 1.6.3 |
| Read-only parameter/SOC storage diagnostics, 64/04 | 1.5.3 | 1.6.3 |
| Persistent individual pack lock, extended off and CCL clamp | Unavailable | 1.6.3 |
| Verified SOC checkpoint before targeted planned reset | Unavailable | 1.6.3 |
| Stored configurable recharge-waiting hard stop | Unavailable; static image option only | 1.6.3 |
| Addressed UART1 history, 4B | 1.5.4 | 1.6.4 |
| Active/stored calibration reads, 64/05 | 1.5.4 | 1.6.4 |
| Persisted capacity/SOC contents and full-width live energy, 64/06 | 1.5.4 | 1.6.4 |
| Atomic scheduler cleanup preserving the controlled wake update | 1.5.5 | 1.6.5 |

Later releases retain these functions within their branch. Capability discovery and exact image identity remain necessary: current clients require the EXT signature, format 05 and the exact 21-byte identity layout. The published patcher builds only Light 1.5.4/1.5.5 and Full 1.6.4/1.6.5. Current image filenames, build IDs, hashes and test counts describe those concrete builds rather than the introduction of inherited functions.

[Release metadata](../../firmware/releases/README.md) binds exact images to checksums and build IDs. [Release history](../../firmware/CHANGELOG.md) records version differences. OEM parameters and protocols remain in [analysis](../../../analysis/README.md).
