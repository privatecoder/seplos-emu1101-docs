# Tool changes

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

## 2026-10-28

- Patcher2.0.0 produces only MAINT1.5.3 and1.6.3. Explicit profile selection is required at CLI/worker/builder boundaries; positive permission polarity is automatic. The separate polarity option and standalone hard-stop build command are removed.
- Storage diagnostics, service, configurable hard-stop and permission modules/tests use functional names. Retired-profile reproduction tests, their hash fixture, a standalone-only rendering helper and the obsolete capability-renderer alias are removed from active source. The complete prior source remains under ignored local history.
- Current firmware bytes, build IDs, capability flags and runtime parameter semantics are unchanged. Both profiles are rebuilt and checked against the retained EHEX and application SHA256 identities.

## 2026-10-27

- The offline knowledge CLI identifies exact applications/containers and indexes bound artifacts, builds, topic notes, historical counterexamples and dependencies. Queries never invoke firmware, LLVM or a serial port.
- The intra-pack fixture verifier checks preserved 0x5A captures, checksums, decoded expectations and source hashes without hardware.

- Research probes use SHA-256/size-bound canonical build inputs. The binary corpus now resides in `local/fixtures/corpus`; the frozen regression workspace is in `local/history/snapshots`.
- Display-format backups default to `local/devices/backups/parameters`, independently of the working directory.

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
- Frozen builders, laboratory exercises and their dependencies remain under ignored `local/`. `run_historical_tests.py` checks the frozen source inventory and runs only explicitly selected offline suites.
- SOC fixture reuse, display troubleshooting, host framing ambiguity and gateway update limits are documented in the [tool guides](../docs/tools/README.md).

Firmware source and retained OEM/MAINT binaries are unchanged. Tests use synthetic ports and emulated firmware; no device is accessed.
