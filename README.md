# Seplos BMS 2.0/10E/V16 (EMU1101)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Firmware, protocol and hardware references, reproducible MAINT patches and local tools. The analysis covers seven OEM images from 16.04.06 to 16.06.13. The reference for current behavior is 16.06.13 unless another version is stated.

| Directory | Content |
|---|---|
| [vendor/](vendor/) | Original manufacturer firmware, documents and software. |
| [analysis/](analysis/README.md) | OEM firmware behavior, parameters, hardware, topologies, protocols and BatteryMonitor. |
| [mod/](mod/README.md) | Patcher, release metadata, analysis programs, device helpers and MAINT documentation. |
| [references/](references/) | Community and other-vendor references. |

The current patch alternatives are [MAINT1.5.3](mod/docs/firmware/maint153-positive-power.md) and [MAINT1.6.3](mod/docs/firmware/maint163-configurable-hard-stop.md). The [capability matrix](mod/docs/firmware/uart-write-capabilities.md) compares them with OEM16.06.13. The [firmware changelog](mod/firmware/CHANGELOG.md), [OpenBMS Monitor contract](mod/docs/firmware/openbms-monitor.md) and [build instructions](mod/docs/firmware/build-and-validation.md) define their behavior, identification and reproducibility.

[Ports and topologies](analysis/hardware/ports-and-topologies.md) describe which inverter and monitor connections can coexist and when a bus must be idle. The interface definitions above distinguish the shared UART0 pack bus from UART1 and the actual CAN wires.

Original vendor images remain unchanged. Generated patch binaries, private configuration exports, laboratory captures, build results and historical working material are kept under the ignored `local/` directory. The public release directory contains metadata and reproduction instructions; actual images remain in `local/releases/`.

The ignored [local knowledge library](local/README.md) indexes exact image identities, reusable artifacts, complete build bundles, topic evidence and frozen emulator inputs. The [offline lookup guide](mod/docs/tools/knowledge-library.md) provides commands for reusing those findings and identifying new firmware.

Code-derived findings, manufacturer specifications and hardware assumptions are distinguished in the references. Firmware status is not an electrical isolation measurement. The project is unofficial and is not affiliated with Seplos or SH Energy.
