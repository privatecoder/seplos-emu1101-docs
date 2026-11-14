# BMS modifications

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT (EMU1101 Extended Firmware). Custom firmware for Seplos BMS 2.0 (EMU1101, hardware V16).

The offline patcher builds cumulative EMU1101-EXT firmware directly from compatible OEM images. Current profiles are **Light 1.5.6** and **Full 1.6.7**.

Addressed parameter/identity access, maintenance, UART0 marker access, UART1 power/RTC access control and storage diagnostics are available from Light 1.5.3 and Full 1.6.3. Full 1.6.3 also provides persistent individual pack lock, verified SOC saving before planned reset and configurable recharge-waiting hard stop. Shared history, active/stored calibration and persisted-capacity/live-energy reads start at Light 1.5.4 and Full 1.6.4. The atomic scheduler fix starts at Light 1.5.5 and Full 1.6.5. Validated early UART0 poll completion starts at Light 1.5.6 and Full 1.6.6. Full 1.6.7 adds a [separate numeric EXT setting](docs/firmware/configurable-ccl-ramp.md) for downward CCL steps of 1–20 A per online pack per update, default 1, with a fixed upward step of 1. The normal application workflow configures the master and excludes the field from OEM parameter replication. See [feature availability](docs/firmware/README.md#feature-availability).

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

Current profiles passed their mandatory offline execution suites (see the exact group counts in the [release metadata](firmware/releases/README.md)) and rebuilt byte-identically. They have not been flashed or hardware-tested. Historical hardware results apply only to their identified builds and test conditions. Start with [build and validation](docs/firmware/build-and-validation.md), then follow the [flash procedure](docs/tools/flashing.md) for the chosen device and image.

Current tests consume explicit integrity-checked metadata and binary registries. Frozen source, chained builders and laboratory test dependencies are retained privately and are not included in a public checkout. The [historical runner](tools/run_historical_tests.py) lists their prerequisites or executes explicit suites when those private inputs are available. Research probes may deliberately bind an exact historical image and are documented separately from current release validation.
