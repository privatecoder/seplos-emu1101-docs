# Seplos BMS 2.0/10E/V16 (EMU1101): CAN inverter protocols

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

What the BMS sends to the inverter via CAN. The focus is **protocol 1 "PNG_DYE_Luxp_TBB"**, the Pylontech-compatible protocol used with **Deye** and Luxpower. Basis is the disassembly up to V16.06.13; addresses apply to 06.13.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2, inverter protocols and available monitoring/service paths. Availability depends on the **active requester on each bus**, not the number of sockets or gateways.

Confidence: **confirmed** = directly from the code · **probable** · **assumption**. All multi-byte fields are **little-endian**, except for Growatt and Studer (big-endian).

---

## Manufacturer CAN specification: scope and differences

[Seplos BMS CAN Protocoll V1.0.pdf](<../../vendor/docs/protocol%20specs/Seplos%20BMS%20CAN%20Protocoll%20V1.0.pdf>) is the original **SEPLOS CANBUS Protocol V1.0**, copyright 2020. It has six PDF pages including the cover; printed pages 1–5 correspond to PDF pages 2–6. File metadata gives 2020-06-13. SHA-256: `264cdf6e2348c121ffd04b9af287f55b038702862c36a3b333d06a1fe8ddb0a6`.

It is a useful primary source for the intended Pylontech-style CAN layout. It does not identify 10E/V16 or OEM16.06.13 and is not a specification for UART1/RS485, all selectable CAN profiles, or MAINT services. Firmware addresses and behavior below refer to OEM .13. Manufacturer statements and code-derived behavior are distinguished; no hardware capture was performed.

| Subject / PDF page | Manufacturer document | OEM .13 implementation and interpretation |
|---|---|---|
| Timing and frame type, p.2 | Standard CAN, 500 kbit/s, one-second cycle. Declares compatibility with Pylontech V1.3 and Goodwe V1.5. | Corroborates profile 1's 11-bit/500 kbit/s, one-second burst. It does not cover the MUST 29-bit/100 kbit/s exception or independently certify a particular inverter. See driver/dispatcher `0x9A88`/`0xAEBA`. |
| Inverter heartbeat, p.2 | Requests inverter `0x305` with eight zero bytes every second. | No application receive/heartbeat-timeout path is used: CAN interrupts are disabled and receive routine `0xC580` is not called. Do not infer that missing `0x305` causes a firmware communication alarm or exposes an incoming control command. CAN link-layer acknowledgement is separate from this application heartbeat. |
| DIP role/address, pp.2–3 | Slaves 1–15 use DIP1–4; master DIP5–8 table covers 2–15 total packs. | Consistent with DIP5–8 encoding **slave count**, not total packs. For two packs only DIP5 is ON. Unlike the conflicting H150/H200 tables, this table leaves DIP8 OFF for 2–8 packs. Its omitted 16-pack row is not proof of a 15-pack firmware limit. |
| `0x351`, pp.4–5 | Charge voltage/current limit, discharge current limit/voltage, 0.1 V/A units; low byte first (note on p.6). | Corroborates the existing offsets/scales. It gives no derivation for CVL/CCL/DCL, heating overrides or ramp behavior; those come from `0x98A8` and the frame builders. |
| `0x355`, p.5 | 16-bit SOC/SOH in whole percent; single module or system average. | Confirms field positions/scales, not an averaging algorithm. OEM .13 fixes SOH at 100 and has its own aggregate SOC and 98% cap. A published SOH field is not proof of a working health estimator. |
| `0x356`, p.5 | Voltage 0.01 V, current 0.1 A and temperature 0.1 °C; voltage labelled signed. | Offsets/scales match; the decoded firmware table below treats voltage as unsigned. Profile 1 additionally fills bytes6–7 with minimum cell temperature. The PDF does not specify that extra field or the selected temperature source. |
| `0x359`, pp.3–4 | Bytes0/1 protection and bytes2/3 warnings, plus pack count and an online bitmap for addresses0–7. | In profile 1, **protection bytes0/1 stay zero**; native protection conditions are partly mapped into bytes2/3 (`0x9CE0`). Bytes5–6 contain total nominal Ah, unspecified in the PDF. Byte7 covers only addresses0–7 and cannot enumerate all 16 packs. Do not decode the generic protection table as observed native output. |
| `0x35C`, p.5 | Byte0 bits7/6 charge/discharge enable, bits5/4 force-charge requests I/II. | Corroborates the bit names. Thresholds/hysteresis, CCL-dependent enable and the master's cycle count in bytes2–3 remain firmware findings; they are not defined here. |
| Extreme-values frame, pp.5–6 | The PDF literally prints ID **`0x70`**; its cell-voltage entries incorrectly use temperature units and signed type. | The examined profile 1 sends **`0x370`**, cell voltages **unsigned mV**. The matching temperature/voltage layout suggests a missing `3` and copied field descriptions in the PDF; use the code-derived ID/types, not the literal typo. |
| `0x371`, p.6 | Four 16-bit extremum-location fields without an explanation of their numbering. | The builder supplies one-based **pack numbers**, with the high bytes zero, rather than a complete cell-address encoding. The source alone does not define that distinction. |
| `0x35E`, p.6 | Incomplete manufacturer ASCII table with the text “Energy” and only Byte0/Byte1 labels. | The actual eight bytes are `53 48 45 6E 65 72 67 79`, **SHEnergy**. The PDF cannot supply a complete eight-byte literal or a serial identity. |

Use this PDF as protocol provenance and the code-derived tables below as the OEM .13 decoder contract. It supplies no addressed CAN parameter writes, power/reset control, clock setting or individual-slave CAN query. Those remote functions use the separately wired UART1 RS485 pair where supported by MAINT. The manufacturer's declared compatibility does not replace an exact frame/profile match.

## 1. Summary for protocol 1

- **Only the master pack (DIP address 0) sends CAN.** Slaves are silent on CAN. *(confirmed)*
- **Almost all values are system values across all online packs** (exceptions: the cycle count in 0x35C and the ambient temperature and cycles in 0x356 for GINLONG and Victron/SMA are the master's own values, `0x9C9A`–`0x9CB2`). The master collects them via the intra-pack protocol (0x5A): voltage = average, current and capacity = sum, cell extremes across all packs. *(confirmed)*
- **500 kbit/s**, 11-bit IDs. Roughly once per main loop tick, the set **0x351 → 0x355 → 0x356 → 0x359 → 0x370 → 0x371 → 0x35E → 0x35C** is sent *(confirmed; one-second scheduler period, with runtime jitter as described in §2.1)*.
- **The BMS receives nothing via CAN.** Heartbeat 0x305 and other frames from the inverter are ignored; there is no timeout. *(confirmed)*
- **Manufacturer name in 0x35E: "SHEnergy"**, not "PYLON". *(confirmed)*
- **0x359 bytes 0/1 (the Pylontech "Protection" fields) are always 0.** Some protection states are nevertheless mapped into the alarm bytes: cell/pack under-voltage protection (event 2 bits 3/7) and charge over-current protection (event 5 bit 1). *(confirmed, 16.06.13 `0x9CE0`)*
- **SOC stays at 98 %** until every pack is at least 98 % (and the system SOC is above 98 %). *(confirmed)*
- **CVL is fixed** to the parameter "pack overvoltage protection". There is no absorption/float reduction. Throttling happens only via the charge current limit (CCL). *(confirmed)*

**Schematic configuration example:** assume BitGroup7 bit 7 = 0 ("passive" limiting) and the illustrative parameter values below. These values are synthetic, not a parameter export or an operating recommendation. Results are per pack able to charge:

| Quantity | Formula | Result |
|---|---|---|
| CVL | parameter 14 (pack OVP), assumed 57.6 V | **57.6 V** |
| DVL | parameter 12 (pack undervoltage alarm), assumed 44.8 V | **44.8 V** |
| CCL | parameter 50 (assumed charge OC warning 80 A) / 2 | **40.0 A** |
| DCL | \|parameter 52\| (assumed magnitude 90 A) − 10 A | **80.0 A** |

In addition, the CCL is set to 10 A total on warnings and to 0 A when a cell is > parameter 4 (cell OVP) + 30 mV (details in section 3).

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
| 4 SMA_SOFAR | 6: 0x351, 0x355, 0x356, 0x35A, 0x35E, 0x35F | ≈ 12 ms |
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

Function `0x99BA` runs before each CAN cycle, but only calls `0x94D2` (sums/extremes), `0x96CE` (counts/flags) and `0x98A8` (limits) once a polling round over all slaves is complete (`0x20000000` bit 2, `0x99C0`; without slaves, `0x12E2` sets the bit every second). In between, CAN resends the last computed values. At 150 ms per slave, the system values with 11 slaves are therefore refreshed about every 2 s, not every second. *(confirmed)* The source is the 30-byte pack records `0x20000524 + 30·i` (see [intra-pack.md](intra-pack.md)). The structures `0x2000164C` (system values), `0x20001634` (extremes) and `0x2000161E` (OR of the alarm events of all packs) are described in [modbus-rtu.md, section 2](modbus-rtu.md#2-data-source-system-aggregate-0x2000164c).

| Limit | Calculation |
|---|---|
| **CVL** | (parameter 14 "pack OVP" + 5)/10 → 0.1 V. Fixed, no reduction |
| **DVL** | (parameter 12 "pack undervoltage alarm" + 5)/10 → 0.1 V |
| **DCL** | \|parameter 52 "discharge OC warning"\| in 0.1 A; above 20.0 A → minus 10.0 A; × number of packs able to discharge without a warning. No ramp or continuous SOC/temperature derating curve; discrete discharge warnings, including low-SOC and temperature warnings, remove a pack from the eligible count |
| **CCL** | see below |

**CCL in order of priority:**
1. No pack may charge (charge MOS off or "Intermittent recharge waiting" on all packs) → **0, immediately**.
2. All packs able to charge have a charge-related warning (cell/pack high-voltage alarm, charge temperature, ambient/MOS temperature, charge OC, event 6 flags) → **10.0 A total**. This is the "max. 10 A on warning" rule mentioned in the Seplos documentation.
3. Otherwise, per pack able to charge:
   - Function switch `0x2000002F` **bit 7 = 1** (official name unknown; according to the Seplos specification, "Active/Passive current limiting" are BitGroup6 bit 6/7, i.e. something else): parameter 50 "charge OC warning", above 20 A minus 10 A
   - **Bit 7 = 0** (*"Passive"*): parameter 50 / 2
   - in each case × number of packs able to charge **without a charge-related warning**; every warning pack drops out of the sum, only when none is left does item 2 apply (10 A total) (`0x96CE`, `0x98D4`)
4. **Heating:** function switch `0x2B` bit 6, highest cell temp. < 25 °C and lowest ≤ parameter 36 (off > parameter 37) → **at least pack count × 10.0 A**. This also applies if step 1 took effect. (06.11: 5 A per pack)
5. Highest cell > **parameter 4 (cell OVP) + 30 mV** → **0, immediately**.
6. **Ordinary ramp:** at most (packs online × 1.0 A) per aggregate update, upward or downward. Steps 1 and 5 first write 0 directly to the stored CCL; step 4 writes a raised heating minimum directly. Those overrides therefore take effect immediately and are not delayed by the ordinary ramp (`0x98F8–0x98FC`, `0x9940–0x994C`, `0x9956–0x995A`, ramp `0x995C–0x9986`).

There is **no continuous SOC-dependent current-limit curve**. Low-SOC warning (event 6 bit 2, P78) can nevertheless exclude a pack from the discharge-capable count and reduce DCL (`0x96CE`; aggregate `+0x04`). SOC also controls force-charge requests and the 98 % reporting cap. Temperature warnings likewise affect eligibility rather than applying a continuous derating curve.

**Status bits `0x200000F7`:**

| Bit | Meaning |
|---|---|
| 0 | discharging (≤ −0.8 A / off > −0.6 A) |
| 1 | charging (≥ +1.0 A / off < +0.8 A) |
| 2 | highest cell ≤ cell OVP + 30 mV |
| 3 | at least one pack may discharge |
| 4 | SOC ≤ 5 % (off > 10 %) |
| 5 | SOC ≤ 9 % (off > 13 %); cleared while force-charge-I bit 4 is set |
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
| 0 | 4 | **Force Charge Request II** | SOC ≤ 9 % (off > 13 %), suppressed while request I is active; only if no cell overvoltage |
| 0 | 3 | Full Charge Request | never set |
| 1 | – | 0 | |
| 2–3 | – | **cycle count of the master pack** (u16) *(not Pylon standard)* | |
| 4–7 | – | 0 | |

Not sent: 0x35A, 0x35F, 0x372–0x37F and extended IDs.

### Practical consequences

- The inverter charges up to the **pack OVP threshold** (CVL). Throttling comes only via the CCL (10 A on warning, 0 A when a cell is > OVP + 30 mV). Anyone wanting a lower end-of-charge voltage has to lower parameter 14. *(code confirmed, assessment assumption)*
- Because the Protection fields of 0x359 stay 0, an inverter that only evaluates those fields does not shut down because of a protection bit; some protection states still appear in the alarm bytes. The BMS protects itself via its MOSFETs and CCL = 0. *(code confirmed, inverter reaction assumption)*
- During "Intermittent recharge waiting" (charging stopped after 100 % until SOC < parameter 80), the pack counts as charge-blocked. If all packs are affected, **CCL = 0** and Charge Enable = 0 follow, even without the SP80 MOSFET shutdown, unless a heating request raises the CCL to the heating minimum (step 4); ordinary changes follow the ramp, while all-blocked zero and a raised heating minimum use the immediate overrides described above. *(confirmed)*

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
- Official names of the function switch bits `0x2F` bit 7 and `0x2B` bit 6 (effect clarified: CCL mode and cell heating respectively, see [configuration-parameters](../firmware/configuration-parameters.md#5-function-switches-bitgroup07)).
