# MAINT 1.5.4: lightweight diagnostics

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101), OEM 16.06.13-based lightweight profile. MAINT 1.5.4 adds addressed UART1 history, active/stored calibration and persisted-capacity/live-energy reads. Group0.bit3=1 permits UART1 power/RTC; 0 denies it. Addressed parameter/identity access, maintenance services, UART0 marker access and ten-byte storage diagnostics remain available. Bit 4 remains reserved. There is no parameter migration, persistent individual pack lock, extra CCL clamp, configurable hard-stop parameter or SOC checkpoint before reset.

The same image supports master and slaves. It uses five existing OEM hook sites and no additional persistent RAM. New read discovery requires the 21-byte MNT05 response and appended big-endian capability mask 000F. [Remote diagnostics](remote-diagnostics.md) defines exact lengths, offsets, units and errors. Read-only access adds no enable flags and remains available with Group0 permissions disabled. UART2 display behavior is unchanged.

| Group0 field | Meaning |
|---|---|
| bit 0 | 1 permits UART1 A1 parameter writing |
| bit 1 | Existing temperature-sensor plausibility check |
| bit 2 | 1 permits UART1 maintenance start under the other prerequisites |
| bit 3 | 1 permits UART1 on/off, reset and RTC setting |
| bits 4–7 | Reserved in this profile |

Image flags 3A identify UART1 power/RTC, positive polarity, UART0 marker/info and storage diagnostics. Flag 04 is absent, so Group0.bits4/5 have no lock meaning. Flags 40/80 are absent. An optional static hard-stop build has flags 3B; bit 0 is an immutable image property.

UART1 45/04, 45/06 and 4E return RTN05 without action when bit 3=0. UART1 4D, binary 47/A2/A4 and read-only services remain ungated. UART0 power/RTC is independent. UART0/UART2 can edit bit 3; a change through UART1 A1 returns atomic E3. Existing bit 0/bit 2 protection and parameter validation remain. Group0=FF permits UART1 power/RTC without initialization or stored-value conversion.

On/off uses OEM routines, including the master's slave broadcast. Off remains logical: charging may undo it, and its CCL contribution need not become zero. No additional MOSFET, limiter or wakeup intervention is introduced. Reset success has no ACK and does not gain verified SOC saving.

Addressed UART0/UART1 64/04 remains format 01, ten bytes, LENGTH `B014`. Lock fields FF/FF and cache 00 mean unavailable. It reads flash without repair or writing. The new 64/06 can read persisted contents in this profile; read capability does not imply a checkpoint before reset. See [storage and reset](storage-and-reset.md).

History is one record per request and shares the OEM UART0/UART1 cursor. Failed EEPROM reads restore the cursor; an unanswered request still has an ambiguous outcome. Concurrent ring writes prevent an atomic download guarantee. Calibration/live-energy reads are snapshots and do not save, repair or calibrate.

Build with `--maint-version 1.5.4 --base-revision 13` using the [build procedure](build-and-validation.md). Positive flags and the four read capabilities are intrinsic; there are no compatibility flags. The [shared payload](../../firmware/patcher/seplos/payload.s), [storage diagnostic builder](../../firmware/patcher/seplos/storage_diagnostics.py) and [remote diagnostic builder](../../firmware/patcher/seplos/remote_diagnostics.py) retain guarded native contracts. Unknown code or data shapes are refused.

The current image has 57,304 application bytes, a 4,212-byte appendix and 225 update blocks. Build ID is `80112d861b8329c4`. It passed 214 mandatory actual-Thumb groups and rebuilt byte-identically. [Release metadata](../../firmware/releases/maint-light.json) records EHEX SHA-256 `bc1442ed075d94f10fcd08d2ce322c9e1eb23748ee0459894f1bf74cb3b18382` and application SHA-256 `0e10295aac3f3c88ea5f77f1deaf431a67f6f720c7e82a7e805bf4e1ecb34ef3`. The history model injects UART1 RX at the EEPROM transfer boundary; full concurrent UART0 polling, timer and protection execution has not been tested. No current image was flashed or hardware-tested; offline checks do not establish real flash/I2C timing, electrical behavior or physical current accuracy. [Capability matrix](uart-write-capabilities.md) · [Validation limits](validation-methods-and-limits.md)
