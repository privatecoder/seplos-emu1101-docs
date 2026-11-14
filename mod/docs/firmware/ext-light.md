# EMU1101-EXT Light 1.5.3 and later: lightweight diagnostics

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT Light provides addressed parameter/identity access, maintenance services, UART0 marker access, UART1 power/RTC access control and ten-byte storage diagnostics from Light 1.5.3. Group0.bit3=1 permits UART1 power/RTC; 0 denies it in every versioned release. Addressed UART1 history, active/stored calibration and persisted-capacity/live-energy reads are available from Light 1.5.4. The current published image is Light 1.5.6, based on OEM 16.06.13. Bit 4 remains reserved. There is no parameter migration, persistent individual pack lock, extra CCL clamp, configurable hard-stop parameter or SOC checkpoint before reset.

The same image supports master and slaves. The current Light 1.5.6 image includes guarded early-polling hooks and no additional persistent RAM. The atomic scheduler cleanup introduced in Light 1.5.5 preserves interrupt updates through a short saved-PRIMASK critical section; the separate OEM skip branch remains intact. Discovery of the shared read capabilities requires the 21-byte EXT05 response and appended big-endian capability mask 000F. [Remote diagnostics](remote-diagnostics.md) defines exact lengths, offsets, units and errors. Read-only access adds no enable flags and remains available with Group0 permissions disabled. UART2 display behavior is unchanged.

Validated early master polling is available from Light 1.5.6. A complete matching response can finish the transaction before the nominal 150 ms timeout. Missing or invalid responses retain the original deadline; polling remains sequential and aggregation remains tied to the slow pass. See [early UART0 polling](early-polling.md) for compatibility, timing and validation limits.

| Group0 field | Meaning |
|---|---|
| bit 0 | 1 permits UART1 A1 parameter writing |
| bit 1 | Existing temperature-sensor plausibility check |
| bit 2 | 1 permits UART1 maintenance start under the other prerequisites |
| bit 3 | 1 permits UART1 on/off, reset and RTC setting |
| bits 4–7 | Reserved in this profile |

Image flags 3A identify UART1 power/RTC, the standard 1=enabled permission semantics, UART0 marker/info and storage diagnostics. Flag 04 is absent, so Group0.bits4/5 have no lock meaning. Flags 40/80 are absent. An optional static hard-stop build has flags 3B; bit 0 is an immutable image property.

UART1 45/04, 45/06 and 4E return RTN05 without action when bit 3=0. UART1 4D, binary 47/A2/A4 and read-only services remain ungated. UART0 power/RTC is independent. UART0/UART2 can edit bit 3; a change through UART1 A1 returns atomic E3. Existing bit 0/bit 2 protection and parameter validation remain. Group0=FF permits UART1 power/RTC without initialization or stored-value conversion.

On/off uses OEM routines, including the master's slave broadcast. Off remains logical: charging may undo it, and its CCL contribution need not become zero. No additional MOSFET, limiter or wakeup intervention is introduced. Reset success has no ACK and does not gain verified SOC saving.

Addressed UART0/UART1 64/04 remains format 01, ten bytes, LENGTH `B014`. Lock fields FF/FF and cache 00 mean unavailable. It reads flash without repair or writing. Light 1.5.4 and later provide 64/06 to read persisted contents; read capability does not imply a checkpoint before reset. See [storage and reset](storage-and-reset.md).

History is one record per request and shares the OEM UART0/UART1 cursor. Failed EEPROM reads restore the cursor; an unanswered request still has an ambiguous outcome. Concurrent ring writes prevent an atomic download guarantee. Calibration/live-energy reads are snapshots and do not save, repair or calibrate.

Build with `--ext-version 1.5.6 --base-revision 13` using the [build procedure](build-and-validation.md). The standard permission semantics and four read capabilities are intrinsic. The [shared payload](../../firmware/patcher/seplos/payload.s), [storage diagnostic builder](../../firmware/patcher/seplos/storage_diagnostics.py) and [remote diagnostic builder](../../firmware/patcher/seplos/remote_diagnostics.py) retain guarded native contracts. Unknown code or data shapes are refused.

The current Light 1.5.6 image passes its mandatory actual-Thumb groups, including early UART0 polling. The release metadata records exact image sizes, hook and test counts. [Release metadata](../../firmware/releases/ext-light.json) records the exact build ID and EHEX/application SHA-256. The history model injects UART1 RX at the EEPROM transfer boundary; deterministic native cases cover enabled timer/protection/CMP handlers and concurrent UART0 reception with deferred parsing, while physical multi-pack UART0 polling remains untested. No current image was flashed or hardware-tested; offline checks do not establish real flash/I2C timing, electrical behavior or physical current accuracy. [Capability matrix](uart-write-capabilities.md) · [Validation limits](validation-methods-and-limits.md)
