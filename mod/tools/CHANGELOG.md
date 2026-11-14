# Tool changes

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

## Tooling and functional-contract consistency, 2026-11-13

- Function availability starts at Light 1.5.3+ / Full 1.6.3+, with shared remote reads at .4+ and atomic scheduler cleanup at .5+. Earlier development contracts remain in the firmware changelog and local evidence.
- Patcher help uses explicit Light/Full names and the standard 1=enabled permission rule. Source comments and test names describe the supported functions; the control helper example names the actual executable.
- Renamed device tests for storage diagnostics and configurable hard stop. Firmware execution paths, protocol fields and image identities remain unchanged.

## EXT identity and profile API, 2026-11-13

- Current clients and metadata use EMU1101-EXT Light/Full names and exact ASCII EXT/format 05 identity. Archived identity signatures and layouts are rejected; no compatibility decoder is part of the current tools.
- Patcher selection uses required `--ext-version` / API `ext_version` for Light 1.5.4, Light 1.5.5, Full 1.6.4 or Full 1.6.5. Release files are `ext-light.json` and `ext-full.json`, with separate .4 reference metadata.
- Frozen image-bound SOC, UART ownership, address-chain and historical audit probes retain their original bytes and pinned evidence under ignored local history. Current generic OEM probes and the capability renderer remain in the published tool tree.

## Sequential pack flashing, 2026-11-01

- Added `flash_packs.py`: count-based master (0 through N−1) and external (1 through N) address plans, offline by default. Execution pins reviewed release bytes, saves every target baseline before the first reset and verifies exact EMU1101-EXT identity, parameters, serials and retained measurements before advancing.
- Added an exclusive local UART0 transport with strict fragmented-reply/echo handling, extra-response rejection, passive quiet and absent-bootloader checks. Optional distinct UART1 maintenance start is confirmed and never automatically cleared. External requesters must be stopped separately.
- Light downgrade is refused when an existing individual lock is active or its stored/runtime state is uncertain. Errors stop the whole batch without replay, recovery or advancing. Reports retain phase, verified predecessors and maintenance-start ambiguity.
- Extracted `prepare_bytes`/`prepare_image` and `flash_session` from `flash_gap.py`, preserving its CLI and transfer stream. Serial receive deadlines now use monotonic time. `boot_entry.py` and manual isolated-target recovery contracts are unchanged.
- Validation is offline only. The shared-bus batch path and current EMU1101-EXT releases have not been flashed or tested on physical hardware.

## 2.1.0: shared remote diagnostics, 2026-11-01

- Patcher profiles are EMU1101-EXT Light 1.5.4 and EMU1101-EXT Full 1.6.4. Both add addressed UART1 history and UART0/UART1 active/stored calibration, persisted capacity mirrors and full-width live energy reads. Existing profile-specific power, lock and checkpoint behavior remains.
- Identity format 05 adds all four read capabilities in a separate u16 word. Current EXT05 rebuilds retain that layout; the current client rejects archived signatures/layouts. Read-only CLI actions never initiate writes.
- Native guards bind calibration/SOC/history roles and reject unreviewed code shapes. Mandatory native feature groups and publisher checks cover both profiles.
- The matrix renderer reads exact identity and checksums from generic profile metadata. Current files are `ext-light.json` / `ext-full.json` and bind rebuilt EXT05 images; archived raw identities and original manifests remain unchanged in local history.

## 2026-10-28

- The public Markdown checker validates Git-visible relative targets and anchors, rejects ignored private evidence links, and supports an index-path mode. It performs no network or firmware execution.

- Patcher 2.0.0 produces only EMU1101-EXT Light 1.5.3 / EMU1101-EXT Full 1.6.3. Explicit profile selection is required at CLI/worker/builder boundaries; the standard 1=enabled permission semantics apply to every versioned profile. The standalone hard-stop build command is removed.
- Storage diagnostics, service, configurable hard-stop and permission modules/tests use functional names. Retired-profile reproduction tests, their hash fixture, a standalone-only rendering helper and the obsolete capability-renderer alias are removed from active source. The complete prior source remains under ignored local history.
- That tool refactor preserved the tested firmware bytes and runtime semantics; the original exact identities remain in local history.

## 2026-10-27

- The offline knowledge CLI identifies exact applications/containers and indexes bound artifacts, builds, topic notes, historical counterexamples and dependencies. Queries never invoke firmware, LLVM or a serial port.
- The intra-pack fixture verifier checks preserved 0x5A captures, checksums, decoded expectations and source hashes without hardware.

- Research probes use SHA-256/size-bound canonical build inputs. Historical binary fixtures and frozen regression sources are not included in the public checkout.
- Display-format backups use a project-relative private directory independently of the working directory; `--backup-dir` selects an explicit destination.

- The maintenance client accepts canonical `--uart UART0` and `--uart UART1` selectors. Address gates, request frames and physical baud rates retain their existing behavior.
- Capability Markdown displays UART0/UART1/UART2 while JSON output, extracted data and decoder identifiers retain their existing meanings.
- Tool guides distinguish importable boot-entry support, restart return checks and version-bound historical probes from current release verification.

## 2026-10-26

- Firmware comparison rejects missing/empty input, absent start addresses and failed child disassembly commands. Strict input preparation records OEM and LLVM identities.
- The current capability catalogue reads the two public release JSONs without importing historical revisions or loading build reports. The published matrix is generated from its template and checked for exact consistency.
- Flash helpers validate complete EHEX before device access and require new log files. `flash_gap.py --address N` targets application queries/reset/verification at decimal address N (0–21; default 0). Bootloader transfers still require one isolated target.
- Application verification checks reply address and checksum; write acknowledgement requires complete WFB. Valid blocks with byte sums at or above 65535 use modulo-65536 checksum arithmetic. Existing valid image streams and blocks remain unchanged.
- Patcher regression metadata is stored in small, integrity-checked fixtures with provenance. The binary corpus is an explicit size/SHA-256 registry. Current tests do not consume disposable build reports.
- `verify_releases.py` separates retained-image identity verification from an optional actual rebuild and mandatory native test run.
- Historical builders, laboratory exercises and their dependencies require a separately retained archive. `run_historical_tests.py` checks its source inventory and runs only explicitly selected offline suites.
- SOC fixture reuse, display troubleshooting, host framing ambiguity and gateway update limits are documented in the [tool guides](../docs/tools/README.md).

This 2026-10-26 tool-only revision left firmware source and retained OEM/EMU1101-EXT images unchanged. Its tests used synthetic ports and emulated firmware without device access.
