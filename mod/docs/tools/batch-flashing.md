# Sequential pack flashing

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

`flash_packs.py` updates a declared set of packs over a local USB–RS485 adapter on UART0 at 19200 baud. It uses the existing `flash_gap.py` transfer and `boot_entry.py` entry procedure, then verifies each target before proceeding. The target must match one of the two current [release metadata files](../../firmware/releases/README.md). `--profile light` selects MAINT 1.5.4; `--profile full` selects MAINT 1.6.4. `--image PATH` may select another copy of the exact same release bytes; it does not permit arbitrary firmware.

The default invocation only prints an offline plan. **Only `--execute` opens serial ports or performs device operations.** The tool has no TCP transport and never automatically restores parameters, unlocks a pack, clears maintenance, retries a write or invokes recovery.

## Count, addresses and marker

| Mode | Meaning of count N | Example with 12 | Maximum count |
|---|---|---|---:|
| `--mode master` | Seplos master plus its slaves; addresses 0 through N−1 | 0, 1, …, 11 | 16 |
| `--mode external` | Only slaves, queried by an external PC/inverter; addresses 1 through N | 1, 2, …, 12 | 15 |

Count includes the master in master mode. Pack addresses are decimal, not hexadecimal. Transfers proceed in ascending address order, including address 0 first in master mode. Automatic addressing (`Group7.Bit5`) must be disabled on every target.

**An active maintenance marker does not change the master's address: it stays 0.** The patch only forces its effective slave count to zero and stops its polling. A paused master is still queried and reset at address 0.

## Bus conditions

The application reset selects an address; the bootloader itself has no pack address. This batch procedure therefore requires all declared packs to begin in their applications, one coordinated requester, stopped master polling and only the selected pack entering the bootloader during each transfer. Stop other monitor/updater software and pause any external requester before execution.

Before any reset, the script obtains backups and unique BMS serials for every target. Before each transfer it requires a passive 1.2-second quiet interval and an unanswered read-only RFL probe. An existing bootloader response, additional/foreign frame, partial response, unexpected traffic or missing target stops the batch. One exclusive local UART0 descriptor is held throughout; this cannot stop an independent external host or invalidate a serial descriptor that another process already held.

The shared-bus sequence is conditionally supported by application address-selection evidence and offline host tests. **It has not been tested on a physical multi-pack bus.** Silence and valid replies cannot prove uniqueness against identical collisions, hidden/unpowered boards or another board spontaneously entering its bootloader later. First deployment needs physical bus/bootloader verification; a software address is not physical isolation. The single-pack helpers retain their isolated-target requirement.

Use the established [maintenance/flash procedure](flashing.md). During a Seplos master halt, inverter-facing aggregate values no longer describe the complete bank. Prepare that operating window before a batch.

## Commands

Use the prepared interpreter directly; no activation is needed:

```sh
PROJECT='/absolute/path/to/Seplos V2 10E BMS'
PY="$HOME/.local/share/seplos-firmware-tools/venv/bin/python"
TOOLS="$PROJECT/mod/tools/device"
UART0_PORT='/dev/cu.YOUR_UART0_ADAPTER'
UART1_PORT='/dev/cu.YOUR_UART1_ADAPTER'
cd /private/tmp
```

First inspect a plan without opening either adapter:

```sh
"$PY" -I -B "$TOOLS/flash_packs.py" 12 --mode master --profile full
"$PY" -I -B "$TOOLS/flash_packs.py" 12 --mode external --profile full
```

The JSON lists every address, exact selected image, MAINT version, build ID, EHEX SHA-256 and ACK gap. `--dry-run` makes the same offline behavior explicit. `--profile light` selects the smaller firmware branch.

### Seplos master with a separate UART1 maintenance adapter

```sh
"$PY" -I -B "$TOOLS/flash_packs.py" 12 \
  --mode master --profile full \
  --port "$UART0_PORT" --maintenance-port "$UART1_PORT" \
  --execute
```

The adapters must be physically distinct; identical paths, resolved aliases and the same `cu.`/`tty.` endpoint are rejected. The script reads master status on UART1 at 9600 baud and waits the practical 200 ms before each UART1 maintenance request. This is a host margin, not measured MCU scheduler latency. If the known marker is inactive, it sends maintenance start once; an already active marker is not rewritten. A fresh status must confirm marker `00000000` and effective slave count 0. Polling bytes already in flight are collected and logged after that confirmation; a full quiet interval must then occur within five seconds.

Maintenance start requires existing compatible MAINT support, the existing start permission and disabled automatic addressing. The tool does not enable these settings. An OEM master cannot acquire this capability from the host script.

### Master already paused, or polling manually halted

```sh
"$PY" -I -B "$TOOLS/flash_packs.py" 12 \
  --mode master --profile full --port "$UART0_PORT" --execute
```

Without `--maintenance-port`, the script never starts maintenance. UART0 must already be available, for example through an active marker or the established manual DIP procedure. An original firmware master may lack `64/02`; complete addressed reachability and bus silence remain necessary. Once the master runs the selected MAINT image, known marker status and effective slave count 0 are checked between packs. Unknown marker values or active polling stop the batch.

### External master with slave addresses 1 through N

```sh
"$PY" -I -B "$TOOLS/flash_packs.py" 12 \
  --mode external --profile full --port "$UART0_PORT" --execute
```

Pause the external requester yourself. No Seplos maintenance command can stop it. The script requires address 0 to remain silent and never starts maintenance in this mode. A partial address-0 response is an error, not evidence of absence.

## Backups and verification

A fresh directory is created under `local/devices/flash-logs/batch-TIMESTAMP-ID/`. `--out NEW_DIRECTORY` selects another new location; existing directories are rejected before opening a device.

- `report.json`: selected image, phases, current/failed address, confirmed predecessors and maintenance-start attempt/confirmation state. Updates are atomic. A failed start acknowledgement or confirmation does not imply an unchanged marker.
- `bus.log`: serial TX/RX and maintenance/transfer state. No pending input is silently flushed by the batch transport.
- `pack-NN-before.json`: full raw/decoded parameter block, device name, both serials, base information, supported MAINT/storage diagnostics and telemetry. All target backups are saved before the first reset.
- `pack-NN-after.json`: fresh post-flash snapshot, also retained when a subsequent comparison fails.

A target is marked verified only after its application returns, a settling interval has passed, its exact `64/03` payload matches the image metadata and its parameters/device name and both serials match the backup. The expected base family is checked through `51`. Previously present cell or pack voltage readings must not become zero. The next address is not reset until those checks finish successfully.

These checks establish application identity and available readbacks, not a cryptographic readback of every programmed byte or an electrical battery test. SOC and other live telemetry may change at restart; parameter equality does not prove SOC preservation. Full-profile checkpoint behavior depends on the source firmware executing the reset; flashing a full target does not retroactively add a checkpoint to an older/light source.

An active or uncertain persistent individual lock blocks a downgrade to light firmware. The script checks live status and available stored/runtime diagnostics and never unlocks or writes A1 automatically.

The default `--gap-ms 350` is an additional host pause after bootloader acknowledgements. It is configurable from 0 through 1000 ms and is not a universal flash-time guarantee. Firmware bytes are validated and pinned in memory; changing the selected image or metadata file stops subsequent transfers.

## Completion, errors and recovery

The maintenance marker is **never cleared automatically**, even after success. When the whole master-mode batch is verified, restore polling deliberately through UART1 and confirm the expected slave count:

```sh
"$PY" -I -B "$TOOLS/maintenance_client.py" stop \
  --uart UART1 --address 0 --serial "$UART1_PORT" --expected-slaves 11
```

Here 11 is the expected physical DIP slave count for the example of 12 total packs, not the number of flashed addresses. Keep the marker active if further UART0 work is intended. A clear ACK alone does not prove polling has resumed; the helper waits for fresh status.

Any uncertain ACK, reset error, wrong identity/build, changed parameters, missing measurement or interrupted process stops the entire run. Check the failed phase/address and wire log. Do not move to another target or automatically replay the failed transfer. There is no automatic resume/skip of already verified targets; another batch explicitly reflashes its whole declared range.

If recovery is needed, isolate the actual failed target and establish its bootloader state. Then use the existing helper with the exact image and verified file SHA-256 from the plan:

```sh
"$PY" -I -B "$TOOLS/flash_recovery.py" \
  "$UART0_PORT" "$IMAGE" "$EXPECTED_SHA256" "$NEW_RECOVERY_LOG"
```

Set those three values deliberately; the recovery helper has no pack-address argument. Verify the restored application, exact MAINT identity, parameters and serials separately. The batch script never calls recovery or sends another reset/erase/program retry for you.

## Validation scope

The device suite uses deterministic serial/storage models, tests both twelve-pack address ranges, malformed/extra/partial responses, all-bank backup ordering, exact post-verification, lock/downgrade guards, source pinning, errors and interruption boundaries. Existing single-pack transfer/ACK/reset tests remain applicable. Native UART0 counterexamples cover OEM 16.06.13 and MAINT 1.6.4 at their exact APP hashes and show foreign requests do not reset other modeled packs. They do not emulate the bootloader or establish physical multidrop timing.

No board was accessed or flashed during development. The current MAINT images and this batch path still require hardware validation.
