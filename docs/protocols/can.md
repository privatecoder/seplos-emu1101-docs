# Seplos 10E / EMU1101: CAN inverter protocols

What the BMS sends to the inverter via CAN. The focus is **protocol 1 "PNG_DYE_Luxp_TBB"**, the Pylontech-compatible protocol used with **Deye** and Luxpower. Basis is the disassembly up to V16.06.13; addresses apply to 06.13.

Confidence: **confirmed** = directly from the code · **probable** · **assumption**. All multi-byte fields are **little-endian**, except for Growatt and Studer (big-endian).

---

## 1. Summary for Deye

- **Only the master pack (DIP address 0) sends CAN.** Slaves are silent on CAN. *(confirmed)*
- **All values are system values across all online packs.** The master collects them via the intra-pack protocol (0x5A): voltage = average, current and capacity = sum, cell extremes across all packs. *(confirmed)*
- **500 kbit/s**, 11-bit IDs. Roughly once per main loop tick, the set **0x351 → 0x355 → 0x356 → 0x359 → 0x370 → 0x371 → 0x35E → 0x35C** is sent *(confirmed; period presumably approx. 1 s)*.
- **The BMS receives nothing via CAN.** Heartbeat 0x305 and other frames from the Deye are ignored; there is no timeout. *(confirmed)*
- **Manufacturer name in 0x35E: "SHEnergy"**, not "PYLON". *(confirmed)*
- **0x359 never reports "Protection"** (bytes 0/1 are always 0), only warnings. *(confirmed)*
- **SOC stays at 98 %** until all packs are above 98 %. *(confirmed)*
- **CVL is fixed** to the parameter "pack overvoltage protection". There is no absorption/float reduction. Throttling happens only via the charge current limit (CCL). *(confirmed)*

**With the example configuration** (`config/parameter-export-example.xml`, module 1101-SP75, BitGroup7 = `1F` → bit 7 = 0 = "passive" limiting), per pack able to charge:

| Quantity | Formula | Result |
|---|---|---|
| CVL | parameter 14 (pack OVP) | **56.0 V** |
| DVL | parameter 12 (pack undervoltage alarm) | **46.4 V** |
| CCL | parameter 50 (charge OC warning 150 A) / 2 | **75.0 A** |
| DCL | \|parameter 52\| (155 A) − 10 A | **145.0 A** |

In addition, the CCL is set to 10 A total on warnings and to 0 A when a cell is > 3.65 V + 30 mV (details in section 3).

---

## 2. CAN driver *(confirmed)*

| Item | Finding |
|---|---|
| Controller | SJA1000/PeliCAN-like at `0x50020000` (registers on a 4-byte grid: MOD 0x00, CMR 0x04, SR 0x08, IER 0x10, BTR0 0x18, BTR1 0x1C, RXERR 0x38, TXERR 0x3C, TX buffer from 0x40) |
| Sending | `0xC4DA(base, ext, id, data, dlc, singleshot)`: 11- or 29-bit IDs, **single-shot** (no automatic retransmission), no waiting for a free TX buffer, busy-wait in between (`0x9B4C`, a few ms) |
| Initialization | `0x9A88`: acceptance filter open, **no interrupts**. **500 kbit/s** for all protocols, **100 kbit/s only for protocol 7 (MUST)** |
| Re-init | at boot and when switching **to or from** protocol 7 (ASCII 0xA6 / binary 0x63). Switching between 1–6: store only |
| Bus-off | `0x9B2E` before each send cycle: on bus-off, the error counters are reset and the controller is restarted |
| Reception | **none**: IER = 0, receive function `0xC580` is never called |
| Send dispatcher | `0xAEBA`, **once per main loop pass = 1 s** (call `0x621A` directly after the aggregation `0x99BA`). Sends only if `0x200000F7` bit 7 is set. `0x99BA` sets it only on the master (DIP 0) |
| Protocol selection | `0x20000024` (1…20). **0 and 8…20 send the protocol 1 set** |

### 2.1 Send timing *(confirmed, 06.13; constants identical in all versions)*

- **Period: 1 s.** The main loop is started by the measurement sequencer after timer 0 has ticked 200 times (5 ms each, clock = SystemCoreClock/200). At the end of each pass it calls the send dispatcher. The timing is therefore tied to a hardware timer, not to computation time; jitter arises only from the runtime of the preceding main loop.
- **Burst:** Per pass, **all** frames of the active protocol are sent back to back, without selection, counters or alternation between passes.
- **Gap between two frames:** wait loop `0x9B4C` with 5 × 5400 = 27,000 iterations (Victron/SMA partly 3 × 5400). At a **48 MHz** CPU clock (`SystemCoreClock`, set in `0xC814`, source via startup routine `0xC8FC`) and ≈ 5 cycles per loop iteration, this gives **≈ 2.8 ms** (Victron/SMA ≈ 1.7 ms). Possible flash wait states would lengthen the gap slightly *(order of magnitude confirmed, exact value only measurable)*.
- An 8-byte frame takes about 0.25 ms at 500 kbit/s (about 1.2 ms for MUST at 100 kbit/s); the gap is therefore sufficient before the next frame is written into the TX buffer. Since the driver sends **single-shot**, a lost frame is only replaced in the next burst (1 s later).
- Before each burst, `0x9B2E` checks for bus-off and restarts the controller if needed.

| Protocol | Frames per burst (order) | Burst duration |
|---|---|---|
| 1 PNG_DYE_Luxp_TBB (Deye/Pylontech) | 8: 0x351, 0x355, 0x356, 0x359, 0x370, 0x371, 0x35E, 0x35C | ≈ 20 ms |
| 2 Growatt | 7 (0x311–0x322) | ≈ 17 ms |
| 3 Victron | 16: 0x351, 0x355, 0x356, 0x35A, 0x35E, 0x35F, 0x370–0x379 | ≈ 31 ms |
| 4 SMA_SOFAR | same builder as Victron | – |
| 5 GINLONG | 6: 0x351, 0x355, 0x356, 0x359, 0x35E, 0x35C | ≈ 14 ms |
| 6 Studer | 5: 0x0A0, 0x0B0, 0x0B1, 0x0C0, 0x0C1 | ≈ 11 ms |
| 7 MUST | 4: 0x30100, 0x30200, 0x30400, 0x30500 | ≈ 9 ms |

For a capture this means: once per second, a packet of 4–16 frames arrives, spaced about 3 ms apart.

**Protocol table** (jump table at `0xAED0`)

| No. | Name | Frame builder | IDs |
|---|---|---|---|
| 1 (+0, 8–20) | PNG_DYE_Luxp_TBB | `0xA826` | 0x351, 0x355, 0x356, 0x359, 0x370, 0x371, 0x35E, 0x35C |
| 2 | Growatt_SPF_SPH | `0xABAA` | 0x311, 0x312, 0x313, 0x314, 0x319, 0x320, 0x322 (big-endian) |
| 3 | Victron | `0xA9BA` | 0x351, 0x355, 0x356, 0x35A, 0x35E, 0x35F, 0x370–0x379 |
| 4 | SMA_SOFAR | `0xA9BA` | 0x351, 0x355, 0x356, 0x35A, 0x35E, 0x35F |
| 5 | GINLONG | `0xA90C` | 0x351, 0x355, 0x356, 0x359, 0x35E, 0x35C |
| 6 | Studer | `0xAC74` | 0x0A0, 0x0B0, 0x0B1, 0x0C0, 0x0C1 (big-endian) |
| 7 | MUST | `0xAE4A` | 0x30100, 0x30200, 0x30400, 0x30500 (29 bit, 100 kbit/s) |

---

## 3. Limits and data source (master aggregation) *(confirmed)*

Before each CAN cycle, function `0x99BA` calls `0x94D2` (sums/extremes), `0x96CE` (counts/flags) and `0x98A8` (limits) in sequence. The source is the 30-byte pack records `0x20000524 + 30·i` (see [intra-pack.md](intra-pack.md)). The structures `0x2000164C` (system values), `0x20001634` (extremes) and `0x2000161E` (OR of the alarm events of all packs) are described in [modbus-rtu.md, section 2](modbus-rtu.md#2-data-source-system-aggregate-0x2000164c).

| Limit | Calculation |
|---|---|
| **CVL** | (parameter 14 "pack OVP" + 5)/10 → 0.1 V. Fixed, no reduction |
| **DVL** | (parameter 12 "pack undervoltage alarm" + 5)/10 → 0.1 V |
| **DCL** | \|parameter 52 "discharge OC warning"\| in 0.1 A; above 20.0 A → minus 10.0 A; × number of packs able to discharge without a warning. No ramp, no SOC or temperature derating |
| **CCL** | see below |

**CCL in order of priority:**
1. No pack may charge (charge MOS off or "Intermittent recharge waiting" on all packs) → **0, immediately**.
2. All packs able to charge have a charge-related warning (cell/pack high-voltage alarm, charge temperature, ambient/MOS temperature, charge OC, event 6 flags) → **10.0 A total**. This is the "max. 10 A on warning" rule mentioned in the Seplos documentation.
3. Otherwise, per pack able to charge:
   - Function switch `0x2000002F` **bit 7 = 1** (official name unknown; according to the Seplos specification, "Active/Passive current limiting" are BitGroup6 bit 6/7, i.e. something else): parameter 50 "charge OC warning", above 20 A minus 10 A
   - **Bit 7 = 0** (*"Passive"*): parameter 50 / 2
   - in each case × number of packs able to charge
4. **Heating:** function switch `0x2B` bit 6, highest cell temp. < 25 °C and lowest ≤ parameter 36 (off > parameter 37) → **at least pack count × 10.0 A**. This also applies if step 1 took effect. (06.11: 5 A per pack)
5. Highest cell > **parameter 4 (cell OVP) + 30 mV** → **0, immediately**.
6. **Ramp:** The CCL changes per cycle by at most (packs online × 1.0 A), both upward and downward.

There is **no SOC-dependent derating** of the current limits. The SOC only affects the force-charge bits and the 98 % cap.

**Status bits `0x200000F7`:**

| Bit | Meaning |
|---|---|
| 0 | discharging (≤ −0.8 A / off > −0.6 A) |
| 1 | charging (≥ +1.0 A / off < +0.8 A) |
| 2 | highest cell ≤ cell OVP + 30 mV |
| 3 | at least one pack may discharge |
| 4 | SOC ≤ 5 % (off > 10 %) |
| 5 | SOC ≤ 9 % (off > 13 %) |
| 6 | full charge request (no writer found, always 0) |
| 7 | master/sending active |

---

## 4. Protocol 1 "PNG_DYE_Luxp_TBB" (Pylontech: Deye, Luxpower, TBB …), byte by byte *(confirmed)*

All frames: standard 11-bit ID, DLC 8, little-endian, direction BMS → inverter.

### 0x351: Charge/discharge limits

| Byte | Content | Type / unit |
|---|---|---|
| 0–1 | **CVL** charge voltage limit | u16, 0.1 V |
| 2–3 | **CCL** charge current limit | u16, 0.1 A |
| 4–5 | **DCL** discharge current limit | u16, 0.1 A (positive) |
| 6–7 | **DVL** discharge voltage limit | u16, 0.1 V |

### 0x355: SOC / SOH

| Byte | Content | Type / unit |
|---|---|---|
| 0–1 | **SOC** of the system = (Σ remaining / Σ full) rounded. **If the system SOC is > 98 % but any pack is < 98 %, 98 is reported** | u16, % |
| 2–3 | **SOH = fixed 100** | u16, % |
| 4–5 | highest cell voltage (system) *(not Pylon standard)* | u16, mV |
| 6–7 | lowest cell voltage (system) *(not Pylon standard)* | u16, mV |

### 0x356: Voltage / current / temperature

| Byte | Content | Type / unit |
|---|---|---|
| 0–1 | voltage = **average** of the pack voltages | u16, 0.01 V |
| 2–3 | current = **sum** of all packs, + = charging. Dead band: 0 between approx. −0.8 A and +1.0 A | s16, 0.1 A |
| 4–5 | highest cell temperature (system) | s16, 0.1 °C |
| 6–7 | lowest cell temperature (system) *(Pylon: unused)* | s16, 0.1 °C |

### 0x359: Protection / alarms

| Byte | Bit | Meaning | Source (OR of all packs) |
|---|---|---|---|
| 0 | – | Protection 1: **always 0** | – |
| 1 | – | Protection 2: **always 0** | – |
| 2 | 1 | High Voltage | highest cell > cell OVP + 30 mV |
| 2 | 2 | Low Voltage | Event 2 & 0xCC (cell/pack undervoltage alarm + protection) |
| 2 | 3 | High Temperature | Event 3 & 0x33 (charge/discharge overtemp. alarm + protection) |
| 2 | 4 | Low Temperature | Event 3 & 0xCC |
| 2 | 7 | Discharge Overcurrent | Event 5 & 0xF8 (discharge OCP, transient, short circuit, lockouts) |
| 3 | 0 | Charge Overcurrent | Event 5 bit 1 (charge OC **protection**) |
| 3 | 3 | System/Internal Communication Error | slave offline ≥ 30 cycles (`0x20000000` bit 3) |
| 3 | 4 | cell difference fault (*not Pylon standard*) | Event 1 bit 4 |
| 4 | – | module count = configured packs | u8 |
| 5–6 | – | **total nominal capacity in Ah** (packs × parameter 58) **instead of "PN"** | u16 |
| 7 | – | online bitmask of the packs (bit 0 … 7) | u8 |

Charge/discharge OC **alarms** (event 5 bit 0/2) and overvoltage **alarms** from event 2 are not reported. Overvoltage only appears via the threshold cell OVP + 30 mV.

### 0x370 / 0x371: Extremes (not Pylon standard)

| ID | Byte | Content |
|---|---|---|
| 0x370 | 0–1 / 2–3 | highest / lowest cell temperature (s16, 0.1 °C) |
| 0x370 | 4–5 / 6–7 | highest / lowest cell voltage (u16, mV) |
| 0x371 | 0 / 2 / 4 / 6 | pack number (1-based) of max. temp. / min. temp. / max. cell voltage / min. cell voltage; bytes 1, 3, 5, 7 = 0 |

### 0x35E: Manufacturer name

`53 48 45 6E 65 72 67 79` = **"SHEnergy"**

### 0x35C: Request flags

| Byte | Bit | Meaning | Condition |
|---|---|---|---|
| 0 | 7 | **Charge Enable** | CCL ≠ 0 (since 06.11) |
| 0 | 6 | **Discharge Enable** | at least one pack may discharge |
| 0 | 5 | **Force Charge Request I** | SOC ≤ 5 % (off > 10 %), only if no cell overvoltage |
| 0 | 4 | **Force Charge Request II** | SOC ≤ 9 % (off > 13 %), only if no cell overvoltage |
| 0 | 3 | Full Charge Request | never set |
| 1 | – | 0 | |
| 2–3 | – | **cycle count of the master pack** (u16) *(not Pylon standard)* | |
| 4–7 | – | 0 | |

Not sent: 0x35A, 0x35F, 0x372–0x37F and extended IDs.

### Practical consequences

- Deye charges up to the **pack OVP threshold** (CVL). Throttling comes only via the CCL (10 A on warning, 0 A when a cell is > OVP + 30 mV). Anyone wanting a lower end-of-charge voltage has to lower parameter 14. *(code confirmed, assessment assumption)*
- Because 0x359 never reports "Protection", the inverter does not shut down because of a protection bit. The BMS protects itself via its MOSFETs and CCL = 0. *(code confirmed, inverter reaction assumption)*
- During "Intermittent recharge waiting" (charging stopped after 100 % until SOC < parameter 80), the pack counts as charge-blocked. If all packs are affected, **CCL = 0** and Charge Enable = 0 follow, even without the SP80 MOSFET shutdown. *(confirmed)*

---

## 5. Other protocols (06.13)

### 5 GINLONG (`0xA90C`)

| ID | Content |
|---|---|
| 0x351 | as protocol 1 |
| 0x355 | SOC % (98 % cap), SOH 100, rest 0 |
| 0x356 | V 0.01 V, I 0.1 A, **ambient temperature of the master pack** (0.1 °C), bytes 6–7 = 0 |
| 0x359 | bytes 0–3 as protocol 1, bytes 4–7 = 0 |
| 0x35E | "PYLON " + total nominal capacity Ah (u16) |
| 0x35C | bit 7 Charge Enable = highest cell ≤ OVP + 30 mV (not CCL ≠ 0), bits 6/5/4/3 as protocol 1 |

### 3 Victron / 4 SMA_SOFAR (`0xA9BA`)

| ID | Content | Victron only |
|---|---|---|
| 0x351 | as protocol 1 | |
| 0x355 | SOC %, SOH 100, SOC in 0.01 % (bytes 4–5) | |
| 0x356 | V 0.01 V, I 0.1 A, ambient temp. master 0.1 °C, cycles master | |
| 0x35A | 2-bit fields (01 active / 10 inactive). **Alarm bytes 0–3 fixed "inactive"** (`AA AA AA 02`). Warnings: byte 4 HV/LV/discharge high temp., byte 5 low temp./charge high/low temp./discharge OC, byte 6 charge OC/short circuit/BMS internal, byte 7 cell imbalance | |
| 0x35E | "SHEnergy" | |
| 0x35F | FW version `10 06` (bytes 2–3), Σ full capacity Ah (bytes 4–5) | |
| 0x370 / 0x371 | ASCII "CAN-SMAR" / "TBMS-BAT" (name "CAN-SMARTBMS-BAT") | ✔ |
| 0x372 | packs with both MOS on / charging blocked / discharging blocked / offline (u16 each) | ✔ |
| 0x373 | min./max. cell voltage mV, min./max. cell temperature K | ✔ |
| 0x374–0x377 | ASCII "Pack-NN#" for min. V / max. V / min. T / max. T (incorrectly encoded from pack 20 onward) | ✔ |
| 0x378 | 2 × u32 from `cc8+0x58/+0x5C`: charged / discharged energy in 0.1 kWh | ✔ |
| 0x379 | Σ full capacity Ah | ✔ |

SMA_SOFAR only sends up to and including 0x35F.

### 2 Growatt_SPF_SPH (`0xABAA`, big-endian)

| ID | Content |
|---|---|
| 0x311 | CVL, CCL, DCL (0.1 V/A); byte 7 status: 3 discharging / 2 charging / 1 idle, \|0x08, \|0x20 discharging possible, \|0x40 charging possible |
| 0x312 | bytes 2/3 fault and alarm bits (under-/overvoltage, OC, communication, cell difference, temperatures); byte 4 pack count; byte 7 packs × cells |
| 0x313 | V 0.01 V, I 0.1 A, max. cell temp. 0.1 °C, SOC %, SOH 100 |
| 0x314 | Σ remaining/full capacity 0.01 Ah (u16, overflow from 655 Ah), cell difference mV, cycles master |
| 0x319 | flags (as 0x35C), max./min. cell mV, pack no. |
| 0x320 | 'G','T', FW version `10 06` |
| 0x322 | max./min. cell temp., pack no., max./min. SOC |

### 6 Studer (`0xAC74`, big-endian)

| ID | Content |
|---|---|
| 0x0A0 | byte 0 charging/discharging forbidden, force flags; byte 1 communication error, cell difference, short circuit; byte 2 warning bits; byte 7 = 0x10 |
| 0x0B0 | V 0.1 V, I 0.1 A, max. cell temp., SOC %, SOH 100 |
| 0x0B1 | Σ full/remaining capacity Ah, max./min. cell temp. |
| 0x0C0 | CCL, CCL + 10 A, CVL, (parameter 19 + 5)/10 |
| 0x0C1 | DCL, DCL + 10 A, DVL, 0 |

### 7 MUST (`0xAE4A`, 29-bit, **100 kbit/s**)

| ID | Content |
|---|---|
| 0x00030100 | CVL 0.1 V, CCL 0.1 A, **DVL** 0.1 V, **DCL** 0.1 A (different order than 0x351) |
| 0x00030200 | byte 4 = 1 charging forbidden, byte 6 = 1 discharging forbidden |
| 0x00030400 | V 0.1 V, I 0.1 A, ambient temp. master (1 °C), byte 6 alarm bits |
| 0x00030500 | SOC %, SOH 100, SOC 0.01 % |

---

## 6. CAN version history *(confirmed)*

| Transition | Change | Effect on Deye/protocol 1 |
|---|---|---|
| 04.06 → 06.03 | If all packs are charge-blocked, the **CCL becomes 0 immediately** (previously only via the ramp). MUST frame code appears as **dead code** | yes: faster 0 A report |
| 06.03 → 06.05 | no CAN change | – |
| **06.05 → 06.11** | **MUST** becomes selectable (name, dispatcher case 7, 100 kbit/s; in 06.05 value 7 fell through to the protocol 1 set). **0x35C Charge Enable = "CCL ≠ 0"** instead of "cell ≤ OVP + 30 mV". **Heating minimum current** (CCL ≥ packs × 5 A). **CCL = 0 immediately** when cell > OVP + 30 mV. With more than one pack able to charge, still always half the charge OC warning per pack | yes |
| **06.11 → 06.12** | The active/passive selection (`0x2F` bit 7) now applies to **any pack count**; previously always passive with multi-pack. **Heating minimum current 5 A → 10 A per pack** | yes: multi-pack with "active" gets considerably more CCL (e.g. 2 packs, warning 61 A: 06.11 = 61.0 A, 06.12 = 102.0 A) |
| 06.12 → 06.13 | Protocol 1 **unchanged**. Victron/SMA only: 0x35F capacity is now a rounded 32-bit sum, 0x379 = Σ measured full capacity instead of packs × nominal capacity | no |

The literal constants 0x377 (887), 0x3D6 (982) and 0x3DE (990) do not belong to protocol 1. 0x377 is a base in the Victron/Growatt builder; 982/990 are used in SOC/capacity logic (`0x9044`, `0x8C08`).

## 7. Open

- Exact frame gap within a burst (≈ 2.8 ms calculated; exact only by measurement, due to possible flash wait states).
- Official names of the function switch bits `0x2F` bit 7 and `0x2B` bit 6 (effect clarified: CCL mode and cell heating respectively, see [configuration-parameters](../configuration-parameters.md#5-function-switches-bitgroup07)).
