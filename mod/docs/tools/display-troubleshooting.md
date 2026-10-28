# Display values and format troubleshooting

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The BMS can return valid measurements over UART0 while its local display shows zero values. The display is a separate UART2 consumer; a display symptom alone does not establish erased measurements, a failed firmware update or an incorrect SOC.

## Separate firmware operation from display decoding

1. Read fresh addressed 51/42/44 over an available UART0/UART1 route, and 64/03 on supported MAINT firmware. Confirm that the target responds and that measurements/identity are plausible. Respect bus ownership.
2. Read Group7. Bit3 enables the local display protocol; Bit4 selects its spontaneous status format. Preserve enable and every unrelated bit. The format affects UART2 output, not UART0/UART1 framing.
3. Determine the actual display model and required format. In one historical display/build case, valid UART0 telemetry coexisted with zeroes on the screen and the short spontaneous format restored the display. That observation is not a universal instruction to clear Bit4.
4. If changing format is justified, use [display_format.py](../../tools/device/display_format.py) with an explicit pack address and adapter. The helper backs up the parameter block, detects intervening changes, guards the A1 learned-capacity side effect and reads back the result.

```sh
"$SEPLOS_TOOLS_PY" -I -B "$SEPLOS_PROJECT/mod/tools/device/display_format.py" \
  7 status --port /dev/your-rs485-adapter
# Choose only the format required by the connected display:
"$SEPLOS_TOOLS_PY" -I -B "$SEPLOS_PROJECT/mod/tools/device/display_format.py" \
  7 kurz --port /dev/your-rs485-adapter
```

`status` is read-only, `kurz` selects short and `erweitert` selects extended format. UART0 needs a quiet pack bus; the helper's `--uart1` option uses its own binary parameter route and requires UART1 writing permission. Apply the setting to the board hosting the display. There is no display-to-slave proxy.

## Evidence limits

The historical check compared OEM and a fixed MAINT display builder/TX path in a bounded emulator and found matching output for the supplied synthetic state. No physical UART2-port capture identified a universal LCD protocol requirement, and no independent restart-persistence test was established for that observation. Readback confirms the active parameter; it does not prove that another display model understands the resulting frames.

Do not overwrite SOC merely to match another parallel pack or repeatedly reflash based only on the display. Use [SOC/persistence](../../../analysis/firmware/soc-capacity-and-persistence.md), [binary display framing](../../../analysis/protocols/binary-display-protocol.md) and [flash verification](flashing.md) to distinguish those separate behaviors. Raw installation captures remain under `local/devices/lab/`; the helper defaults parameter backups to `local/devices/backups/parameters/`.
