# Startup, clock, timers and output write sites (06.13)

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Image: `CAN1101[V16.06.13_PN01_250607].ehex`; complete application SHA-256:
`5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95`.
All addresses below are application addresses for this exact OEM build.

Code-derived facts are separated from nominal clock calculations and unmeasured
hardware behavior. Register names use the pinned SWM181 reference manual V2.07
and both Synwit SDK snapshots in the [MCU source inventory](../../vendor/docs/mcu-synwit-swm181/SOURCES.md).
The REA/Ghidra and REA/Hopper evidence, source bindings and bounded offline
replays are retained in an unpublished research archive.

## 1. Reset path and RAM initialisation *(confirmed)*

```
Reset vector 0xC985 → 0xC984  ldr r0,[0xC9D8] (=0xC1); bx r0
0x00C0  ldr r0,=0x20001A98; mov sp,r0; bl 0xCBC0
0xCBC0  region-table loop, 2 records of 16 bytes at 0xCE3C, callback via blx
        0xCE3C: src 0xCE5C → 0x20000000, 0x108 bytes, copy  (handler 0xCBFE)
        0xCE4C: dst 0x20000108, 0x1990 bytes, zero fill   (handler 0xCC0E)
0xCBD8  bl 0xC8 → ldr r0,=0x60F1; bx r0 → 0x60F0
0x60F0  16 init calls (0x60F0–0x612E), cpsie i at 0x6148, endless loop 0x6152–0x62A4
```

`0x20000108 + 0x1990 = 0x20001A98`: the zero-initialized region ends at the
initial SP. This does not measure stack reservation, free SRAM or maximum stack
depth. The manual specifies 16 KB SRAM for the MCU family; the image's initial
SP is not the physical SRAM limit.

## 2. Interrupt vectors *(confirmed)*

| Vector | IRQ | Handler | IRQMUX source / role | Priority |
|---|---|---|---|---|
| 0x40 | 0 | 0x5FB6 | `0x67` CMP; calls 0x6C44, short-circuit discharge protection | 0 |
| 0x44 | 1 | 0x5FF0 | `0x54` TIMR0, nominal 5 ms | 1 |
| 0x48 | 2 | 0x60CC | `0x55` TIMR1, nominal 1 s | 1 |
| 0x4C | 3 | 0x0296 | `0x58` UART0 | 2 |
| 0x50 | 4 | 0x25A6 | `0x59` UART1 | 3 |
| 0x54 | 5 | 0x759C | `0x5A` UART2 | 3 |

The initialization callers are `0x5F70`, `0x5FC4`, `0x60A6`, `0x00D4`,
`0x23DC` and `0x7428`, respectively. They call `0xBF08`, which writes the
source to `0x45000000 + 4*IRQ`, sets the two-bit NVIC priority and enables the
IRQ. Lower priority numbers have higher urgency. The source codes agree in
both SDKs and manual p.49; this identifies the MCU source, not an electrical
connector pin.

IRQ6–31 and the implemented core exception handlers other than Reset point to
`b .` stubs in `0xC988–0xC9D4`. Reserved core slots `0x20`/`0x24` contain
metadata, not handler pointers. **SysTick's handler is a stub**; the inspected
periodic scheduler uses TIMR0/TIMR1 rather than a SysTick ISR.

## 3. System clock *(confirmed)*

`0x20000100` (SystemCoreClock) starts as **24,000,000** from the RW init data. The path
0x60F0 → 0xC932 → 0xC8FC → 0xC814 sets it to **48,000,000** at 0xC844/0xC846 when the
clock registers read back the value written to them. `0xC8FC` writes
`0x5000C000 = 3` (HRCCR: HRC enabled, 48 MHz selected), clears CLKSEL bit 1
(no divide-by-four) and sets bit 2 of `0x40000000` (HRC selected). All three
settings are needed for the 48 MHz derivation; bit 2 alone does not specify
the frequency. The sequence agrees with the clock tree (manual p.36) and SDK
`switchToRC48MHz`. It does not measure oscillator accuracy.

## 4. Timers *(confirmed)*

| | Timer 0 (TIMR0) | Timer 1 (TIMR1) |
|---|---|---|
| init function | 0x5FC4 (called from 0x612A) | 0x60A6 (called from 0x612E) |
| load register | `0x50007000` | `0x5000700C` |
| load value | SystemCoreClock / 200 = **240,000** (division via `__aeabi_uidiv` 0xC9DC, store at 0xB7A2) | SystemCoreClock = **48,000,000** |
| control | `0x50007008` | `0x50007014` |
| interrupt enable `0x50007070` | bit 0 | bit 1 |
| flag clear `0x50007074` | write 1 | write 2 (helper 0xB744, store 0xB766) |
| IRQ routing | `0x45000004` = source 0x54 → IRQ1 | `0x45000008` = source 0x55 → IRQ2 |
| nominal period | 5 ms | 1 s |

The two load values have an exact 200:1 ratio. The periods assume one count per 48 MHz
clock. The SDK writes LDVAL directly, without subtracting one; the manual's
timing diagram (p.87) includes the zero-count state. A one-clock increment is
about 21 ns at nominal 48 MHz. These are nominal intervals, not measured
wall-clock precision. Slow-loop counters and the fast 5 ms protection path
must be distinguished.

## 5. Scheduler flags and watchdog

| Address | Meaning | Confidence |
|---|---|---|
| `0x200000AA` | startup counter in the 5 ms ISR. At 400 calls (about 2 s), calls 0x496A, 0x5260, 0x549E, 0x55CE, 0x5D0C and 0x9A88 once. At 600 calls (about 3 s), calls 0x18C4 and sets A8 bit 1. The startup branch calls 0x8670. On subsequent ticks, A8 bit 1 gates 0x1914, 0x1ABA, 0x231C, 0x1F16, 0x6AB8, 0x725A and 0x85DE; 0x869E/0x8B54 also run in that post-startup branch. The common tail is 0x1472, 0x0176, 0x2476, then A9 bit 7. | confirmed |
| `0x20000B60` | u16 counter in the measurement sequence 0x1ABA, incremented at 0x1B72 | confirmed |
| `0x200000A8` | main-loop flags. **Bit 2** is set at 0x1C64 when 0x20000B60 exceeds 199 (nominally 1 s after the measurement sequencer starts). The main loop tests it at 0x6152, runs the slow block, clears bit 2 at 0x625A and sets bit 3, which gates communication block 0x6264–0x62A2. That block can run repeatedly between slow ticks; it is not itself limited to one call per second. Bit 2 is also cleared at 0x1910. | confirmed |
| `0x200000A9` | progress bitmask. In the 1 s ISR (0x60CC), the watchdog is fed (`0x50009010` = 0x55, at 0x60E8) **only if the byte is 0xFF**; the byte is cleared only after that successful feed. Bits accumulate since the last feed, not necessarily within one second. | confirmed |

The progress bits have concrete producers:

| A9 bit | Writer / checkpoint |
|---|---|
| 0 | `0x1C74`: end of the measurement round, only while backlog counter `0x20000B5F < 5` |
| 1–5 | `0x6172`, `0x61CA`, `0x61EC`, `0x620C`, `0x6228`: groups of slow-loop work completed |
| 6 | `0x62A2`: communication block completed |
| 7 | `0x60A2`: common tail of the 5 ms ISR completed |

These are grouped checkpoints, not one independent bit per function. If a required
checkpoint stops arriving, the guard can withhold further feeds; it does not
prove detection of every possible hung task or corrupted state.

**Watchdog setup:** before the `cpsie i` instruction at `0x6148`, `0x613E` calls
`0xBC34(0x50009000, SystemCoreClock << 3, 0)` and `0x6144` calls `0xBC6E`.
The first routine enables the WDT peripheral clock, stops the counter, clears IF,
writes `LOAD = (SystemCoreClock << 3) >> 1`, and sets CR.RSTEN (bit 1).
`0xBC6E` sets CR.EN (bit 0). At nominal 48 MHz the requested period is
384,000,000 clocks and the actual LOAD write is **192,000,000** (`0x0B71B000`).
The reset-mode SDK performs the same division by two. Manual p.97, figure 6-16,
instead depicts reset after a single LOAD countdown. The configuration and
reset intent are established, but an exact physical **4 s versus 8 s** reset
deadline is not settled by these conflicting sources. No elapsed reset time was
measured.

### Backlog, flag coalescing and a controlled lost update

`0x1C46–0x1C56` tests whether the previous slow tick is still pending and
increments `0x20000B5F`, saturating at 10; otherwise it clears the counter.
This detects backlog, not every lost flag update. A8 bit 2 is one pending-work
bit, not a tick counter: setting it again while it is already set coalesces
requests.

The main-loop read-modify-write at `0x624E–0x625A` is unprotected. It loads
A8, sets bit 3, clears bit 2 and stores the whole byte. A controlled native
instruction test demonstrates that this can overwrite an independent update
of **bit 1, the measurement-enable flag**, by the wake path:

| Step | Native action | A8 |
|---|---|---|
| 1 | Main cleanup loads the byte at `0x624E` | `0x04` |
| 2 | TIMR0 interrupts before the next instruction. With startup count 601, wake status `0x200000F1` bit 5 set and wake counter `0x200015DC` at 200, `0x8B54` calls measurement reinitialization `0x18C4`. Its store at `0x1910` clears bit 2. | `0x00` |
| 3 | Wake code stores measurement-enable bit 1 at `0x8BDA` and consumes the wake status. | `0x02` |
| 4 | Main cleanup resumes with its older loaded value and stores at `0x625A`. | `0x08` |

With cleanup completed before TIMR0, the same wake path instead leaves A8 at
`0x0A`, retaining measurement enable. A separate native control starts with
A8=`0x06` and measurement counter 199: the sequencer sets already-pending bit 2,
and cleanup leaves `0x0A`. This is coalescing, not the independent enable-bit
loss above.

The demonstrated instruction window uses explicit synthetic call states. A
bounded native sleep/wake replay confirms the wake-counter progression from a
specified synthetic sleep state. It does **not** establish that normal complete
execution reaches that aged wake counter while main cleanup is pending. Such
coincidence may require a delayed or stalled main loop. Full-system
reachability, physical occurrence and failure frequency remain unproven. The
mandatory test records this as inherited-behavior **characterization**; a pass
does not mean the firmware is race-free. EMU1101-EXT Light 1.5.4 / EMU1101-EXT Full 1.6.4 retain this OEM code.

If measurement enable is lost in this way, later TIMR0 ticks skip the seven
bit-1-gated measurement/fast/protection calls listed above. Possible effects
include stalled measurements, delayed voltage/temperature and charge/discharge
decisions, stale SOC/status/CAN values, and interruption of the gated fast
current and precharge processing. This is broader than a single delayed slow
tick. TIMR0's common tail, UART handlers and the independent comparator IRQ0
short-circuit path are not disabled by this flag alone. The result establishes
neither that every protection stops nor that every fast protection continues.
If required measurement/slow-loop progress bits stop arriving, watchdog feeds
can eventually be withheld; no physical reset deadline was measured.

The maintained native cases and their model limits are described in
[firmware validation](../../mod/docs/firmware/validation-methods-and-limits.md#deterministic-interrupt-and-uart-models).

### Atomic cleanup from EMU1101-EXT Light 1.5.5 / Full 1.6.5

These profiles replace the initial `0x624E` load/OR pair with a guarded BL to a
24-byte appendix. The branch at `0x6252` then skips the displaced native store
and returns to `0x625C`. The independent skip branch at `0x6254` is unchanged.
Source-derived CFG checks bind R5 to A8 and R6 to 8 and reject alternative entry
into the overwritten or displaced cleanup instructions.

The helper saves R2/return link, reads PRIMASK, masks interrupts, freshly reads
A8, sets bit 3, clears bit 2, stores the byte, restores the saved PRIMASK and
returns. An interrupt that updates wake measurement enable executes either
before the fresh read or after the protected store; the cleanup cannot overwrite
that update through its old loaded value. The incoming interrupt mask, R2–R12,
SP and native R0/R1/NZCV effects are retained. BL supplies a new return link;
incoming LR preservation is not claimed. The helper temporarily uses eight
stack bytes and no additional persistent RAM.

The introduced masked interval is six instructions (fresh load through mask
restore), with no calls inside it. Native tests sweep 13 instruction boundaries
under both incoming masks, 2,048 flag/mask/CV cases, and ordered/coalesced/new
slow-tick controls. Removing exclusion, moving the load outside it, forcing an
unconditional enable, or changing continuation/skip behavior fails the named
regression. These are controlled maskable-IRQ tests, not measured physical
latency or a complete firmware concurrency proof. The OEM negative control
continues to reproduce the original loss; physical occurrence in installations
remains unproven.

## 6. GPIO 0x50002000: all direct output writes *(confirmed)*

0x50002000 is the **GPIOB DATA** register and 0x50002004 is **DIR** (SWM181 header).
The MOSFET outputs are therefore pins **PB12 (charge)** and **PB13 (discharge)**. The
helper 0xB3A8 sets direction bits (store 0xB46A). Every write listed below is a word
read-modify-write with a single mask. The inventory covers direct stores found through
literal-pool loads and xrefs; stores through a computed base are not covered.

| Bit | Function | Clear | Set | Condition |
|---|---|---|---|---|
| 12 | charge MOSFET | 0x6348 (init 0x62DC), 0x6BB6 (0x6AB8), 0x70E2 | 0x70DA | in 0x6FFA, follows `0x200000B5` bit 1 in both directions |
| 13 | discharge MOSFET | 0x6314 (init), 0x6B00 (0x6AB8), 0x6C7E / 0x6CA6 (IRQ0 path 0x6C44), 0x7232, 0x7242 | 0x723A, 0x7304 | 0x723A only if B5 bit 0 = 1 and bit 4 = 0. 0x7304 is in 0x725A after the precharge stage |
| 15 | precharge | 0x62FA (init), 0x7316, 0x7328, 0x724C | 0x7278 | 0x725A sets bit 15 first (0x7278), then bit 13 (0x7304), then clears bit 15 (0x7316) |
| 10 | current limiter | 0x632E (init), 0x6BAE, 0x6C2E, 0x6C3E, 0x70F0 | 0x6C36 only | B5 bit 2 = 1 and `0x20000035` bit 7 = 0 |
| 11 | heater/relay, **active low** | 0x7414 | 0x6362 (init), 0x741C | inverted to B5 bit 3 |

Bits 10, 12 and 13 are set only when their enable bit in B5 (bits 2, 1, 0) is 1. Bits 10
and 13 can also be cleared while enabled, by interlocks in the 5 ms protection path
(0x6AB8) and in the IRQ0 path. In 0x6AB8, bit 12 is cleared together with bit 10 at 0x6BAE
and 0x6BB6. The gate is `0x2000002E` bit 6, B5 bit 1 set and bit 2 clear, and
`0x20000036` bit 6 clear. Afterwards `0x200000B5 = (B5 & 0xFD) | 4`, which hands charging
over to the current-limited path. This branch also requires signed current
`[0x20000C94] >= 1000` (`0x6B9E–0x6BA8`); omitting that comparison overstates
when the handover occurs.

`0x6FFA` tests voltage event byte `0x20000031 & 0x22`; `0x7184` tests
`0x20000031 & 0x88`. These are the cell/pack overvoltage and undervoltage
protection bits. The routines also contain current/state-dependent branches that
clear event bits or change the path. The masks alone are not an unconditional
MOSFET-off rule; see the full [function-switch and event logic](configuration-parameters.md).

## 7. UART initialization and nominal timing

The startup initializers call common UART driver `0xB970`. All three use 8N1,
RX FIFO threshold 6 and receive-timeout interrupts.

| UART | Initializer | Requested baud | BAUD divider at 48 MHz | Divider-derived baud | Timeout count / interval |
|---|---|---|---|---|---|
| UART0 | `0x00D4` | 19200 | `0x9B` (155) | 19230.77 | 10 / 5.2 ms |
| UART1 | `0x23DC` | 9600 | `0x137` (311) | 9615.38 | 100 / 104 ms |
| UART2 | `0x7428` | 9600 | `0x137` (311) | 9615.38 | 10 / 10.4 ms |

The driver uses integer division: `BAUD = floor(SystemCoreClock/16/requested)-1`.
The hardware formula is `SYSCLK/[16*(BAUD+1)]`; timeout is `count*10/baud` while
the RX FIFO is nonempty and no new byte arrives (manual pp.104–108). The UART1
requested-rate approximation is 104.1667 ms, distinct from the divider-derived
104 ms. Initial settings do not exclude later baud reconfiguration, and the
actual oscillator frequency was not measured.

The manual explicitly recommends leaving a byte in the FIFO so that the timeout
can delimit a frame (p.104). This matches the OEM receive pattern; it is not an
extra 3.5-character Modbus frame-gap detector. See [UART1 receive gap and buffer ownership](../protocols/uart1-receive-gap-and-buffer-ownership.md).

## 8. CAN initialization

`0x9A88`, called at startup tick 400, requests 100 kbit/s only when protocol
selector `0x20000024 == 7`; otherwise it requests 500 kbit/s. It passes the
24-byte CAN configuration to driver `0xC41E` and opens the controller with
`0xC4D0`. Mode is normal, the single 32-bit acceptance mask is all ones
(all comparisons are don't-care), and all four interrupt-enable bytes are zero.

At nominal 48 MHz, segment encodings BS1=3, BS2=2 and SJW=2 give 8 time quanta
per bit, a 62.5% sample point and single sampling:

| Protocol selection | BT0 | BT1 | Prescaler field BRP | Derived bitrate |
|---|---|---|---|---|
| 7 | `0x9D` | `0x23` | 29 | 100000 bit/s |
| other | `0x85` | `0x23` | 5 | 500000 bit/s |

The formula is `SYSCLK/[2*(BRP+1)*(1+(BS1+1)+(BS2+1))]` (manual p.183).
An open acceptance filter does not mean the application processes incoming
frames. See [CAN driver and transmit behavior](../protocols/can.md#2-can-driver-confirmed).

## 9. Reference and analysis limits

- The manual and SDK disagree on watchdog reset timing. The manual's reset-cause
  page also conflicts with its own register map and both SDK headers: p.45 prints
  RSTSR at `0x50000308` with WDT bit 1, whereas p.40 and the SDK map it to
  `0x40000308`, and the SDK defines WDT cause bit 3. No reset-cause decoder is
  established here.
- UART CFG is at offset `0x18` in both SDKs and the manual's detailed p.109,
  despite the p.105 summary printing `0x14`. The newer SDK names flow-control
  fields at `0x14`; the older one reserves that location. Preserve offset and
  source-version distinctions.
- Ghidra/Hopper pseudocode is not original C. In `0xBC34`, Ghidra's guessed
  signature loses the mode argument preserved in r2 across helper calls.
  Hopper's `0x9A88` pseudocode omits configuration stores visible in both
  providers' instructions. Register writes and calling conventions above are
  checked against instructions, rather than inferred from those signatures.
- The direct GPIO write inventory is bounded as stated in section 6. No complete
  indirect-store proof, physical pin tracing, hardware timing, stack high-water
  measurement or full-system boot test is claimed.
