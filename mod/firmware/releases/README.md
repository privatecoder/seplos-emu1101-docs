# MAINT release metadata

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101) current release identities refer to exact OEM 16.06.13-based images. Historical identifiers, checksums and release facts remain in the [changelog](../CHANGELOG.md) and unchanged local manifests.

- [MAINT 1.5.3](maint153-positive-power.json): lightweight profile with positive UART1 power/RTC permission and storage diagnostics.
- [MAINT 1.6.3](maint163-configurable-hard-stop.json): full profile with persistent individual lock, verified SOC checkpoint before reset and configurable hard stop.

These JSONs are the identity authorities. The [generated matrix](../../docs/firmware/uart-write-capabilities.md) reads their version, build ID, flags and checksums directly.

Each JSON includes the literal image filename, complete EHEX SHA256, decoded application SHA256, sizes and available capability identifiers. Actual images and full manifests remain in project-relative `local/releases`; generated build reports and resolved assembler remain in `local/builds`. There are no firmware binaries or binary symlinks in this directory. An EHEX checksum is different from an application checksum.

The current 1.5.3 and 1.6.3 releases have offline evidence only and were not flashed or hardware-tested. Historical inverse-polarity 1.6 bench evidence covered an isolated master at address0 without polling or slaves; it established no electrical gate/current result or multi-board guarantee.

For reproduction, use the [build procedure](../../docs/firmware/build-and-validation.md), the exact OEM source and the declared base revision. Compare both output hashes, 64/03 payload, build ID, sizes and required test results with the selected metadata. A different OEM input, declared revision, profile or hard-stop option can produce another build ID and checksum. Only MAINT1.5.3 and MAINT1.6.3 can be built. Permission polarity is intrinsic; no historical binary path is required by the patcher.

The fixed ACCESS regression input has its own hash/size entry in [the corpus registry](../patcher/corpus.json); its historical identity is not a current release guarantee. Test historical images within their named scope and probe each board independently.

[Current contracts](../../docs/firmware/README.md) · [Complete changelog](../CHANGELOG.md)
