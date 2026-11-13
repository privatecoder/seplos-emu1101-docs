# EMU1101-EXT release metadata

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Current release identities refer to exact OEM 16.06.13-based images. The [changelog](../CHANGELOG.md) records functional history; original raw identities, checksums and reports remain in ignored local archives.

| Profile | Metadata | Build ID | Mandatory groups |
|---|---|---|---:|
| EMU1101-EXT Light 1.5.4 | [references/ext-light.json](references/ext-light.json) | `ffe3acf7e52bed80` | 251 |
| EMU1101-EXT Full 1.6.4 | [references/ext-full.json](references/ext-full.json) | `4f4d2715c9ee553c` | 333 |
| EMU1101-EXT Light 1.5.5 | [ext-light.json](ext-light.json) | `082cb731c006aac5` | 257 |
| EMU1101-EXT Full 1.6.5 | [ext-full.json](ext-full.json) | `13464fc91a6e6a20` | 339 |

Light and Full inherit basic access, power/RTC access control and storage diagnostics from their first versioned releases, Light 1.5.3 and Full 1.6.3. Full 1.6.3 additionally provides persistent pack lock, a verified checkpoint before planned reset and configurable hard stop. Shared history/calibration/persisted-capacity/live-energy reads start at Light 1.5.4 and Full 1.6.4. See [feature availability](../../docs/firmware/README.md#feature-availability).

The atomic scheduler cleanup fix is available from Light 1.5.5+ / Full 1.6.5+: a short saved-PRIMASK read/modify/write preserves the reproduced wake flag update. They use six/22 guarded hooks and zero/four bytes of persistent RAM. The [reference manifests](references/README.md) bind the exact EXT05 Light 1.5.4/Full 1.6.4 reference identities and their current mandatory test counts.

These JSONs are the identity authorities. The [generated matrix](../../docs/firmware/uart-write-capabilities.md) reads their version, build ID, flags and checksums directly.

Each JSON includes the literal image filename, complete EHEX SHA256, decoded application SHA256, sizes and available capability identifiers. An EHEX checksum is different from an application checksum.

All four EXT05 images have offline evidence only and were not flashed or hardware-tested. The results establish no electrical gate/current behavior or physical multi-board guarantee.

For reproduction, use the [build procedure](../../docs/firmware/build-and-validation.md), the exact OEM source and the declared base revision. Compare both output hashes, 64/03 payload, build ID, sizes and required test results with the selected metadata. A different OEM input, declared revision, profile or hard-stop option can produce another build ID and checksum. Current builds are EMU1101-EXT Light 1.5.5 and EMU1101-EXT Full 1.6.5; explicit Light 1.5.4/Full 1.6.4 reference builders remain available. The permission rule is fixed throughout the versioned releases; no historical binary path is required by the patcher.

The [corpus registry](../patcher/corpus.json) binds exact inputs for compatibility and already-patched-input refusal checks. These fixtures do not extend the four supported output versions.

[Current contracts](../../docs/firmware/README.md) · [Complete changelog](../CHANGELOG.md)
