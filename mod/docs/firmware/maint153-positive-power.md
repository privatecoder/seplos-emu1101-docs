# MAINT 1.5.3: positive UART1 power and RTC permission

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Seplos BMS 2.0/10E/V16 (EMU1101), OEM 16.06.13-based lightweight profile. Group0.bit3=1 permits UART1 power/RTC; 0 denies it. Addressed parameter/identity access, maintenance services, UART0 marker access and read-only storage diagnostics remain available. Bit4 remains reserved. There is no parameter migration, persistent individual pack lock, extra CCL clamp or SOC checkpoint before reset.

The [release metadata](../../firmware/releases/maint153-positive-power.json) defines the exact image filename, build ID, MNT04 INFO, flags and EHEX/application SHA-256. The [generated capability matrix](uart-write-capabilities.md) renders current identities directly from that metadata.

The image contains 56,016 application bytes, a 2,924-byte appendix and 220 update blocks. It uses five OEM hook sites and no additional persistent RAM. The same image supports master and slaves.

Image flag `08` describes the polarity of supported controls; it does not add Cutoff. Flag `04` is absent, so Group0.bits4/5 have no lock meaning. Flags `02/10/20` identify UART1 power/RTC, UART0 marker/info and UART0/UART1 storage diagnostics. Flags `40/80` are absent. An optional static hard-stop build has flags `3B`; bit0 remains an immutable image property.

| Group0 field | Meaning |
|---|---|
| bit0 | 1 permits UART1 A1 parameter writing |
| bit1 | Existing temperature-sensor plausibility check |
| bit2 | 1 permits UART1 maintenance start under the other prerequisites |
| bit3 | 1 permits UART1 on/off, reset and RTC setting |
| bits4–7 | Reserved in this profile |

UART1 45/04, UART1 45/06 and UART1 4E return RTN05 without action when bit3=0. UART1 4D, binary 47/A2/A4 and read-only 64 services remain ungated. UART0 power/RTC is independent. UART0/UART2 can edit bit3; a change through UART1 A1 returns atomic E3. Existing bit0/bit2 protection and parameter validation remain. Group0=FF permits UART1 power/RTC without initialization or stored-value conversion.

On/off uses the OEM routines, including the master's slave broadcast. Off remains logical: charging may undo it, and its CCL contribution need not become zero. No new MOSFET, limiter or wakeup intervention is introduced. Reset success has no ACK and does not gain verified SOC saving.

Addressed UART0/UART1 64/04 is unrestricted at the board's own address 0–21; foreign/FF requests are silent. Format01 has ten bytes and LENGTH `B014`. Lock fields `FF/FF` and cache `00` mean unavailable, not unlocked. It reads flash without repair or writing. See [storage diagnostics](storage-and-reset.md) and the [integration contract](openbms-monitor.md).

Build with `--maint-version 1.5.3 --base-revision 13` using the [build procedure](build-and-validation.md). The existing `POSITIVE_FLAGS` assembler branch is reused. Relative to 1.5.2, exactly eleven application bytes change: one conditional-branch byte, one patch-version byte, one flags byte and eight build-ID bytes. The entire native OEM prefix, including the five hooks, is identical. The published current profiles retain their exact binary identities.

The [shared payload](../../firmware/patcher/seplos/payload.s) implements the permission branch, and the [lightweight diagnostic builder](../../firmware/patcher/seplos/storage_diagnostics.py) adds read-only storage inspection.

The release passed 194 mandatory actual-Thumb groups, including sixteen diagnostic groups with positive permission, both control values, unrestricted diagnostics and reserved-bit4/FF cases. Missing or wrong mandatory suites prevent publication. Unknown code forms are refused. Emulator peripherals do not establish real timing or electrical behavior. This release was not flashed or hardware-tested. [Metadata](../../firmware/releases/maint153-positive-power.json) · [Capability matrix](uart-write-capabilities.md)
