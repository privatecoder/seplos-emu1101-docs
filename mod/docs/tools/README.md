# Firmware analysis and device tools

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The tools use project-relative source locations `mod/tools/firmware-analysis` and `mod/tools/device`. [Analysis tools](../../tools/firmware-analysis/README.md) document offline code/emulator commands; [device tools](../../tools/device/README.md) document exact client arguments and device operations. The [firmware contracts](../firmware/README.md) define what the running profile supports.

Use prepared external environments at the established paths from [build setup](../firmware/build-and-validation.md). `SEPLOS_PYTHON` selects `~/.local/share/seplos-oem-patcher/venv/bin/python` for patching and offline analysis with `unicorn==2.1.4`. `SEPLOS_TOOLS_PY` selects `~/.local/share/seplos-firmware-tools/venv/bin/python` for device helpers; it requires `pyserial==3.5` and `unicorn==2.1.4`. Existing correctly populated environments can be reused; inspect the [setup](../firmware/build-and-validation.md) before running commands. LLVM remains an external requirement for native analysis. Set the root to the actual checkout, quote it and run from a neutral directory:

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
export SEPLOS_PYTHON="$HOME/.local/share/seplos-oem-patcher/venv/bin/python"
export SEPLOS_TOOLS_PY="$HOME/.local/share/seplos-firmware-tools/venv/bin/python"
export SEPLOS_DEVICE="$SEPLOS_PROJECT/mod/tools/device"
export SEPLOS_ANALYSIS="$SEPLOS_PROJECT/mod/tools/firmware-analysis"
cd /private/tmp
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/maintenance_client.py" --help
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/parameter_client.py" --help
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/identity_client.py" --help
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/display_format.py" --help
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/restart_pack.py" --help
```

The maintenance client prints the request when no serial/TCP transport is selected:

```sh
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/maintenance_client.py" info --address 11
"$SEPLOS_TOOLS_PY" -I "$SEPLOS_DEVICE/maintenance_client.py" diagnostics --uart UART1 --address 11
```

Address 11 decimal is 0B hex. Select `--uart UART0` only with a quiet UART0 bus. Diagnostics is read only and never sends reset or firmware. Decode only recognized INFO layouts and keep unknown/unavailable fields distinct from healthy/unlocked values. Do not infer every slave's firmware from the master.

Parameter and identity clients provide binary UART1 access, raw serial-number checks and complete 47/A1 block handling. Preserve all untouched fields; an accepted A1 can adjust learned capacity/SOC when it differs from P58 by at least 10 Ah. UART1 writing requires bit0 and protects bits2/3, plus bit5 in full profiles. Device name and serial-number writes remain UART0-only. Display format is stored in Group7.bit4 and can be changed through a permitted complete parameter write. Actual UART2 operation requires its local connection and enable/format settings; UART1 remains a separate protocol port.

`restart_pack.py` is an action: use one reset, expect no success ACK and verify the same board afterwards. Full-profile reset may report RTN08 instead of resetting. `flash_gap.py`, `flash_recovery.py` and `boot_entry.py` support the retained isolated-device bootloader procedure; follow [flashing](flashing.md) and each client's help. `boot_entry.py` is an importable module, not a standalone CLI. Select the application address explicitly with `flash_gap.py --address`; the bootloader still requires one isolated target.

Offline analysis reads OEM inputs from `vendor/firmware` and selected releases/fixtures from `local/releases` and `local/fixtures`. Put reports, resolved source, disassembly and generated images under `local/builds`; keep raw captures and installation values local. Use explicit fresh output paths. Reusable firmware analysis covers access capabilities, SOC/persistence, power paths, UART ownership and version-bound native emulation. Unknown code shapes remain evidence limits, not an invitation to reuse fixed addresses against another image.

Use one shared lock per physical serial/gateway connection, one outstanding request and UART1's practical 200 ms quiet period after the final received byte. Parameter/SN reads on UART1 need no maintenance; UART0 host access needs stopped master polling. Hardware captures and raw evidence belong under `local/devices/lab`; offline analysis evidence uses `local/research/<topic>/evidence`, build outputs use `local/builds/runs` and tool reports use a new dated experiment directory. No example here selects a real adapter, gateway or installation address.


## Research and troubleshooting guides

- [SOC emulator fixture API and extension rules](soc-fixtures.md)
- [Display values and format troubleshooting](display-troubleshooting.md)
- [Host framing ambiguity and busy-bus outcomes](../firmware/openbms-monitor.md#transport-ambiguity-and-result-classification)

Current helpers and catalogue generation use maintained inputs under `mod/`. Frozen legacy builders, laboratory exercises and their regression dependencies remain under ignored `local/`; use the [historical test runner](../../tools/run_historical_tests.py) to list or explicitly execute those checks. A version-bound research probe may still require its documented historical images/report data. Do not substitute another image for a pinned profile.
