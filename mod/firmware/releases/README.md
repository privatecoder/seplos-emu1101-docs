# EMU1101-EXT release metadata

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Current profiles are **Light 1.5.6** and **Full 1.6.7**. These identities bind exact OEM 16.06.13-based images. The patcher also reproduces Light 1.5.4/1.5.5 and Full 1.6.4/1.6.5/1.6.6 reference images unchanged.

| Profile | Metadata | Build ID | Mandatory groups |
|---|---|---|---:|
| EMU1101-EXT Light 1.5.4 | [references/ext-light.json](references/ext-light.json) | `ffe3acf7e52bed80` | 251 |
| EMU1101-EXT Full 1.6.4 | [references/ext-full.json](references/ext-full.json) | `4f4d2715c9ee553c` | 333 |
| EMU1101-EXT Light 1.5.5 | [references/ext-light-1.5.5.json](references/ext-light-1.5.5.json) | `082cb731c006aac5` | 257 |
| EMU1101-EXT Full 1.6.5 | [references/ext-full-1.6.5.json](references/ext-full-1.6.5.json) | `13464fc91a6e6a20` | 339 |
| EMU1101-EXT Light 1.5.6 | [ext-light.json](ext-light.json) | `fe7cba82f861f337` | 269 |
| EMU1101-EXT Full 1.6.6 | [references/ext-full-1.6.6.json](references/ext-full-1.6.6.json) | `2508b93f45c29f31` | 351 |
| EMU1101-EXT Full 1.6.7 | [ext-full.json](ext-full.json) | `f445666c205184a8` | 360 |

Light and Full inherit basic access, power/RTC access control and storage diagnostics from Light 1.5.3 and Full 1.6.3. Full 1.6.3 additionally provides persistent pack lock, a verified checkpoint before planned reset and configurable hard stop. Shared history/calibration/persisted-capacity/live-energy reads start at Light 1.5.4 / Full 1.6.4. Atomic scheduler cleanup starts at Light 1.5.5 / Full 1.6.5.

[Early UART0 polling completion](../../docs/firmware/early-polling.md) starts at Light 1.5.6 / Full 1.6.6. The current images have eight/25 guarded hooks and zero/four bytes of additional persistent RAM. EXT05 remains 21 bytes with the existing image flags; Light uses capability mask `000F` and Full 1.6.7 uses `001F`; no parameter migration is needed. See [feature availability](../../docs/firmware/README.md#feature-availability).

[Configurable downward CCL](../../docs/firmware/configurable-ccl-ramp.md) starts at Full 1.6.7: 1–20 A per online pack per update, default 1, fixed upward factor 1. Light 1.5.6 remains unchanged.

These JSONs are the identity authorities. Each includes the literal image filename, complete EHEX SHA-256, decoded application SHA-256, sizes, test count and capability identifiers. EHEX and application hashes identify different byte sequences. The [generated matrix](../../docs/firmware/uart-write-capabilities.md) reads the current identities directly.

All seven EXT05 images have offline evidence only and were not flashed or hardware-tested. The results establish no electrical gate/current behavior or physical multi-board guarantee.

For reproduction, use the [build procedure](../../docs/firmware/build-and-validation.md), exact OEM source and declared base revision. Compare both output hashes, 64/03 payload, build ID, sizes and mandatory test results with the selected metadata. A different OEM input, declared revision, profile or hard-stop option can produce another build ID and checksum. Current source guards require the reviewed OEM 16.06.13 polling contracts; older profiles retain their documented broader source compatibility.

The [corpus registry](../patcher/corpus.json) binds exact compatibility and already-patched-input refusal fixtures. These fixtures do not extend the seven supported output versions.

[Reference metadata](references/README.md) · [Current contracts](../../docs/firmware/README.md) · [Changelog](../CHANGELOG.md)
