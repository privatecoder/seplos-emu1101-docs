# Seplos 10E / EMU1101: response fields that carry a current limit or enable

Overview of every field in which the firmware (16.06.13) reports a **charge current limit (CCL)**, **discharge current limit (DCL)** or an **enable/request bit** (charge/discharge enable, force charge) to the outside. Collected from [can.md](can.md), [modbus-rtu.md](modbus-rtu.md), [pylontech-rs485.md](pylontech-rs485.md) and the code; addresses for 16.06.13.

Purpose of this list: a complete, field-by-field index of these fields rather than a blanket register mask. Useful for example to merge the same values from different protocols in a monitor.

## Source of most values

CCL and DCL live in the **system aggregate** `0x2000164C` (`0x98A8`, `0x99BA`): CCL at `+0x24` (= `0x20001670`), DCL at `+0x28` (= `0x20001674`), each u16 in 0.1 A. The enable/force bits derive from `0x200000F7` and the aggregate counters (see [modbus-rtu.md §2](modbus-rtu.md#2-data-source-system-aggregate-0x2000164c)). **Exceptions** that do *not* come straight from the aggregate are marked below — they are computed separately in the builder. Zeroing only the aggregate does not cover those exceptions.

Base rules *(confirmed)*:
- **CCL** = parameter 50 (charge OC warning), halved or −10 A depending on BitGroup7 bit 7, × charge-capable packs without a charge warning; **10 A total only while not all packs are charge-locked** (otherwise 0; `0x98C8`–`0x98F8`); 0 if a cell > parameter 4 + 30 mV; ramp ± (packs online × 1 A) per cycle.
- **DCL** = |parameter 52| (−10 A above 20 A) × discharge-capable packs without a discharge warning; 0 when all warn; no ramp.

## CAN (depends on protocol `0x20000024`)

| Protocol | Frame | Field | Content |
|---|---|---|---|
| 1 Deye/Pylontech (`0xA826`) | `0x351` | byte 2–3 / 4–5 | CCL / DCL, u16 0.1 A |
| 1 | `0x35C` byte 0 | bit 7 / 6 / 5 / 4 | charge enable (CCL ≠ 0) / discharge enable / force charge I (SOC ≤ 5 %) / force charge II (SOC ≤ 9 %) |
| 2 Growatt (`0xABAA`, BE) | `0x311` | CVL, CCL, DCL; byte 7 | CCL/DCL 0.1 A; status bits \|0x20 discharge, \|0x40 charge allowed |
| 2 | `0x319` | flags | like `0x35C` |
| 3 Victron / 4 SMA (`0xA9BA`) | `0x351` | byte 2–3 / 4–5 | CCL / DCL |
| 5 GINLONG (`0xA90C`) | `0x351` | byte 2–3 / 4–5 | CCL / DCL |
| 5 | `0x35C` byte 0 | bit 7 / 6 / 5 / 4 | **bit 7 charge enable = highest cell ≤ OVP + 30 mV, not CCL ≠ 0** *(exception)*; bits 6/5/4 like protocol 1 |
| 6 Studer (`0xAC74`, BE) | `0x0C0` | CCL, **CCL + 10 A**, CVL | *(exception: CCL + 10 A)* |
| 6 | `0x0C1` | DCL, **DCL + 10 A**, DVL | *(exception: DCL + 10 A)* |
| 6 Studer | `0x0A0` byte 0 | **bit 0 charge forbidden, bit 1 discharge forbidden** (inverted from `0x200000F7` bits 2/3), **bit 2 force charge** (F7.5); **bit 4** from F7.6, which the examined app paths do not set (`0x96CE`–`0x9864`), so **0** in normal operation; `0xA636`–`0xA664` | forbid/force bits |
| 7 MUST (`0xAE4A`, 29-bit) | `0x00030100` | CVL, CCL, DVL, DCL | different order than `0x351` |
| 7 MUST | `0x00030200` | **byte 4 = 1 charge forbidden, byte 6 = 1 discharge forbidden** | forbid bits |

So the GINLONG charge enable and the Studer `+10 A` values do **not** simply follow the aggregate CCL/DCL. *(confirmed)*

## Pylontech ASCII on UART1 (master only, ADR 0x12/0x02)

| Command | Field | Content |
|---|---|---|
| `0x63` (`0x2882`) | byte 4–5 | CCL, u16 0.1 A |
| `0x63` | byte 6–7 | DCL, **s16 negative**, 0.1 A |
| `0x63` | byte 8 | 0x80 charge enable (cell ≤ OVP + 30 mV, **not** CCL ≠ 0) *(exception)*, 0x40 discharge enable, 0x20 SOC ≤ 9 %, 0x10 full charge (never set) |

Note *(confirmed)*: "charge enable" can be 1 even though CCL = 0; the force-charge bits are shifted by one bit relative to `0x35C` (SOC ≤ 5 % is not reported at all).

## Modbus RTU (master only, FC 03/04)

| Register (map) | Field | Content |
|---|---|---|
| FC03 `0x0000`×12 PACE (`0x32B8`) | `0x0B` | **bit 10 at least one pack can charge, bit 11 can discharge** (`0x341C`–`0x3440`); no CCL/DCL |
| FC03 `0x0000`×28 (`0x3BCC`) | `0x19`/`0x1A` / `0x1B` | CCL·10 / DCL·10, **0.01 A** (aggregate ×10, `0x3D1A`–`0x3D68`) |
| FC03 `0x0001`×35/40 (`0x2BA6`/`0x2DF0`) | `0x19` / `0x23` | CCL·10 / DCL·10, 0.01 A, max 32700 |
| FC03 `0x0013`×17 (`0x357E`) | `0x19` / `0x23` | CCL·10 / DCL·10 (`0x35CC`, `0x3600`) |
| FC03 `0x001F`×9 / `0x0025`×3 (`0x34BC` / `0x352E`) | `0x26` / `0x27` | CCL / DCL (`0x34E2`–`0x34EE`, `0x3530`–`0x353E`) |
| FC03 `0x0010`×19 (`0x301E`) | `0x19` | **CCL computed more simply, no DCL** *(exception)* |
| FC03 single registers (since 06.11) | `0x0072` / `0x0073` | CCL / DCL (positive), 0.1 A |
| FC03 single registers | `0x0074` low byte | **bit 7 charge enabled (CCL ≠ 0), bit 6 discharge enabled, bit 5 force charge I, bit 4 force charge II** |
| FC03 `0x1000` map | `0x1011` / `0x1012` | CCL / DCL, 0.1 A |
| FC03 `0x1000` map | `0x1001` | **bit 0 discharge allowed, bit 1 charge allowed** |
| FC03 `0x0000`×28 | `0x13` | **status:** `\|0x40` (bit 6) discharge allowed, `\|0x80` (bit 7) charge allowed |
| FC03 `0x0001`×35/40, `0x0010`×19, `0x0013`×17 | `0x13` | **status:** bit 5 discharge allowed, bit 6 charge allowed |
| FC04 `0x3100`×44 (`0x364A`) | `0x3111` | **bit 0 at least one pack may charge, bit 1 may discharge** (`0x374E`–`0x376A`) |
| FC04 `0x3100`×44 | `0x3127` | **bit 15 charge forbidden, bit 14 discharge forbidden, bit 13 force charge (SOC ≤ 9 %)**, bit 3 neither charge nor discharge (`0x3818`–`0x382A`), bit 1 charge only, bit 0 discharge only |
| FC03 `0x9000`×26 (`0x3898`, loop `0x39F2`) | `0x9018` / `0x9019` | CCL / DCL (**new 06.13**), 0.1 A |
| FC03 `0x9000`×26 | `0x9004` | **own current threshold from parameter 50** (halved if applicable), cap CCL + 5 A only from CCL ≥ 10 A (`0x3924`–`0x3944`); **can be > 0 even when system CCL = 0** *(not the system CCL)*, 0.01 A |

The CCL/DCL registers of most maps mirror the aggregate (`0x20001670`/`0x20001674`). Exceptions: `0x0010`×19 computes its own simpler CCL without DCL; `0x9004` is **not** a CCL mirror but a separate threshold from parameter 50 (can be positive even when the system CCL is 0). *(confirmed)*

## Summary: fields that carry a current limit / enable

- **CCL:** CAN `0x351` B2–3 (prot. 1/3/4/5), `0x311` (prot. 2), `0x0C0` (prot. 6, plus CCL+10 A), `0x00030100` (prot. 7); Pylontech `0x63` B4–5; Modbus `0x0000`×28 `0x19`/`0x1A`, `0x0001`×35/40 `0x19`, `0x0013` `0x19`, `0x001F`/`0x0025` `0x26`, `0x1011`, `0x0072`, `0x9018`, simpler `0x0010×19` `0x19`; **not a CCL mirror:** `0x9004` (own threshold).
- **DCL:** CAN `0x351` B4–5, `0x311`, `0x0C1` (plus DCL+10 A), `0x00030100`; Pylontech `0x63` B6–7; Modbus `0x0000`×28 `0x1B`, `0x0001`×35/40 `0x23`, `0x0013` `0x23`, `0x001F`/`0x0025` `0x27`, `0x1012`, `0x0073`, `0x9019`.
- **Enable/request:** CAN `0x35C` B0 bits 3–7 (prot. 1/5), `0x319` (prot. 2), **Studer `0x0A0` B0 (forbid 0/1, force 2/4)**, **MUST `0x00030200` B4/B6 (forbid)**; Pylontech `0x63` B8; Modbus PACE `0x0B` bits 10/11, `0x0074` bits 4–7, **`0x13`** (×28: bits 6/7; `0x0001`/`0x0010`/`0x0013`: bits 5/6), **`0x1001` bits 0/1**, **`0x3111` bits 0/1**, **`0x3127` bits 15/14/13/3**. (Victron/SMA `0x35A` is a **warning frame** (`0x9E0A`–`0x9F56`), not an enable field.)

**Exceptions that do not follow the aggregate CCL/DCL:** GINLONG/Pylontech charge enable (cell voltage instead of CCL), Studer `+10 A`, Modbus `0x0010×19` (own CCL); `0x9004` is not a CCL mirror at all but a separate threshold. *(confirmed)*
