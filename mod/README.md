# Seplos BMS 2.0/10E/V16 (EMU1101) modifications

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The offline patcher builds cumulative MAINT firmware directly from compatible OEM images. MAINT **1.5.3** provides addressed parameter and identity access, maintenance services, positive UART1 power/RTC permission and storage diagnostics. MAINT **1.6.3** also provides a persistent individual pack lock, verified SOC saving before planned reset and configurable recharge-waiting hard stop. Both current profiles use Group0.bit3=1 to permit UART1 power/RTC.

| Location | Contents |
|---|---|
| [firmware/patcher](firmware/patcher/README.md) | Patcher, assembler, emulator and tests |
| [firmware/releases](firmware/releases/README.md) | Public release identifiers, checksums and capabilities |
| [firmware/CHANGELOG.md](firmware/CHANGELOG.md) | Complete release history |
| [docs/firmware](docs/firmware/README.md) | Current byte contracts, access matrix and build instructions |
| [docs/tools](docs/tools/README.md) | Analysis and device command usage |
| [tools/firmware-analysis](tools/firmware-analysis/README.md) | Reusable offline analysis and emulation |
| [tools/device](tools/device/README.md) | Clients and device operations |

Firmware updates use UART0. Query each board independently; the same image supports master and slaves.

OEM knowledge belongs in [analysis](../analysis/README.md), original inputs in [vendor firmware](../vendor/firmware/), and published release identities in [firmware/releases](firmware/releases/README.md). Generated patch binaries, private configuration exports, captures and historical laboratory records are not published. The release directory contains metadata and reproduction instructions.

The current profiles have offline execution evidence and have not been flashed or hardware-tested. Historical hardware results apply only to their identified builds and test conditions. Start with [build and validation](docs/firmware/build-and-validation.md), then follow the [flash procedure](docs/tools/flashing.md) for the chosen device and image.

Current tests consume explicit integrity-checked metadata and binary registries. Frozen source, chained builders and laboratory test dependencies are retained privately and are not included in a public checkout. The [historical runner](tools/run_historical_tests.py) lists their prerequisites or executes explicit suites when those private inputs are available. Research probes may deliberately bind an exact historical image and are documented separately from current release validation.
