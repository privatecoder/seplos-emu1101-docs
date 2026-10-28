# Intermittent recharge: soft stop vs. hard stop

When a pack is full and intermittent recharge is enabled, the retained OEM builds use either a soft stop or the SP80 hard-stop mask. The code establishes output requests and reported limits; electrical load sharing remains conditional on the fitted power stage. The comparison below concerns the seven retained OEM images; MAINT 1.6.3 adds runtime selection, described at the end.

Confidence tags as in the rest of this documentation: **confirmed** = read from the code, **probable** = inferred, **assumption** = interpretation (here: hardware behaviour that the firmware cannot show).

## 1. Terms

| Name used here | Firmware | What a full, "waiting" pack does |
|---|---|---|
| **Soft stop** | every version except 16.06.05 (16.04.06 … 16.06.04, 16.06.11 … 16.06.13) | does not inhibit the charge MOSFET solely because of waiting; the master only lowers the charge current limit (CCL) sent to the inverter |
| **Hard stop** | 16.06.05 (SP80); also obtainable for later versions by the same one-byte change (§6) | **requests the charge MOSFET off** while waiting, subject to recovery priority and other output conditions |

## 2. The mechanism in both variants *(confirmed)*

Event processing: `0x9190` in 16.06.13 / `0x8F24` in 16.06.12. Full-flag creation and SOC counting are defined in the [SOC reference](soc-capacity-and-persistence.md).

**When a pack is "waiting"** (alarm event 6 bit 1, "Intermittent recharge waiting"):
- set when the pack's full flag is set (SOC jumped to 100 %, either by the 30-minute voltage rule or by over-voltage protection), the rounded whole-percent SOC `(SOC_tenths + 5) // 10` is above parameter 80 (e.g. 96 %), and function switch BitGroup5 bit 1 is on
- cleared when rounded SOC falls to parameter 80 or below, or the highest cell falls to parameter 3 or below
- disabling Group5.Bit1 also clears the full flag continuously except while OVP is active

**How the SOC gets back down while the pack is idle:** in standby with SOC above parameter 80, the coulomb counter deducts an artificial 0.2 A instead of 0.03 A (not when the highest cell is at or above parameter 1 or the pack is at or above N × 3.40 V). The counter runs once per second in units of 0.01 As, so this is 0.2 Ah per hour: at 280 Ah about 0.071 %/h, or roughly 56 h from 100 % to 96 % without any load (only while none of the exceptions applies).

**What the master does with it** (both variants):
- A waiting pack counts as "not chargeable".
- In the normal case CCL = per-pack limit × number of chargeable packs.
- When **all** packs are waiting (or otherwise blocked), the master sends CCL = 0.
- The full CCL rule has further branches with priority over or after this one ([protocols/can.md §3](../protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed)):
  - 10 A in total when every chargeable pack has a charge-related warning
  - a heating minimum (pack count × 10 A) when cell heating is enabled and the cells are cold; this applies even when no pack may charge
  - CCL = 0 when the highest cell exceeds cell OVP (parameter 4) + 30 mV, even if packs are still chargeable
  - a ramp of at most 1 A per online pack and cycle
- From 16.06.11, charge enable follows the resulting CCL (enable = CCL ≠ 0).
- For the discharge limit (DCL) a waiting pack still counts as dischargeable.

**What the pack itself does** (function "charging forbidden", 16.06.13 `0x6FFA`):
1. If the pack has been discharging with more than 10 A for 10 s, charging is allowed, regardless of any other condition except an active over-voltage protection. The 10 s counter resets as soon as the current rises above −10 A.
2. Otherwise charging is forbidden if one of the protection bits is set. Alarm event 6 is checked with mask `0x71` (charger over-voltage, cell too low to charge, reverse polarity, output connection fault).
   - **Soft stop:** mask `0x71`, "waiting" is not part of it, so waiting alone does not open the charge MOSFET. Other protections or current limiting can still open it.
   - **Hard stop:** mask `0x73`, which adds bit 1 "waiting", so the charge MOSFET opens.

So with hard stop, step 1 still overrides: a waiting pack that delivers more than 10 A for 10 s closes its charge MOSFET again, and opens it again in the second the current drops below 10 A.

## 3. What an open charge MOSFET means for discharging *(assumption)*

Everything in this section, and every hard-stop outcome in §4 and §5 that depends on it, rests on an assumption about the hardware. No schematic or measurement is available.

The scenario model assumes back-to-back charge/discharge MOSFET groups and a discharge path through the charge group's body diode while that group is off. A roughly 0.5–0.7 V drop is illustrative, not a measured EMU1101 value or a constant across current and temperature. The [manufacturer catalogue](../hardware/hardware-specifications.md#sh-energy-catalogue-emu1101-product-family) supports positive-side protection with a common charge/discharge port, but supplies no circuit schematic proving this detailed diode path on the examined board.

Consequence in a parallel system: under the assumed diode model, a waiting pack starts to contribute current once the bus voltage is about one diode drop below its own voltage. That is about 0.5 V at pack level, or roughly 30 mV per cell for 16 cells. On the flat LiFePO4 curve, 30 mV per cell is a lot of charge.

## 4. Situations

The numbers in the examples are illustrative, for two packs of 280 Ah with identical parameters. What follows from the code is which MOSFETs are open or closed and which limits the master sends; the CCL values assume the **normal case**, i.e. none of the other CCL branches of §2 (warning, heating, cell above OVP + 30 mV, ramp) is active. How the current then divides between parallel packs depends on pack voltages, impedances and wiring in both variants. For hard stop it additionally depends on the diode path assumed in §3. All load-sharing statements are therefore expected behaviour, not measured behaviour. To confirm them on a real system, watch the current of the waiting pack itself (e.g. in BatteryMonitor or via 0x42 telemetry).

### 4.1 Packs reach 100 % at about the same time

- In the afternoon both packs reach 100 % within a short time.
- **Soft stop:** as soon as both are waiting, the master sends CCL = 0 (normal case) and the inverter stops charging. In the evening both packs discharge with closed MOSFETs and share the load as their voltages and impedances dictate.
- **Hard stop:** same result, both charge MOSFETs are additionally open. In the evening both packs start from the same voltage, so (assuming the diode path of §3) both deliver through their diodes, and each pack closes its charge MOSFET again once it delivers more than 10 A for 10 s.

**Better:** neither. Hard stop brings no benefit here.

### 4.2 One pack is full much earlier than the other

- Pack 1 is at 100 % and waiting, pack 2 is at 85 %.
- **Soft stop:**
  - CCL drops to the limit for one pack (normal case), and the inverter keeps charging the common bus.
  - Pack 1's charge MOSFET is closed, so pack 1 stays connected to the rising charge voltage until pack 2 is full. Being full, it is expected to take little current, but it is held at a high voltage.
  - Depending on cells and settings, a cell may reach the cell over-voltage protection, which then opens the charge MOSFET as a protective shutdown.
- **Hard stop:** waiting requests pack 1's charge MOSFET off. If the fitted hardware blocks charging as assumed, pack 2 can continue charging without charging pack 1 through its normal charge path.

**Potential benefit of hard stop:** it requests a local charge inhibit for the full pack. Electrical effectiveness and recovery still require board-specific evidence.

### 4.3 Evening with a small load after one pack was full

- Pack 1 waiting at 100 %, pack 2 not waiting at 98 %. House load 20–40 A.
- **Soft stop:** both packs discharge with closed MOSFETs and share the load (as voltages and impedances dictate).
- **Hard stop:**
  - Expected (assuming the diode path of §3): pack 2 delivers practically all of the current. Pack 1 only joins once pack 2 is about one diode drop lower.
  - Pack 1 then stays near 100 %. Its own current is close to 0 A, so the pack counts as standby, and only the artificial 0.2 A standby deduction lowers its SOC. At 280 Ah that takes about 56 h if the deduction runs continuously; longer while one of its exceptions applies, shorter if the pack does deliver some current.
  - Expected result: overnight effectively **only one pack is usable**, and that pack carries up to twice its share of the load.
  - This matches a reported case where only one of two packs discharged until intermittent recharge was switched off and on again in BatteryMonitor. That report does not prove the cause, but it fits. Switching intermittent recharge off clears the full flag in the next one-second cycle, unless an over-voltage protection is active at that moment; when the function is switched on again, the pack is no longer waiting.

**Better: soft stop.**

### 4.4 Evening with a large load after one pack was full

- Same starting point, but the load is 150 A.
- **Hard stop:** expected (assuming the diode path of §3): pack 2's voltage sags, and pack 1's diode starts to conduct. Once pack 1 **itself** delivers more than 10 A for 10 s, its charge MOSFET closes again and both packs share the load normally. Whether and how fast pack 1 reaches that threshold depends on the voltage difference and the diode; it is not guaranteed by the total load. Until then the diode losses are about 0.6 V × current.
- **Soft stop:** both packs discharge with closed MOSFETs from the start.

**Better:** soft stop, but the difference is small.

### 4.5 Load peaks while one pack is waiting (hard stop only)

- The master still counts the waiting pack as dischargeable: DCL = per-pack limit × 2.
- The inverter may therefore draw up to twice the per-pack limit, while in the situation of §4.3 almost only pack 2 delivers.
- If the diode path behaves as assumed in §3, a sudden high load can push pack 2 into the discharge over-current warning or protection before pack 1 passes the 10 A / 10 s threshold.

**Better: soft stop.** This is a risk to consider for hard stop in systems that run close to the per-pack current limits.

## 5. Summary: when is hard stop better?

| Situation | Soft stop | Hard stop |
|---|---|---|
| Packs reach 100 % together | good (CCL = 0 in the normal case) | no benefit |
| One pack is full much earlier (old and new packs, different capacities, drift) | full pack held at charge voltage, possibly over-voltage protection | **potential benefit**: charge MOSFET requested off for the full pack |
| Small load after a partial full charge | normal | **worse** (expected, §3): waiting pack is stuck, half the capacity usable, one pack overloaded |
| Large load | normal | mostly fine (expected, §3): back to normal once the waiting pack itself delivers more than 10 A for 10 s |
| Load peaks near the per-pack limit | normal | **risk** (expected, §3): DCL counts the waiting pack, the other pack may hit over-current |

**Assessing hard stop requires both operating conditions and hardware evidence:**
1. your packs regularly reach 100 % at very different times, and
2. while one pack is waiting, **that pack itself** reliably delivers more than 10 A for at least 10 s soon after the evening load starts. The firmware only looks at the waiting pack's own current. A high total load makes this likely but does not guarantee it, so check the waiting pack's current on your system before relying on it.

The OEM main line uses soft stop. Uneven full markers alone do not establish that changing the mask will improve a real installation. Relevant checks include:
- the same parameters on all packs
- the full-voltage threshold N × clamped/quantized P0 and CVL (= P14), together with the minimum-cell, current-status and strict timing conditions in the [SOC reference](soc-capacity-and-persistence.md#2-automatic-corrections-without-ovp)
- working balancing

The standard 16.06.11–16.06.13 then keep all later fixes without the side effects of hard stop. 16.06.05 itself is based on 16.06.04 and lacks every later fix (see the [firmware changelog](firmware-changelog.md)).

## 6. Hard stop on later firmware versions

SP80 differs from 16.06.04 by exactly one byte: `movs r4,#0x71` becomes `movs r4,#0x73` in the function "charging forbidden" *(confirmed)*. The same instruction sequence exists unchanged in all later versions, only at a different address:

| Version | Offset in the image | Original | Hard stop |
|---|---|---|---|
| 16.06.04 → 16.06.05 (SP80) | `0x658A` | `71 24` | `73 24` |
| 16.06.11 | `0x6EA0` | `71 24` | `73 24` |
| 16.06.12 | `0x6EA0` | `71 24` | `73 24` |
| 16.06.13 | `0x706C` | `71 24` | `73 24` |

Notes:
- The retained `.ehex` payload is plain code with no identified whole-image signature/checksum; individual Intel HEX records have checksums. The header of 16.06.04 and SP80 is identical although one byte differs. Only the checksum of the one Intel HEX line that contains the byte has to be recalculated.
- In 16.06.11–16.06.13 the logic around this mask is unchanged, and the master's CCL calculation already treats a pack with an open charge MOSFET as not chargeable. Nothing else needs to change.
- The byte comparison establishes the image change; it does not establish electrical load sharing. The bootloader implementation is unavailable, and its content checks are not established by this mask comparison. Update behavior and the limits of bench evidence are described in the [bootloader reference](../protocols/bootloader-update-protocol.md).
- Hard stop brings all the side effects described in §4. Flashing modified firmware is at your own risk and may void warranty and vendor support.

## References

- [SOC and capacity](soc-capacity-and-persistence.md): full flag, voltage rules and standby deduction
- [Charge permission and output masks](power-on-off.md#charge-permission-and-output-masks): function "charging forbidden" and charge MOSFET
- [firmware-changelog.md](firmware-changelog.md): 16.06.05 (SP80) and later fixes
- [protocols/can.md §3](../protocols/can.md#3-limits-and-data-source-master-aggregation-confirmed): master aggregation of CCL/DCL


In MAINT1.6.3 the effective hard-stop mask can instead be selected with Group0.Bits6/7. Imageflag.Bit7 signals configurability and Imageflag.Bit0 then describes the build default, not the runtime selection. Group5.Bit1 must still enable recharge waiting. See the [MAINT1.6.3 parameter contract](../../mod/docs/firmware/maint163-configurable-hard-stop.md).
