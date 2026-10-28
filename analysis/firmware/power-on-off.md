# On/off and MOSFETs in the original firmware

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The reference is **unmodified OEM firmware**, specifically
16.06.13; all addresses below refer to that image. Counterexamples execute real
Cortex-M0 code with synthetic RAM/GPIO inputs. They are not electrical measurements.

## Three different states

| Layer | Meaning |
|---|---|
| System status `0x200000AC.bit5` | Logical **off**; does not prove that both power paths are open |
| On-off `0x200000B5` | Bit 0 discharge, bit 1 charge MOSFET, bit 2 current limiter, bit 4 precharge; output decisions |
| Supply/self-hold | A separate, conditional later shutdown path; logical off does not immediately power down the MCU |

**On/off does not provide galvanic isolation.** Off alone does not inhibit the
charge path, and charging recovery can even enable the discharge path. Conversely,
on alone does not guarantee that either MOSFET is enabled.

## What the original command does

ASCII `0x45` type `0x04` clears the off bit for value `0x10` and sets it for every other value;
the master uses `0x1F` for off. Handler `0x0A3C`, action `0x0A86–0x0ABC`. It also sets
on/off broadcast requests. This branch neither writes MOSFET GPIOs directly nor
saves parameters. RTN 00 acknowledges command acceptance, not a lasting MOSFET state.

Charge/discharge evaluation follows in the 1 s block; discharge may first require
precharge. On is not a restart (type 6 is a watchdog reset without a reply), a
general alarm reset or an independently persisted per-pack lock.

## Off and the power paths

Logical off is a normal discharge/precharge inhibit. Charging, limiting and heating retain their own conditions. The [output masks](#charge-permission-and-output-masks) and [recovery priority](#discharge-permission-and-recovery-priority) determine whether the paths actually conduct. A charge MOSFET reported off does not rule out the parallel limiter path.

The native handler changes logical off immediately (`0x0A86–0x0ABC`); outputs follow the next one-second evaluation (`0x61B0–0x61C0`). On the bench, logical off retained communication and accepted a later targeted on. With UVP/empty and an expired 60 s counter, off returned about one second after on; after a restart the counter's initial window allowed on/off normally (`0x887C`, `0x88BC`, `0x8A42`). A restart resets this counter, whereas on only clears the off bit.

## Automatic wakeup and repeated off

- **Charging detected:** `0x870C` normally sets system status bit 1 from +0.60 A,
  or +1.20 A with event 4.bits 0–3 (hysteresis: [system-status table](states-and-triggers.md#charging--discharging--standby--off-system-status)). `0x8A36`
  then clears off. This threshold is distinct from the 3 A recovery threshold.
- **Port voltage:** after 30 state calls in off, `0x8A96–0x8AB6` compares port
  voltage with P15. If port>P15 and internal cause bits 2/3 at `0x200000F1` are
  clear, `0x8AE2–0x8AEE` returns the logical state to standby. This is not an
  unconditional 30 s wakeup: internal causes can prevent it. The counterexample
  explicitly supplies the required conditions.
- **Undervoltage/empty flag:** without charging or active charge activation,
  `0x887C–0x88C2` sets a shutdown cause after 60 s, which reasserts off. On does
  not clear that cause or the elapsed counter. If the cause persists, off can
  return on the next 1 s cycle.
- Button, enabled external switch and another on command are additional paths.
  On/off edges at the master can trigger further broadcasts.

After on, protections and the recovery priority below determine outputs. On alone does not guarantee either gate.

## Charge permission and output masks

Evaluator:16.06.13 `0x6FFA`;16.06.05 `0x6516`. The >10 A discharge-recovery branch is `0x7036`–`0x704A` in16.06.13.

The function sets or clears **alarm event 8 bit 6** ("charging forbidden"). From this follow the system status/on-off bit 1 and finally GPIO `0x50002000` bit 12, i.e. the charge MOSFET.

1. A counter counts up (max. 30) as long as the current is **< −10.00 A** (discharging). If the current is above that, it is set to 0.
2. From counter value 10, i.e. with sustained discharge above 10 A:
   - If **cell or pack overvoltage protection** is active (event 2 bit 1/5), these bits are **cleared**: discharging lifts the OVP protection. Charging remains forbidden in this cycle.
   - If no OVP protection is active, charging is allowed.
3. Otherwise charging is forbidden if one of these bits is set:
   - Event 2: cell OVP (bit 1), pack OVP (bit 5)
   - Event 3: charge overtemp. protection (bit 1), charge undertemp. protection (bit 3)
   - Event 4: ambient overtemp. protection (bit 1), undertemp. protection (bit 3), power stage overtemp. protection (bit 4)
   - Event 5: charge overcurrent protection (bit 1)
   - Event 6 with mask **`0x71`**: charger overvoltage (bit 0), cell too low to charge (bit 4), reverse polarity (bit 5), output connection fault (bit 6)
     - **SP80 only (06.05):** mask **`0x73`**, i.e. additionally **bit 1 "Intermittent recharge waiting"**
   - internal flag (`0x200000EA` in 06.05) bit 6
4. Afterwards: on-off bit 1 → GPIO pin of the charge MOSFET. If current limiting (bit 2) is off, GPIO bit 10 is cleared.

The bit masks are identical in all versions, **except SP80**. The **source of the temperature condition** changed in 16.06.11: up to 16.06.05 it tests the reported event 3 (`0x20000032`, masked by the current direction), from 16.06.11 the raw protection byte `0x200000BB` (not masked by direction; from 16.06.12, however, masked with BitGroup2, 06.13 `0x6946`–`0x6952`, not in 16.06.11, see [changelog](firmware-changelog.md)). *(confirmed: 16.06.05 `0x6576`, 16.06.11 `0x6E84`, 16.06.13 `0x7050`)*

Additionally (06.12/06.13): if event 7 bit 6 or 7 is set (current limiting, see [current limiting](states-and-triggers.md#current-limiter-current-limiter)) and the pack is charging, the **charge MOSFET is switched off and the current limiter switched on**. The standby shutdown also sets "charging forbidden" 60 s before shutting down. *(confirmed)*

## Discharge permission and recovery priority

Evaluator:16.06.13 `0x7184`,16.06.12 `0x6FB8`. In16.06.13 the logical-off test is at `0x7204`–`0x720A`, after the charging-recovery branch described below. The normal blocked path clears GPIO13/GPIO15 and on-off Bits0/4, disabling discharge and precharge (`0x723E`–`0x7252`).

The discharge MOSFET (on-off bit 0, GPIO 13) is **off** as long as any of the following applies:
- Event 2 bit 3/7: cell or pack undervoltage protection
- Raw cell temperature state `0x200000BB` & 0xA0: discharge over/undertemperature protection
- Event 4 & 0x1A: ambient over/undertemperature protection, power stage protection
- Event 5 bits 3–7: discharge overcurrent protection, short-term overcurrent protection, short-circuit protection, both locks
- Event 6 & 0x68: **SOC protection (parameter 79)**, reverse polarity (never set), output connection fault
- Empty flag (`0x200000F5` bit 0, set when the SOC jumps to 0 % due to UVP)
- System status bit 5 "off"

**Charging recovery precedes the inhibits above:** with system status bit 7 set (charge current at least 3.01 A; clears below 2.81 A), `0x719C–0x71B8` jumps to the output stage before testing them. Without cell/pack UVP it enables discharge even while off is set. Pending UVP is cleared first; discharge remains inhibited only in that clearing cycle. This is more than merely clearing UVP. Re-enabling may require [precharge](states-and-triggers.md#soft-start-precharge). A synthetic4 A case enables both MOSFETs while the initial off bit is still set; subsequent state processing can clear off in the same cycle. *(confirmed: code and counterexample)*

## Off triggers and delayed supply shutdown

`0x8978`, `0x89E8`, `0x8A24`, `0x88D0` *(confirmed, 06.12 identical)*

| Trigger for "off" | Condition | Back on through |
|---|---|---|
| Button | pressed > 3 s (> 301 s → event 1 bit 3 button fault) | Button, charging |
| External switch | BitGroup7 bit 0, input GPIO `0x50001000` pin 0 high | Pin low, charging |
| Control command | ASCII 0x45 type 4, value ≠ 0x10 | Type 4 with 0x10, charging |
| **Undervoltage / empty** | cell or pack UVP (event 2 bit 3/7) or empty flag, not charging, no pending charge activation: after **60 s** (`0x887C`–`0x88C2`, counter `0x200015D0`), then again every second | Charging; "on" holds only once the reason is gone |
| **Standby shutdown** | BitGroup7 bit 1; **P77 hours** of continuous standby without external voltage at the port (system status bit 4 and not bit 2), highest cell < P5, no pending charge activation; 5 s outside standby reset the counter | Charger (port > P15), button, charging |

- Sequence of the standby shutdown: 60 s "charging forbidden", then "off". After 30 s "off" and without voltage at the port: save state to internal flash (block 6), then GPIO `0x50001000` bit 1 = 0. That this switches off the BMS supply (self-holding circuit) is *probable*.
- **Off is a logical state, not a guarantee that both power paths are disconnected.** Normally it inhibits discharge including precharge, while charging remains independently possible; charging-current-status recovery can bypass the discharge inhibit. On only clears the off bit, without directly forcing either MOSFET or clearing persistent protection causes. The output masks and recovery priority above determine the actual state. *(confirmed,16.06.13)*
- A master with slaves reports every change as a broadcast to the slaves, whatever the trigger ([ASCII command 45](../protocols/seplos-ascii.md#53-cid2-0x45-remote-control)). *(confirmed)*
- **Illustrative configuration:** BitGroup7.Bit1=1 and P77=48 h. An inverter that keeps the port energized or regularly charges can prevent this continuous-standby timeout.

**Separate thresholds:** detected charging clears off at the charging-detection threshold (normally 0.60 A, or 1.20 A with event 4.bits 0–3), not only at 3 A. A port-voltage wakeup is also possible after 30 state calls if port>P15 and internal shutdown-cause bits 2/3 are clear (`0x8AA4–0x8AEE`). This is not an unconditional 30 s release. On does not generally clear protection/shutdown causes.

Native save path: `0x5564` → `0x4748` before releasing supply self-hold; state-of-charge restoration follows the [block6 persistence rules](soc-capacity-and-persistence.md#4-what-returns-after-loss-of-power). Button or eligible port voltage can abort shutdown. The port-voltage wakeup also checks internal cause bits, as described above.

## Master, slaves and current limits

The master sends `00 04 1F` (off) or `00 04 10` (on) to FF once per on/off edge (`0x8A24`, `0x13F6`), between normal polls and only while configured as a polling master. There is no cyclic repetition. A polling master does not process host 45 requests on UART0. Slaves
remain silent. A slave switched off by unicast has no independent permanent lock:
a later master-on broadcast, detected charging or an eligible port-voltage wakeup
can switch it on again. Local protection and recovery conditions still apply.

`0x96CE` counts charge capability from on-off & 0x06 (charge MOSFET **or** limiter)
and discharge capability from on-off & 0x11 (discharge/precharge), with additional
alarm conditions. **Off does not automatically set CCL to 0.** An available charge
path can still contribute. DCL contribution disappears when discharge is actually
inhibited; the off bit alone does not replace checking paths and alarms. Aggregate
CCL `0x98A8` also has a downward ramp, fallback and heater rules. Do not infer an
immediate numerical limit from off alone. See [Modbus§2](../protocols/modbus-rtu.md#2-data-source-system-aggregate-0x2000164c).

## Diagnostics and evidence limits

44 exposes only on-off & 0x0F and system status & 0x33; precharge is hidden. The 32-byte
`0x5A` response includes full on-off at byte 28 and full system status at byte 31.
An auxiliary flag such as on-off `0x40` is not a MOSFET permission. Firmware status
bits do not replace electrical gate/current measurements. Supply self-hold
hardware needs separate verification.

The repeated unmodified 16.06.13 Thumb counterexamples confirm: ordinary off leaves
the charge gate on, charging recovery can re-enable discharge, charge inhibit is
recalculated, sustained discharge can override it, and port voltage can clear off
after 30 state calls when eligible. These are synthetic code executions, not
measurements on a loaded battery. Function addresses above allow independent
inspection of the vendor image. For the source conditions see
[Charge permission and output masks](power-on-off.md#charge-permission-and-output-masks),
[On/off, standby shutdown and external switch](states-and-triggers.md#onoff-standby-shutdown-and-external-switch),
and [ASCII45](../protocols/seplos-ascii.md#53-cid2-0x45-remote-control).

The saved results of five OEM counterexamples (`oem-cutoff.json`, local reference, not published)
cover ordinary off, 4 A charging recovery, recalculated charging inhibition,
discharge recovery and eligible port wakeup after 30 calls. The existing
[offline reproduction helper](../../mod/tools/firmware-analysis/probe_pack_cutoff.py)
accepts only the fixed, verified OEM file hash. It runs with `python -I` from
`/private/tmp` using the patcher's virtual environment, Unicorn and LLVM;
`--out NEW.json` selects a new output file. It has no serial access.
