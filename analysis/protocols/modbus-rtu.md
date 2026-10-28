# Seplos BMS 2.0/10E/V16 (EMU1101): Modbus RTU (inverter port), undocumented

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The firmware contains a complete **Modbus RTU slave** on the inverter-side RS485 interface. None of the Seplos PDFs mention it. Basis: disassembly of V16.04.06 to V16.06.13, addresses for **06.13**.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2, inverter protocols and available monitoring/service paths. Availability depends on the **active requester on each bus**, not the number of sockets or gateways.

Confidence: **confirmed** = directly from the code · **probable** · **assumption**.

---


**Scope:** these tables describe UART1 (RS485 pair of the CAN socket), especially OEM16.06.13. UART0 does not implement this map or this Modbus slave in .13. UART1 is occupied if an inverter polls it; a second uncoordinated requester is unsupported. Master address 0 works even without slaves, but then reports a one-pack aggregate.

## 1. Framing and rules

| Item | Behavior | Confidence |
|---|---|---|
| Slave ID | only **0x01** is answered | confirmed |
| Who answers | only the **master pack** (DIP address 0). Function `0x99BA` sets the enable bit `0x200000F7.7`; if the DIP address is ≠ 0, it is cleared | confirmed (bit), probable (purpose) |
| Function codes | **03** (holding) and **04** (input), otherwise exception **01** | confirmed |
| Start address | only the ones listed below, otherwise exception **02** | confirmed |
| Register count | **fixed per start address** (only the low byte is checked). Any other count → exception **03**. Partial ranges are not possible | confirmed |
| Byte order | big-endian, 16-bit registers | confirmed |
| CRC | Modbus CRC16, appended in `0x4554` | confirmed |
| In parallel | Pylontech ASCII frames (`~…`) are also answered on the same port, see [pylontech-rs485.md](pylontech-rs485.md) | confirmed |

UART1 receive separation and ready-buffer ownership apply to this protocol too. Use one coordinated requester and a practical initial pause of 200 ms after a complete answer; see [UART1 receive timing and its limits](uart1-receive-gap-and-buffer-ownership.md).

**Valid start/count combinations (06.13)**

| FC | Start | Count | Handler |
|---|---|---|---|
| 03 | 0x0000 | 0x0C (12) | `0x32B8` (PACE) |
| 03 | 0x0000 | 0x1C (28) | `0x3BCC` |
| 03 | 0x0001 | 0x0F / 0x23 / 0x28 | `0x2B80` / `0x2BA6` / `0x2DF0` |
| 03 | 0x0010 | 0x13 (19) | `0x301E` |
| 03 | 0x0013 | 0x11 (17) | `0x357E` |
| 03 | 0x001F | 0x09 | `0x34BC` (**new in 06.13**) |
| 03 | 0x0025 | 0x03 | `0x352E` |
| 03 | 0x0033 | 0x01 | `0x426C` |
| 03 | 0x0034 | 0x02 | `0x4292` |
| 03 | 0x0070 | 0x11 (17) / 0x01 | `0x3264` / `0x42BA` |
| 03 | 0x0071 … 0x0074 | 0x01 each | `0x42D6`, `0x42F2`, `0x430E`, `0x432A` |
| 03 | 0x1000 | 0x15 (21) | `0x3A08` |
| 03 | 0x9000 | 0x1A (26) (up to 06.12: 0x15) | `0x3898` |
| 04 | 0x0000 / 0x0015 / 0x0028 / 0x3100 | see section 4 | `0x3DAA` / `0x3EB0` / `0x41A4` / `0x364A` |

### ⚠ Non-compliant responses (16-bit byte count)

The handlers for **0x0033, 0x0034, 0x0070 (count 1) and 0x0071–0x0074** write a **16-bit byte count**:

```
01 03 00 02 HH LL CRC CRC              (instead of  01 03 02 HH LL CRC CRC)        single register
01 03 00 04 D0 D1 D2 D3 CRC CRC        (instead of  01 03 04 D0 D1 D2 D3 CRC CRC)  0x0034, 2 registers (`0x4292`)
```

A standard Modbus master reads this as byte count = 0 plus one surplus byte before the data. *(confirmed: code; probably a bug, possibly intentional for a proprietary master)*

---

## 2. Data source: system aggregate `0x2000164C`

Almost all registers come from a system structure. Function `0x99BA` computes it cyclically via `0x94D2`/`0x96CE`/`0x98A8` from the multi-pack table `0x20000524`, i.e. its own values plus the slave values read via CID2 0x5A (see [intra-pack.md](intra-pack.md)). With a single pack, these are the pack's own values. *(confirmed)*

| Offset | Type | Content | Confidence |
|---|---|---|---|
| +0x00 | u8 | configured pack count = slave count (`0x20000026`) + 1 | confirmed |
| +0x01 | u8 | number of packs online (including itself) | confirmed |
| +0x02 | u8 | counter "not all packs online"; from 30 → `0x20000000.3` = communication error | confirmed |
| +0x03 | u8 | packs that **may charge**: charge MOS or current limiting on **and** no charge-blocking alarm (Ev2&0x33, Ev3 bit 0–3, Ev4 bit 0–5, Ev5 bit 0–1, Ev6&0x73, Ev7 bit 6–7) | confirmed |
| +0x04 | u8 | packs that **may discharge**: On-off&0x11 and no discharge alarms (Ev2&0x44, Ev3&0x50, Ev4&0x25, Ev5 bit 2, Ev6 bit 2) | confirmed |
| +0x06 | u8 | packs with **charging blocked**: charge MOS and current limiting off **or Ev6 bit 1 "Intermittent recharge waiting"** | confirmed |
| +0x07 | u8 | packs with discharging blocked (On-off&0x11 = 0) | confirmed |
| +0x0C | i32 | **total current**, 0.1 A (+ = charging). Dead band: "discharging" from ≤ −0.8 A (off > −0.6 A), "charging" from ≥ +1.0 A (off < +0.8 A). Without one of the two flags, 0 is reported | confirmed |
| +0x10 | u32 | average pack voltage, 0.01 V | confirmed |
| +0x14 | u32 | average port voltage, 0.01 V | confirmed |
| +0x18 | u32 | sum of remaining capacity, 0.1 Ah | confirmed |
| +0x1C | u32 | sum of full capacity, 0.1 Ah | confirmed |
| +0x20 | u16 | **system SOC** = remaining·1000/full, 0.1 %, max. 1000 | confirmed |
| +0x22 | u16 | **CVL** (charge voltage limit) = (parameter 14 "pack OVP" + 5)/10 → 0.1 V | confirmed |
| +0x24 | u16 | **CCL** (charge current limit), 0.1 A, see below | confirmed |
| +0x26 | u16 | **DVL** (discharge voltage limit) = (parameter 12 "pack undervoltage alarm" + 5)/10 → 0.1 V | confirmed |
| +0x28 | u16 | **DCL** (discharge current limit), 0.1 A = (−parameter 52 "discharge OC warning" + 5)/10; above 20.0 A minus 10.0 A; × (+0x04) | confirmed |

**CCL calculation** (`0x98A8`): *(confirmed)*
1. Base = parameter 50 ("charge OC warning") in 0.1 A.
   - Function switch `0x2000002F` **bit 7 set**: above 20.0 A → minus 10.0 A
   - Bit 7 **not set**: halved
2. × number of packs able to charge (+0x03). If (+0x03) = 0, a flat 10.0 A applies.
3. If all online packs are charge-blocked (+0x06 ≥ +0x01): **0 immediately**, written to the stored CCL before the ramp.
4. Heating charge request `0x200000F8.2` active (function switch `0x2B` bit 6, max. cell temp. < 25.0 °C, min. temp. ≤ parameter 36): **at least configured pack count × 10.0 A**, including when step 3 applied; a raised minimum is written directly to the stored CCL (`0x9940–0x994C`).
5. `0x200000F7.2` = 0 (highest cell > parameter 4 cell OVP + 30 mV): **0 immediately**, overriding heating (`0x9956–0x995A`).
6. **Ordinary ramp:** per aggregate update at most ± (packs online × 1.0 A). The direct stores in steps 3–5 bypass this delay; see [CAN limit ordering](can.md#3-limits-and-data-source-master-aggregation-confirmed).

Synthetic scaling example (not an operating recommendation): parameter 50 = 100 A, bit 7 of BitGroup7 = 0 → halved → **50 A per pack**. DCL: parameter 52 = −105 A → 105 − 10 = **95 A per pack**. CVL = 56.0 V (parameter 14), DVL = 46.4 V (parameter 12).

**Status flags `0x200000F7`** *(confirmed)*

| Bit | Meaning |
|---|---|
| 0 | discharging (I ≤ −0.8 A; off > −0.6 A) |
| 1 | charging (I ≥ +1.0 A; off < +0.8 A) |
| 2 | charging allowed (highest cell ≤ cell OVP + 30 mV) |
| 3 | at least one pack may discharge |
| 4 | SOC ≤ 5.0 % (off > 10.0 %): force charge I |
| 5 | SOC ≤ 9.0 % (off > 13.0 %; cleared when bit 4 is set): force charge II |
| 7 | inverter Modbus active (master only) |

**Further aggregates:**
- `0x2000161E[0…8]` = **bitwise OR across all packs** of Ev1, Ev2, Ev3, Ev4, Ev5, Ev6&0x7F, On-off, Ev7, Ev8.
- `0x20001634`: +0/+2 max./min. cell voltage (mV), +4/+6 max./min. cell temperature (0.1 K).
- `0x20001627[0…3]`: 1-based pack number of max./min. cell and max./min. temperature.
- `0x20000C48`: temperatures in 0.1 °C (signed), 8-byte records, value at +6. Index 0–3 cells, 4 ambient, 5 power stage.

---

## 3. Holding registers (FC 03)

### 3.1 `0x0000` × 12: **PACE BMS Modbus V1.3** (mapping confirmed, identical to [PACE BMS Modbus Protocol RS485 V1.3.pdf](<../../references/other-vendors/PACE/PACE%20BMS%20Modbus%20Protocol%20RS485%20V1.3.pdf>))

| Reg | Content | Unit |
|---|---|---|
| 0x00 | current (+0x0C)·10, int16, + = charging | 10 mA, **overflow from ±327 A** |
| 0x01 | pack voltage | 10 mV |
| 0x02 | SOC | % |
| 0x03 | SOH = **fixed 100** | % |
| 0x04 | total remaining capacity | 10 mAh, **u16 overflow from 655 Ah** |
| 0x05 | total full capacity | 10 mAh, same |
| 0x06 | nominal capacity = parameter 58 × pack count | 10 mAh, same (at 280 Ah already from 3 packs) |
| 0x07 | cycles (own pack) | – |
| 0x08 | 0 | – |
| 0x09 | warning flags (see below) | bits |
| 0x0A | protection flags = **always 0** | – |
| 0x0B | status (see below) | bits |

Reg 0x09 (PACE meaning in parentheses):
- b0 = highest cell > OVP + 30 mV (cell OV)
- b1 = Ev2 b2|b3 (cell UV)
- b2 (pack OV) is **never** set
- b3 = Ev2 b6|b7 (pack UV)
- b4 = Ev5 b1 (charge OC)
- b5 = Ev5 b3…b7 (discharge OC/short circuit)
- b8 = Ev3 b0|b1 (charge high temp.)
- b9 = Ev3 b4|b5 (discharge high temp.)
- b10 = Ev3 b2|b3 (charge low temp.)
- b11 = Ev3 b6|b7 (discharge low temp.)
- b12 = Ev4 b0|b1 (ambient high)
- b13 = Ev4 b2|b3 (ambient low)
- b14 = Ev4 b4|b5 (MOSFET temp.)
- b15 = SOC < 15.0 % (SOC low)

Reg 0x0B: b8 charging, b9 discharging, b10 charge MOS on (not all packs blocked), b11 discharge MOS on. The fault bits b0–b7 are always 0.

### 3.2 `0x0000` × 28 (since 06.11)

| Reg | Content | Unit |
|---|---|---|
| 0x00 | **0x0641** (1601), constant | identifier? *(assumption)* |
| 0x01–0x04 | 0 | |
| 0x05–0x09 | device name, 10 ASCII characters (`EMU110110E`), 2 per register | |
| 0x0A | 0 | |
| 0x0B | total full capacity | Ah |
| 0x0C | 0 | |
| 0x0D | **0x3EC4** (16068), constant | ? |
| 0x0E–0x12 | 0 | |
| 0x13 | status: 1 idle / 2 charging / 3 discharging; \|0x04 no force charge, \|0x08 always, \|0x40 discharging allowed, \|0x80 charging allowed | bits |
| 0x14 | alarm: b0 an Ev5 bit, b4 Ev3 b4\|5, b5 Ev3 b0\|1, b6 Ev3 b6\|7, b7 Ev3 b2\|3 | bits |
| 0x15 | SOC | % |
| 0x16 | voltage | 0.01 V |
| 0x17 | current ·10, int16 | 0.01 A |
| 0x18 | ambient temperature | °C (signed) |
| 0x19 / 0x1A | CCL·10 (duplicated) | 0.01 A |
| 0x1B | DCL·10 | 0.01 A |

### 3.3 `0x0001` × 15 / 35 / 40 and `0x0010` × 19: presumably **Growatt lithium RS485**

- **× 15** (`0x2B80`): 15 registers, all 0 *(confirmed)*. Presumably the response to a detection request.
- **× 35** (`0x2BA6`) and **× 40** (`0x2DF0`, additionally 0x24–0x28 = 0) *(confirmed)*:

| Reg | Content | Unit |
|---|---|---|
| 0x01–0x12 | 0 | |
| 0x13 | status: bit 1..0 = 1 idle / 2 charging / 3 discharging; bit 3 always 1; bit 5 discharging possible; bit 6 charging possible | bits |
| 0x14 | 0 (fault, never populated) | |
| 0x15 | SOC | % |
| 0x16 | average pack voltage | 0.01 V |
| 0x17 | total current ·10, int16, **without clamping** | 0.01 A |
| 0x18 | highest cell temperature of all packs | °C |
| 0x19 | CCL·10, max. 32700 | 0.01 A |
| 0x1A | total remaining capacity ·10 (u16 overflow from 655 Ah) | 0.01 Ah |
| 0x1B | parameter 58 × configured pack count (overflow!) | 0.01 Ah |
| 0x1C | **0x1006** = firmware 16.06 | |
| 0x1D | 0 | |
| 0x1E | cycles (own pack) | |
| 0x1F | 0 | |
| 0x20 | 100 (SOH) | % |
| 0x21 | CVL·10 | 0.01 V |
| 0x22 | alarms (see below) | bits |
| 0x23 | DCL·10, max. 32700 | 0.01 A |

Reg 0x22:
- b0 highest cell > OVP + 30 mV
- b1 Ev2 b2|b3 (cell UV)
- b3 Ev2 b6|b7 (pack UV)
- b4 Ev5 b3…7 (discharge OC/short circuit)
- b5 Ev5 b1 (charge OCP)
- b6 Ev3 b4|5
- b7 Ev3 b6|7
- b8 Ev3 b0|1
- b9 Ev3 b2|3
- b10 Ev4 b4|5
- b11 Ev4 b0|1
- b12 Ev4 b2|3

There is no dedicated bit for cell or pack **over**voltage, and charge/discharge OC *alarms* (Ev5 b0/b2) are not reported.

- **`0x0010` × 19** (`0x301E`): same layout at the same addresses 0x10…0x22, but **without DCL**. The CCL (0x19) is calculated more simply:
  - at least one pack not charge-blocked (+0x06 < +0x01) and at least one pack able to charge (+0x03 ≠ 0) → parameter 50 (0.01 A) × packs able to charge, without halving, ramp or heating logic
  - at least one pack not charge-blocked (+0x06 < +0x01), but no pack counted as able to charge (+0x03 = 0) → **3000 (= 30.00 A)**; note that this reports 30 A although no pack qualifies
  - otherwise (all packs charge-blocked) 0
  - clamped to 32700

### 3.4 `0x0013` × 17 (since 04.06)

| Reg | Content | Unit |
|---|---|---|
| 0x13 | bit 5 discharging allowed, bit 6 charging allowed | bits |
| 0x14 | 0 | |
| 0x15 | SOC | % |
| 0x16 | voltage | 0.01 V |
| 0x17 | current ·10, int16 | 0.01 A |
| 0x18 | 0 | |
| 0x19 | CCL·10 | 0.01 A |
| 0x1A | remaining capacity ·10 | 0.01 Ah |
| 0x1B | full capacity ·10 | 0.01 Ah |
| 0x1C–0x20 | 0 | |
| 0x21 | CVL·10 | 0.01 V |
| 0x22 | 0 | |
| 0x23 | DCL·10 | 0.01 A |

### 3.5 `0x001F` × 9 (new in 06.13) and `0x0025` × 3

| Reg | Content | Unit |
|---|---|---|
| 0x1F–0x22 | cell temperature 1–4 | 0.1 °C signed |
| 0x23 | power stage / MOS temperature | 0.1 °C |
| 0x24 | ambient temperature | 0.1 °C |
| 0x25 | CVL | 0.1 V |
| 0x26 | CCL | 0.1 A |
| 0x27 | DCL | 0.1 A |

`0x0025` × 3 returns exactly 0x25–0x27. Together with 0x1F this forms a consistent map 0x1F–0x27, which contradicts 0x0013. It is therefore a different protocol. *(confirmed)*

### 3.6 Single registers `0x0033`, `0x0034`, `0x0070`(×1), `0x0071`–`0x0074` (since 06.11)

| Reg | Content | Unit |
|---|---|---|
| 0x33 | SOC | % |
| 0x34–0x35 | total full capacity ·100, u32 (high word first) | mAh |
| 0x70 | CVL | 0.1 V |
| 0x71 | DVL | 0.1 V |
| 0x72 | CCL | 0.1 A |
| 0x73 | DCL (positive) | 0.1 A |
| 0x74 | flags (low byte): **bit 7 charging enabled** (CCL ≠ 0), **bit 6 discharging enabled**, **bit 5 force charge I** (SOC ≤ 5 %), **bit 4 force charge II** (SOC ≤ 9 %) | bits |

The bit layout of 0x74 matches the **Pylontech CAN frame 0x35C** exactly, and 0x70–0x73 match the values from CAN 0x351. This is presumably a Modbus mapping of the Pylontech CAN values. *(layout confirmed, mapping probable)* Note the non-compliant byte count (section 1).

### 3.7 `0x0070` × 17

| Reg | Content |
|---|---|
| 0x70 | RS485 DIP address |
| 0x71–0x80 | cell voltages 1–16 **of the own pack** (mV), not aggregated |

### 3.8 `0x1000` × 21 (since 06.04)

| Reg | Content | Unit |
|---|---|---|
| 0x1000 | state: 0x20 off (system status bit 5), 0x01 discharging, 0x02 charging, 0x10 idle | enum |
| 0x1001 | b0 discharging allowed, b1 charging allowed | bits |
| 0x1002 | high byte = Ev5 (current), low byte = Ev2 (voltage), OR of all packs | bits |
| 0x1003 | low byte = Ev3; b8 Ev4 b0\|1, b9 Ev4 b2\|3, b10 Ev4 b5, b11 Ev4 b4, b12 Ev4 b6 (heating), b13 Ev6 b2, b14 Ev1 b4, **b15 pack communication error** | bits |
| 0x1004 | voltage | 0.1 V |
| 0x1005 | current (only while charging/discharging, otherwise 0), int16 | 0.1 A |
| 0x1006 | SOC | % |
| 0x1007 | SOH = 100 | % |
| 0x1008 / 0x1009 | max. cell temperature / pack no. | 0.1 °C / 1-based |
| 0x100A / 0x100B | min. cell temperature / pack no. | |
| 0x100C / 0x100D | max. cell voltage / pack no. | mV |
| 0x100E / 0x100F | min. cell voltage / pack no. | mV |
| 0x1010 | CVL | 0.1 V |
| 0x1011 | CCL | 0.1 A |
| 0x1012 | DCL | 0.1 A |
| 0x1013 | DVL | 0.1 V |
| 0x1014 | total full capacity | Ah |

### 3.9 `0x9000` × 26 (06.13; up to 06.12 × 21): BMS limits

Single-pack parameters (not × pack count):

| Reg | Content | Unit |
|---|---|---|
| 0x9000 | parameter 12 pack undervoltage alarm | 0.01 V |
| 0x9001 | parameter 16 pack UVP | 0.01 V |
| 0x9002, 0x9003 | parameter 14 pack OVP (twice) | 0.01 V |
| 0x9004 | parameter 50 charge OC warning (halved if `0x2F.7` = 0); clamped to CCL + 5 A if CCL ≥ 10 A | 0.01 A |
| 0x9005 | parameter 54 charge OCP (halved if applicable) | 0.01 A |
| 0x9006 | −parameter 52 discharge OC warning | 0.01 A |
| 0x9007 | −parameter 55 discharge OCP | 0.01 A |
| 0x9008 / 0x9009 | parameter 24 / 26 charge OTP / UTP | 0.01 °C |
| 0x900A / 0x900B | parameter 32 / 34 discharge OTP / UTP | 0.01 °C |
| 0x900C / 0x900D | = 0x9008 / 0x9009 | |
| 0x900E / 0x900F | parameter 42 / 44 ambient OTP / UTP | 0.01 °C |
| 0x9010 / 0x9011 | = 0x900E / 0x900F | |
| 0x9012 | parameter 48 power stage OTP | 0.01 °C |
| 0x9013 | = 0x900B (placeholder) | |
| 0x9014 | 10 (constant) | |
| 0x9015 | 0 (**new in 06.13**) | |
| 0x9016 | DVL (**new in 06.13**) | 0.1 V |
| 0x9017 | CVL (**new in 06.13**) | 0.1 V |
| 0x9018 | CCL (**new in 06.13**) | 0.1 A |
| 0x9019 | DCL (**new in 06.13**) | 0.1 A |

⚠ **06.13 only accepts count 26.** A master that reads 21 registers as before gets **exception 03**. *(confirmed)*

---

## 4. Input registers (FC 04)

**Valid combinations:** `0x0000`×21, `0x0015`×19, `0x0028`×20, `0x3100`×44 (up to 06.12 ×40). *(confirmed)*

The blocks `0x0000`, `0x0015` and `0x0028` contain **only data of the master pack itself**. `0x3100` mostly returns **system values across all packs**. *(confirmed)*

### 4.1 `0x0000` × 21 (since 06.11)

| Reg | Content | Unit |
|---|---|---|
| 0x00–0x0A | ASCII string 1 (`0x2000004C`, set via CID2 0xA3; **battery serial number**, *confirmed*), the first 22 characters, 2 per register | char |
| 0x0B–0x0E | cell temperature 1–4 | °C (integer, signed) |
| 0x0F | power stage / MOS temperature (the ambient temperature is **not** output) | °C |
| 0x10 | **0x0001**, constant | ? |
| 0x11–0x14 | 0 | |

### 4.2 `0x0015` × 19 (since 06.11): ⚠ shifted by one byte

The handler first writes **a single byte** (cell count), then 18 half-words and a trailing `00`. As a result, all 16-bit fields lie **one byte off the register boundaries**. This is a firmware bug or intended for a master that parses byte by byte. *(confirmed; unchanged since 06.11)*

| Byte offset | Content | Type / unit |
|---|---|---|
| 0 | cell count | u8 |
| 1–2 | cycles | u16 |
| 3–6 | port voltage | u32, mV |
| 7–8 | pack voltage | u16, mV |
| 9–12 | current | **int32, mA** |
| 13–16 | full capacity | u32, mAh |
| 17–20 | nominal capacity (parameter 58) | u32, mAh |
| 21–24 | remaining capacity | u32, mAh |
| 25 | SOC | u8, % |
| 26 | **Protection A**: b0 cell OVP, b1 cell UVP, b2 pack OVP, b3 pack UVP, b4 charge OCP, b5 discharge OCP/short circuit | bits |
| 27–28 | **Status B**: b1 charge MOS/current limiting on, b2 discharge MOS on, b8 charge overtemp. protection, b9 discharge overtemp. protection, b10 charge undertemp. protection, b11 discharge undertemp. protection, b12 power stage OTP, b13 ambient OTP, b14 ambient UTP | bits |
| 29–30 | **Fault C**: b2 temperature sensor fault | bits |
| 31–32 | 0 | |
| 33–34 | **Warnings D**: b0 charge high temp., b1 discharge high temp., b2 charge low temp., b3 discharge low temp., b4 ambient high, b5 ambient low, b6 power stage high, b8 cell high, b9 cell low, b10 pack high, b11 pack low, b12 charge OC alarm, b13 discharge OC alarm | bits |
| 35–36 | **0x3EC4**, constant | ? |
| 37 | 0 | |

### 4.3 `0x0028` × 20 (since 06.11)

| Reg | Content | Unit |
|---|---|---|
| 0x28–0x37 | cell voltage 1–16 (always 16, regardless of cell count) | mV |
| 0x38 / 0x39 | highest / lowest cell temperature | °C |
| 0x3A / 0x3B | highest / lowest cell voltage | mV |

### 4.4 `0x3100` × 44 (06.13; since 06.03 with 40 registers)

| Reg | Content | Unit |
|---|---|---|
| 0x3100 | cell count | |
| 0x3101 | system voltage (average) | 0.01 V |
| 0x3102 | system current, **from 06.13 clamped to ±32700** (up to 06.12: unsigned 16 bit · 10, overflow from ±327 A) | int16, 0.01 A |
| 0x3103 / 0x3104 | **from 06.13: power** U·\|I\|/10 as u32, **low word first** (up to 06.12: both = current·10) | 0.01 W: voltage (0.01 V) × \|current\| (0.1 A) / 10; 0 outside charging/discharging *(confirmed)* |
| 0x3105 | Σ full capacity | Ah |
| 0x3106 | system SOC | % |
| 0x3107 | **60**, constant | ? |
| 0x3108 / 0x3109 | highest / lowest cell temperature of all packs | **0.01 °C** |
| 0x310A / 0x310B | ambient temperature (master; twice) | 0.01 °C |
| 0x310C | power stage / MOS temperature (master) | 0.01 °C |
| 0x310D | cycles (master) | |
| 0x310E | balancing bits cells 1–16 (master) | bits |
| 0x310F | voltage status: 2 = cell > OVP + 30 mV, 1 = undervoltage (Ev2 & 0xCC), 0 = ok | enum |
| 0x3110 | current status: 2 = charge OC (Ev5 b0–1), 1 = discharge OC/short circuit (Ev5 b2–7), 0 = ok | enum |
| 0x3111 | b0 at least one pack may charge, b1 at least one pack may discharge | bits |
| 0x3112 | cell temperature status: 2 = overtemp. (Ev3 & 0x33), 1 = undertemp. (Ev3 & 0xCC) | enum |
| 0x3113 | 0 | |
| 0x3114 | ambient temperature status: 2 high, 1 low | enum |
| 0x3115 | power stage temperature: 2 = high | enum |
| 0x3116–0x3125 | 0 | |
| 0x3126 | **10**, constant | ? |
| 0x3127 | b15 **charging forbidden**, b14 **discharging forbidden**, b13 SOC ≤ 9 % (force charge), b12 = `F7.6` (never set); b3 = neither charging nor discharging, b1 = charging only, b0 = discharging only | bits |
| 0x3128 | 0 (new in 06.13) | |
| 0x3129 | system voltage (new in 06.13) | 0.1 V |
| 0x312A | system current (new in 06.13) | int16, 0.1 A |
| 0x312B | 0 (new in 06.13) | |

**Mapping *(assumption, fairly strong)*:** `0x3100` (FC04) together with `0x9000` (FC03) matches the **EPEver Modbus conventions** ("BMS-Link"):
- real-time data from 0x3100, battery parameters from 0x9000
- temperatures in 0.01 °C
- 32-bit power in 0.01 W with low word first

---

## 5. Modbus version history

| Block | 04.06 | 06.03 | 06.04 / 06.05 | 06.11 / 06.12 | 06.13 |
|---|---|---|---|---|---|
| Dispatcher | only **low byte** of the start address, FC03 only | full address | same | separate FC04 map | new jump structure, RAM +8 |
| 0x0000 × 12 (PACE) | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x0001 × 15 (zeros) | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x0001 × 35 / × 40 | – | – | **new** | ✔ | ✔ |
| 0x0010 × 19 | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x0013 × 17 | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x0025 × 3 | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x0070 × 17 (cells) | ✔ | ✔ | ✔ | ✔ | ✔ |
| 0x9000 | – | **new** (21) | 21 | 21 | **26** |
| 0x3100 (FC04) | – | **new** (40) | 40 | 40 | **44, current fix** |
| 0x1000 × 21 | – | – | **new** | ✔ | ✔ |
| 0x0000 × 28 | – | – | – | **new** | ✔ |
| 0x33 / 0x34 / 0x70(1) / 0x71–0x74 | – | – | – | **new** | ✔ |
| FC04 0x0000 / 0x0015 / 0x0028 | – | – | – | **new** | ✔ |
| 0x001F × 9 | – | – | – | – | **new** |

- Apart from the marked changes, the semantics of each block have been **unchanged** since its introduction. The differences are only literal pools, RAM shifts and the address of the version string. *(confirmed)*
- The 04.06 dispatch values come from `0x3734…0x3786`: `cmp #0x01/#0x10/#0x70/#0x00/#0x25/#0x13`. *(confirmed)*

## 6. Mapping to inverter protocols

| Block | Hypothesis | Confidence |
|---|---|---|
| 0x0000 × 12 | **PACE BMS Modbus V1.3** (many inverters: option "PACE"/"PYLON-485") | **confirmed** (identical to the PACE PDF) |
| 0x0001 × 15/35/40, 0x0010 × 19 | **Growatt** lithium RS485 (SPF/SPH); different models read different windows | assumption |
| 0x0070–0x0074, 0x33, 0x34 | Modbus mirror of the Pylontech CAN values (0x351/0x35C) for a master that polls single registers | assumption |
| 0x0013 × 17, 0x001F–0x0027 | Growatt/Luxpower/SRNE derivative | assumption, low certainty |
| 0x1000 × 21 | Voltronic/MUST/Sofar-style lithium 485 | assumption |
| 0x9000 × 26 and FC04 0x3100 | **EPEver** "BMS-Link" conventions (0x3100 real-time, 0x9000 battery parameters, 0.01 °C, power low word first) | assumption (fairly strong) |
| FC04 0x0000 / 0x0015 / 0x0028 | unknown (MUST/SRNE/Growatt variant or Seplos-specific) | assumption, weak |
| 0x0000 × 28 | unknown (identifiers 0x0641/0x3EC4) | – |


## Historical UART0 exception: OEM16.04.06 only

A separate FC03-like CRC read path exists on UART0 beside ASCII: `0x52FE → 0x1AEE → 0x19C6 → 0x1474 → 0x1A60 → UART0`. Native replay at local address 3: `030300010001D428` yields `030300020000E5E8`; the same request with bad CRC (`…D429`) stays silent. The response uses a **two-byte byte count**, not a standard Modbus reply. From the next available build, 16.06.03, both requests are silent and the UART0 path is absent. Register semantics remain incomplete: do not reuse the UART1 register map here. This is an offline code/emulator result, not a newly measured hardware/inverter test. [Baud and evidence details](../hardware/ports-and-topologies.md#8-application-baud-rates-and-the-historical-uart0-exception).
