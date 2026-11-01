# Device tools

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Choose adapters explicitly;
there is no installation-specific serial-port default. Run `--help` offline
before selecting the operation and transport.

```sh
PROJECT='/path/to/Seplos V2 10E BMS'
SEPLOS_PY="$HOME/.local/share/seplos-firmware-tools/venv/bin/python"
DEVICE="$PROJECT/mod/tools/device"
cd /private/tmp
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" info --uart UART0 --address 7
"$SEPLOS_PY" -I -B "$DEVICE/parameter_client.py" read --address 7
"$SEPLOS_PY" -I -B "$DEVICE/identity_client.py" --address 7
"$SEPLOS_PY" -I -B "$DEVICE/restart_pack.py" 07 --dry-run
```

These examples produce request frames without transport access. Actual client
I/O requires `--serial DEVICE` or `--tcp HOST:PORT`; device operations using
`--port` require an explicitly selected adapter. UART0 uses RS485-1/2 at 19200;
UART1 uses the RS485 pair in the CAN socket at 9600. Coordinate bus ownership
and pause UART0 master polling before host access to master or slaves.

| Command | Behavior |
|---|---|
| `maintenance_client.py` | Marker status/start/stop, MNT02/03/04/05 info, addressed history, calibration and checkpoint/live-energy snapshots; POSIX serial/TCP, standard library. It never sends reset or bootloader commands. |
| `parameter_client.py` | Addressed 47/A1 over serial/TCP, E3 rejection and full readback. Serial requires pyserial 3.5. |
| `identity_client.py` | Addressed A2/A4 using the parameter client's transports. |
| `restart-pack` / `restart_pack.py ADDRESS --port DEVICE` | One addressed UART0 reset; confirm an outage and identical version/BMS serial on return. No ACK for reset, no automatic reset retry. Optional `--dry-run` needs no port or pyserial. |
| `display-format` / `display_format.py ADDRESS MODE --port DEVICE` | `kurz` means short format, `erweitert` extended format, `status` read-only. Changes only Group7.Bit4; preserves display enable and other parameters. |
| `seplos_query.py PORT BAUD ADR_HEX CID2_HEX [INFO_HEX]` | One allowlisted read-only ASCII command. |
| `control.py PORT ADR_HEX TYPE_HEX PARAM_HEX` | One raw UART0 45 control frame for an isolated bench; can change power/state, clear history or restart depending on arguments. |
| `monitor.py SECONDS --port DEVICE`, `wait_and_read.sh PORT` | Read-only query monitoring using the script-relative query helper. |
| `flash_packs.py COUNT --mode master/external --profile light/full` | Offline plan by default. With `--execute --port DEVICE`, backs up all targets and updates them one by one with exact MAINT/parameter/SN checks; stops on the first error. Optional distinct UART1 `--maintenance-port` can pause master 0. See [sequential flashing](../../docs/tools/batch-flashing.md). |
| `flash_gap.py PORT IMAGE GAP_MS NEW_LOG --address N` | Addressed application reset/verification (decimal N, 0–21; default 0), strict image validation before opening the port, exclusive new log and original 256-byte bootloader blocks with configurable ACK gap. One reset, bounded bootloader entry, abort on invalid ACK, no write replay. |
| `flash_recovery.py PORT IMAGE EXPECTED_SHA256 NEW_LOG` | Recover a bootloader already answering RFL, without an application reset. Verify image hash, all outgoing frames and all replies. Requires one isolated pack because the bootloader has no pack addressing. |
| `boot_entry.py` | Importable module: `enter(port, address=N, timeout=3)` sends one reset and repeats only read-only RFL probes. No standalone CLI or erase/program operation. |

Batch count 12 means addresses 0–11 with `--mode master` and 1–12 with `--mode external`. An active maintenance marker leaves master address 0 unchanged. The batch uses one exclusive UART0 descriptor; `flash_gap.prepare_bytes` pins the reviewed input and `flash_gap.flash_session` reuses the one-reset/ACK procedure. Recovery remains manual for an isolated target.

`restart_pack.py` accepts decimal addresses 0–15. It compares command 51 and raw A4 data and requires an observed outage before declaring return. It does not query the MAINT build ID, verify the SOC checkpoint or explicitly decode a reset RTN08; use a checkpoint-aware host for that workflow. A failed return check leaves the action outcome unconfirmed.

Display changes save a fresh pre-write snapshot and guard against the OEM A1
capacity side effect: a difference of at least 10 Ah between learned capacity
and P58 aborts. A second parameter read detects intervening changes. ACK plus
full readback confirms active state; the tool performs no extra reset to claim
persistence and never retries an uncertain write. Backups default to ignored
`local/devices/backups/parameters`; `--backup-dir` selects another directory.

The shell wrappers use `SEPLOS_TOOLS_PY`, or the existing
`~/.local/share/seplos-firmware-tools/venv/bin/python` by default. That device
environment must contain pyserial 3.5 and Unicorn 2.1.4. The separate patcher venv
contains Unicorn but no pyserial. Use `SEPLOS_TOOLS_PY` to select another
prepared interpreter. Dependencies are listed in
[requirements-serial.txt](requirements-serial.txt); no packages are installed
automatically. POSIX serial clients and flash codecs use the standard library.

[Flash and tool documentation](../../docs/tools/README.md),
[capabilities](../../docs/firmware/uart-write-capabilities.md), and
[storage/reset contract](../../docs/firmware/storage-and-reset.md) describe the
version and persistence boundaries.

## Read-only remote diagnostics

MAINT 1.5.4/1.6.4 advertise the four reads through the MNT05 capability mask,
not through version inference. Read fresh `info` for each addressed board.
Historical MNT03/MNT04 decoding remains supported; it grants none of the new
capabilities. The [wire contract](../../docs/firmware/remote-diagnostics.md)
defines exact layouts, units, errors and limits.

```sh
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" info --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" history-oldest --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" history-next --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" calibration-active --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" calibration-primary --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" calibration-backup --address 7
"$SEPLOS_PY" -I -B "$DEVICE/maintenance_client.py" checkpoint-energy --address 7
```

These commands print one request offline. Add `--serial DEVICE` or
`--tcp HOST:PORT` explicitly to send one request; `--uart UART0` selects the
UART0 transport and baud. No read starts a download loop, calibration action,
mirror repair, checkpoint save or reset. Each successful read prints JSON.
`parse_history`, `parse_calibration` and `parse_checkpoint_energy` are also
importable offline decoders. Erased/invalid stored records preserve raw hex;
expected decoded fields are `null`. Native CRC acceptance is independent of
strict record shape and does not establish physical calibration accuracy.

History uses the shared UART0/UART1 cursor. Coordinate readers; concurrent
record creation means a download is not an atomic ring snapshot. The firmware
restores the cursor after a reported EEPROM read failure, but an unanswered
request can already have advanced it. Do not blindly retry `history-next` on
transport ambiguity. Calibration and checkpoint/live energy are snapshots;
a later automatic save can change the next-boot checkpoint.

## Offline regression checks

```sh
"$SEPLOS_PY" -I -B -m unittest discover -s "$DEVICE/tests" -v
```

The current suite uses mocks and synthetic complete flash logs. It opens no serial port or TCP connection. It does not depend on the historical laboratory profile manifests or chained builders.

## Historical builders and laboratory work

The complete frozen source tree, its five chained builders, fixed emulator, laboratory exercises and their tests remain under ignored `local/history/snapshots/mod-before-current-cleanup-2026-10-26/project/mod`. Their source inventory is checked before execution. They are not current release builders; their exact image/data prerequisites and limitations still apply. The [historical runner](../run_historical_tests.py) lists requirements without running a suite:

```sh
"$SEPLOS_PY" -I -B "$PROJECT/mod/tools/run_historical_tests.py" --list
"$SEPLOS_PY" -I -B "$PROJECT/mod/tools/run_historical_tests.py" \
  --suite all --out /private/tmp/seplos-historical-new
```

`--suite legacy`, `device` or `patcher` selects one group. Each historical builder suite runs in its own process to avoid module-name collisions. The runner uses a neutral working directory, produces fresh logs and reports, verifies positive test counts, and opens no devices. It never grants native execution permissions itself. [Current firmware builds](../../firmware/patcher/README.md) use the maintained patcher.
