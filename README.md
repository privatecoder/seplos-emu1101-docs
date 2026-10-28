# Seplos BMS 2.0/10E/V16 (EMU1101)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Firmware, protocol and hardware references, reproducible MAINT patches and analysis tools. The analysis covers seven OEM images from 16.04.06 to 16.06.13. The reference for current behavior is 16.06.13 unless another version is stated.

| Directory | Content |
|---|---|
| [vendor/](vendor/) | Original manufacturer firmware, documents and software. |
| [analysis/](analysis/README.md) | OEM firmware behavior, parameters, hardware, topologies, protocols and BatteryMonitor. |
| [mod/](mod/README.md) | Patcher, release metadata, analysis programs, device helpers and MAINT documentation. |
| [references/](references/) | Community and other-vendor references. |

The current patch alternatives are [MAINT 1.5.3](mod/docs/firmware/maint153-positive-power.md) and [MAINT 1.6.3](mod/docs/firmware/maint163-configurable-hard-stop.md). The [capability matrix](mod/docs/firmware/uart-write-capabilities.md) compares them with OEM 16.06.13. The [firmware changelog](mod/firmware/CHANGELOG.md) records their behavior and build identities.

**Test status:** MAINT 1.5.3 and 1.6.3 have been validated offline, including native Cortex-M0 emulation and byte-identical rebuilds. Neither current release has been flashed or tested on hardware. See the [release metadata](mod/firmware/releases/README.md) and [validation limits](mod/docs/firmware/validation-methods-and-limits.md).

**Experimental firmware:** Incorrect firmware, wiring or an interrupted update can render a BMS unusable and compromise battery protection. Use at your own risk. The project is provided "AS IS", without warranty, under the terms of the [license](LICENSE).

The MAINT release directory publishes metadata and checksums; prebuilt MAINT firmware images are not included. Create patched images from compatible OEM inputs using the [build instructions](mod/docs/firmware/build-and-validation.md).

1. Check [ports, protocols and bus ownership](analysis/hardware/ports-and-topologies.md) for the intended inverter and monitor connections.
2. Follow [build and validation](mod/docs/firmware/build-and-validation.md) to prepare the environment, select a profile and verify the image.
3. Read the [flashing and recovery procedure](mod/docs/tools/flashing.md) before programming a board. Firmware updates use UART0.

[OpenBMS Monitor](https://github.com/privatecoder/openbms-monitor) is the companion monitoring and management application. The [integration contract](mod/docs/firmware/openbms-monitor.md) defines how it uses the patched firmware's addressing, parameters and capabilities.

Project-authored code and documentation are licensed under the [MIT License](LICENSE). Manufacturer and other third-party material, including `vendor/`, `references/` and OEM portions of firmware images, is outside this grant and is not relicensed by this project.

Original vendor images remain unchanged. Code-derived findings, manufacturer specifications and hardware assumptions are distinguished in the references. Firmware status is not an electrical isolation measurement. The project is unofficial and is not affiliated with Seplos or SH Energy.
