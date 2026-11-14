# Seplos BMS 2.0 (EMU1101, hardware V16)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

| Identification field | Reference value |
|---|---|
| Seplos product generation | BMS 2.0 |
| OEM platform | EMU1101 |
| Product variant | 1101-10E |
| Hardware version | V16 |
| OEM reference firmware | 16.06.13 |

[Product identification and supporting evidence](analysis/hardware/product-identification.md)
separate the Seplos generation, product option code, board version and firmware.

EMU1101-EXT (EMU1101 Extended Firmware). Custom firmware for Seplos BMS 2.0 (EMU1101, hardware V16).

Firmware, protocol and hardware references, reproducible patches and analysis tools. The analysis covers seven OEM images from 16.04.06 to 16.06.13. The reference for current behavior is 16.06.13 unless another version is stated.

| Directory | Content |
|---|---|
| [vendor/](vendor/) | Original manufacturer firmware, documents and software. |
| [analysis/](analysis/README.md) | OEM firmware behavior, parameters, hardware, topologies, protocols and BatteryMonitor. |
| [mod/](mod/README.md) | Patcher, release metadata, analysis programs, device helpers and EMU1101-EXT documentation. |
| [references/](references/) | Community and other-vendor references. |

The current patch alternatives are [EMU1101-EXT Light 1.5.6](mod/docs/firmware/ext-light.md) and [EMU1101-EXT Full 1.6.7](mod/docs/firmware/ext-full.md). The [capability matrix](mod/docs/firmware/uart-write-capabilities.md) compares them with OEM 16.06.13. Versioned functionality begins at Light 1.5.3 and Full 1.6.3, including 1=enabled permissions, addressed access, maintenance, identity and storage diagnostics; Full additionally includes the persistent pack lock, planned-reset checkpoint and configurable hard-stop policy from 1.6.3. Addressed history, active/stored calibration and persisted-capacity/live-energy reads are available from Light 1.5.4 and Full 1.6.4. Atomic scheduler cleanup is available from Light 1.5.5 and Full 1.6.5. Early valid-response completion of UART0 master polls is available from Light 1.5.6 / Full 1.6.6. Full 1.6.7 adds a [persistent downward CCL step](mod/docs/firmware/configurable-ccl-ramp.md), integer 1–20 A per online pack per aggregate update, default 1; the upward step stays fixed at 1. This is a separate master-effective EXT setting outside the OEM parameter block and pack replication. Published builders support Light 1.5.4/1.5.5/1.5.6 and Full 1.6.4/1.6.5/1.6.6/1.6.7. The [feature availability table](mod/docs/firmware/README.md#feature-availability) identifies the first versioned release for each function. The [firmware changelog](mod/firmware/CHANGELOG.md) records their behavior and build identities.

[Calculated timing and operating examples](mod/docs/firmware/early-polling.md#calculated-timing-across-firmware-versions) distinguish update counts from conditional elapsed-time estimates and physical inverter response.

**Test status:** EMU1101-EXT Light 1.5.6 passed 269 mandatory native execution groups and EMU1101-EXT Full 1.6.7 passed 360; both rebuilt byte-identically. Neither current profile has been flashed or tested on hardware. See the [release metadata](mod/firmware/releases/README.md) and [validation limits](mod/docs/firmware/validation-methods-and-limits.md).

**Experimental firmware:** Incorrect firmware, wiring or an interrupted update can render a BMS unusable and compromise battery protection. Use at your own risk. The project is provided "AS IS", without warranty, under the terms of the [license](LICENSE).

The EMU1101-EXT release directory publishes metadata and checksums; prebuilt EMU1101-EXT firmware images are not included. Create patched images from the included compatible OEM inputs using the [build instructions](mod/docs/firmware/build-and-validation.md) and select a private output directory with `--out`. Building a supported profile includes its mandatory tests and does not require private research archives. The separate complete historical corpus check requires additional regression images that are not distributed.

1. Check [ports, protocols and bus ownership](analysis/hardware/ports-and-topologies.md) for the intended inverter and monitor connections.
2. Follow [build and validation](mod/docs/firmware/build-and-validation.md) to prepare the environment, select a profile and verify the image.
3. Read the [flashing and recovery procedure](mod/docs/tools/flashing.md) before programming a board. Firmware updates use UART0.

[OpenBMS Monitor](https://github.com/privatecoder/openbms-monitor) is the companion monitoring and management application. The [integration contract](mod/docs/firmware/openbms-monitor.md) defines how it uses the patched firmware's addressing, parameters and capabilities.

Project-authored code and documentation are licensed under the [MIT License](LICENSE). Manufacturer and other third-party material, including `vendor/`, `references/` and OEM portions of firmware images, is outside this grant and is not relicensed by this project.

Original vendor images remain unchanged. Code-derived findings, manufacturer specifications and hardware assumptions are distinguished in the references. Firmware status is not an electrical isolation measurement. The project is unofficial and is not affiliated with Seplos or SH Energy.
