# Seplos BMS 2.0/10E/V16 (EMU1101): binary display protocol (`0x55 … 0xAA`, UART2)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The original V16.04.06–V16.06.13 firmware implements a separate point-to-point binary interface. Confidence: **confirmed** = direct code evidence; **probable** = inferred data flow; **assumption** = hardware/device interpretation. Unless qualified, details below are confirmed for 06.13.

[Ports and topologies](../hardware/ports-and-topologies.md) maps UART0/UART1/UART2 and bus ownership. The [RS485 ASCII protocol](seplos-ascii.md), [Pylontech RS485](pylontech-rs485.md), [Modbus RTU](modbus-rtu.md), [CAN](can.md) and [intra-pack protocol](intra-pack.md) remain separate interfaces.

## 1. Physical layer

- UART2 (`0x50012000`), **9600 baud, 8N1**, **without RS485 direction control**, i.e. point-to-point (RS232/TTL). *(confirmed)*
- Active if function switch `0x2000002F` **bit 3** is set. *(confirmed)*
- *Assumption, well supported:* connection for an **LCD display or Bluetooth/Wi-Fi dongle** (RS232/"LCD" socket). The BMS continuously sends status frames, reports switching off/on, and the extended status message contains the active CAN protocol name and selection number; command 0x63 selects the protocol.
- For comparison: ASCII runs on UART0 (`0x50010000`) with RS485 direction pin, Modbus and Pylontech RS485 on UART1 (`0x50011000`).

## 2. Frame

```
Format A (addressed):   55 | ADR | CMD | LEN | DATA[LEN] | CRC_hi | CRC_lo | AA      (LEN+7 bytes)
Format B (no ADR):       55 | CMD | LEN | DATA[LEN] | CRC_hi | CRC_lo | AA
```

(Format A = addressed, LEN+7 bytes; format B = without ADR.)

- **Format A** applies to all responses. Format B applies to the spontaneous frames 0x46/0xA2/0xA3 when function switch `0x2F` **bit 4 = 0**. If bit 4 = 1, these are also sent in format A.
- ADR when sending = own DIP address. On reception ADR is **not** checked.
- **CRC = CRC-16/XMODEM** (polynomial 0x1021, init 0, not reflected, no XorOut), big-endian, over ADR … last data byte (format B: CMD … data). Check value "123456789" → `0x31C3`. Example: `55 01 AA 00 C5 85 AA`.
- **Errors:** The CMD byte of the response is replaced by the error code, LEN = 0:
  - **0x81** unknown command
  - **0x83** wrong marker
  - **0x87** length
  - **0x88** CRC
  - **0xE2** invalid value / check failed

## 3. Commands

| CMD | Direction | Data | Response / effect | Since |
|---|---|---|---|---|
| 0x47 | device → BMS | – | LEN 168: `3C` + 60×u16, `1B` + 27 bytes, `08` + 8 switches, 10 bytes name | 04.06 |
| 0xA1 | device → BMS | 158 bytes: `3C`+120, `1B`+27, `08`+8 (without name) | write parameters as [ASCII 0xA1](seplos-ascii.md#512-cid2-0xa1-write-parameters); OK → `A1`, LEN 0 | 04.06 |
| 0x63 | device → BMS | protocol 1…20 | set CAN protocol (as [ASCII 0xA6](seplos-ascii.md#514-cid2-0xa6-set-can-inverter-protocol)). **From 06.11** special case 7/MUST with CAN re-initialisation | 04.06 |
| 0x64 | device → BMS | 1…20 | **Stub**: range check only, no effect. **Up to 06.12 bug: acknowledged with CMD 0x63, from 06.13 correctly 0x64** | 04.06 |
| 0xAA | device → BMS | 6 bytes | tunnel, state 2 (no binary response) | **06.13** |
| 0xAB | device → BMS | – | tunnel acknowledgement, state 4 | **06.13** |
| 0x46 | BMS → device | spontaneous | status frame (see below) | 04.06 |
| 0xA2 | BMS → device | spontaneous | once on **switching off** (system status bit 5: 0 → 1) | 04.06 |
| 0xA3 | BMS → device | spontaneous | once on **switching back on** (bit 5: 1 → 0) | 04.06 |
| 0xAA / 0xAB | BMS → device | spontaneous | [tunnel requests](seplos-ascii.md#515-cid2-0xaa--0xab-from-0613-tunnel-to-the-binary-port) | **06.13** |

**Sequence in the main loop's 1-s block** (`0x8288`, called at `0x6202`; not on every fast loop pass): If a received frame is pending, it is processed. Otherwise the BMS sends exactly one spontaneous frame, with priority **A2 > A3 > tunnel > 0x46**. Edge detection uses a shadow byte: `0x200000E8` up to 06.12, `0x200000E9` from 06.13.

Parameter validation, failure ordering, side effects and persistence are defined by [ASCII 0xA1](seplos-ascii.md#512-cid2-0xa1-write-parameters). Binary 0xA1 omits the ten-byte name, so it does not carry a replacement name. Accepted CAN indices, fallback behavior for 8…20, and the stored-7 update hazard are defined by [ASCII 0xA6](seplos-ascii.md#514-cid2-0xa6-set-can-inverter-protocol). Binary CMD values are not ASCII CID2 values: binary 0xA2/0xA3 announce off/on, while ASCII 0xA2/0xA3 read/write a serial string.

**Status frame 0x46:**

- **Short** (`0x761E`, format B, switch `0x2F` bit 4 = 0): `N`, N × cell mV, `06`, 4 cell temperatures, ambient, power section (0.1 K), current (0 when idle), pack voltage, remaining capacity, `03`, full capacity, cycles, port voltage, system status & 0x33, on-off & 0x0F, `06`, event 1–5, event 6 & 0x7F, RS485 address, slave count. **No SOC.** *(confirmed)*
- **Extended** (`0x77DC`, format A, bit 4 = 1), order *(confirmed)*; multi-byte values big-endian:
  1. `N`, N × cell mV
  2. `06`, 4 cell temperatures, ambient, power section (0.1 K)
  3. Current (0.01 A, 0 outside charging/discharging), pack voltage (0.01 V), remaining capacity (0.01 Ah)
  4. `06`, full capacity, **SOC** (0.1 %), rated capacity (P58), cycles, `03 E8` (SOH 100.0 %), port voltage
  5. Byte alarms: N × cell, 4 × cell temperature, ambient, power section, current, voltage
  6. System status & 0x33, on-off & 0x0F
  7. `08`, event 1–5, event 6 & 0x7F, event 7 & 0x30, event 8 & 0x3F
  8. Balancing mask (2 bytes), `00 00`
  9. **Name of the active CAN protocol** (20 bytes) – only this one, on every pack
  10. Device name (10 bytes), FW version `10 06`, CAN protocol number (u8), byte `0x200000A6`, constant `0x46`
  11. **Only master with slaves:** system block (max./min. cell voltage and temperature, total current, average voltage, Σ remaining and full capacity, system SOC, 1000, average port voltage, online bitmask of the packs, OR of the packs’ on-off state masked to bits 0–3, OR of the alarm-event fields with their output masks). Otherwise 46 zero bytes; the length stays the same. The aggregate on-off byte reports gate/current-limiter/heater state; it is not a CCL/DCL-derived enable mask (`0x7E06–0x7E14`, aggregate `0x2000161E+6`).

## 4. Own pack only: no parameter proxy in a multi-pack bank

Forum posts say the Bluetooth display or its app can change slave settings while packs run as master and slaves (DIP 5–8 set). The seven original images (04.06 … 06.13) have no master-to-slave parameter proxy; a separate local display on each pack can still change that pack:

- **Binary port (UART2):** the dispatcher `0x8288` knows only 0x47, 0xA1, 0x63, 0x64 (06.13 also 0xAA/0xAB). 0x47 reads the pack's **own** parameter block `0x20001300` and switches `0x20000028…2F` (`0x7EA2–0x7F80`); 0xA1 writes exactly these (`0x7F82–0x80A4`, stored via `0x4890`). The ADR of a received frame is neither checked nor used as a target (`0x8140–0x820A`): a display on the master changes the **master** whatever ADR it sends.
- **Also while polling:** `0x8288` runs in the 1-s block at `0x6202`, **before** the master/slave branch `0x6264–0x628A`, so the master stays configurable through its display while it polls the slaves.
- **CAN socket (UART1):** only 0x42/0x44/0x4F/0x51/0x60–0x63 (`0x2AF2:0x2B0E–0x2B7A`); a 0x47 ends in RTN 04 (`0x2B3E`), a 0xA1 already exceeds the 230-character receive limit (`0x24E4–0x24F8`). A host there can query slaves directly only if their UART1 pairs are actually wired together and no other host/inverter independently polls UART1; each slave listens locally, with no forwarding by the master.
- **Polling caches no parameters:** the master asks only 0x5A (`0x13F6:0x1454–0x145E`) and keeps 30 status bytes per pack (`0x1384`); the slaves' 0x47/0xA1 never reach it.
- **No window for another host on RS485-1/2:** after the last slave the master pauses until the next second (bit 2, set at `0x14AE:0x1568`, cleared at `0x99BA:0x9A34`). The pause has no fixed length or position and there is no arbitration; a 0xA1 (~358 characters, ~186 ms at 19200 Bd) can collide with the next 0x5A request. There is no supported shared-host window; collision risk is an inference from this timing.

- **All cells of all packs:** of its slaves the master knows only max/min (30 bytes from 0x5A, table `0x20000524`), not the 16 single voltages. Every pack delivers its own cells: 0x42 at its DIP address on the RS485 pair of the CAN socket (UART1), also while the master polls. Only the master transmits CAN: mostly aggregate values, with some own/fixed fields (e.g. cycle count).
- **One display per pack works in a bank:** `0x8288` runs on every pack before the master/slave branch, slaves included. With its own device on each pack's binary port, every pack (master included) can be read and written through its device without changing the multi-pack mode; the binary port is a separate point-to-point line and does not disturb the pack bus. Preconditions: function switch `0x2F` bit 3 on (factory default on), and the device speaks `55 … AA` (*assumption* for the Seplos display, not visible in the code). The same holds for a USB adapter on the RS232/TTL socket; its level (RS232 or TTL) cannot be read from the firmware and must be measured before connecting.

Consequence: over UART0, access slave parameters directly only with the master’s polling stopped (effective slave count 0, or a supported MAINT maintenance marker). With automatic addressing enabled, DIP 5–8 = 0 alone does not guarantee that polling stops; see [intra-pack bus availability](intra-pack.md#taking-the-master-off-the-bus-during-operation-dip-58-to-0). *Assumption* about the forum reports: the master was changed, or other hardware was used (e.g. EMU1203 V16, for which Seplos's app guide describes a pack selection “Single”; a BLE read script uses frames `7E 10 00 46 61 …`, not `55 … AA`), or the link cable was unplugged.

## 5. Firmware version differences

| Item | 04.06 | 06.03–06.05 | 06.11 / 06.12 | 06.13 |
|---|---|---|---|---|
| 0x47, 0xA1, 0x46, 0xA2, 0xA3 | present | unchanged semantics | unchanged semantics | unchanged semantics |
| 0x63 CAN selection | no MUST special case | same | special case 7/MUST; save only on change | same |
| 0xAA / 0xAB tunnel | absent | absent | absent | added |
| 0x64 acknowledgement | incorrectly CMD 0x63 | same | same | corrected to CMD 0x64 |
| Off/on edge shadow | `0x200000E8` | same | same | moved to `0x200000E9`; E8 becomes tunnel state |

Other handlers are semantically unchanged since 04.06 apart from relocated RAM/code addresses. None of the seven OEM images implements a master-to-slave parameter proxy.
