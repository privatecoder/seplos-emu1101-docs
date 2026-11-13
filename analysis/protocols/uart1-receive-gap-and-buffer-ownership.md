# UART1 receive gap and buffer ownership

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

UART1 uses the RS485 pair in the CAN socket at 9600 baud. Code addresses below refer to OEM 16.06.13. Offline receive tests use synthetic frames and addresses; they do not establish physical timing or current-image hardware behavior.

EMU1101-EXT Light 1.5.3 and later, and Full 1.6.3 and later, protect a completed receive buffer against overwriting. This is a release-baseline behavior of the [maintained payload](../../mod/firmware/patcher/seplos/payload.s), independent of the permission bits, which use 1=enabled in every versioned release. Two frames can still merge without a receive timeout in both OEM and EMU1101-EXT. Protecting the buffer can discard a new query while a completed frame occupies it.

The archived 228-case receive study has exact image bindings and dependencies in `local/research/ext-consistency-audit-20261113/topic-analysis.md`. Its results characterize the named archived images; they do not count as validation of current releases. Current image checks are described in [firmware validation](../../mod/docs/firmware/validation-methods-and-limits.md).

## 1. What the firmware configures

OEM 16.06.13 initializes UART1 at `0x23DC`. Instructions `0x2438–0x243C` request
9600 baud; `0x2452–0x2454` set TimeoutTime to 100; `0xB9FC–0xBA04` write it to
CTRL[31:24]. Executed initialization returns configuration
`80250000000000060100006401`, CTRL `64006210`: timeout 100, timeout interrupt
enabled, RX FIFO threshold 6. The archived comparison found identical initialization and UART-driver code in its pinned images; those bindings are retained in the local topic note. The 24 MHz system clock used in this probe is an
emulator fixture, **not a measurement of the BMS clock**; the requested 9600
baud comes from the actual instructions.

The [pinned manufacturer SDK and SWM181 manual](../../vendor/docs/mcu-synwit-swm181/SOURCES.md)
define TimeoutTime/(Baudrate/10) seconds with a nonempty RX FIFO and no new
reception (manual pp.104–108). Page 104 explicitly recommends leaving one byte
in the FIFO to guarantee a receive timeout that can delimit frames. Using the
requested baud rate, nominally:

```text
100 × 10 / 9600 seconds = 104.1667 ms
```

These are 100 character times at 8N1, **not 100 individual bit times**. CR does
not end a frame in the receive ISR; the parser checks CR later.

The OEM clock setup selects nominal 48 MHz. The actual integer divider written
by `0xB970` is 311, giving `48 MHz/[16*(311+1)] = 9615.38` baud and a
divider-derived timeout of **104 ms**. These calculated values refine the
requested-rate approximation above; neither is a physical timing measurement.
The [startup and UART register derivation](../firmware/startup-clock-timers.md#7-uart-initialization-and-nominal-timing)
is bound to the exact OEM .13 application and actual-instruction replay.

## 2. Case A: no receive timeout between two frames

OEM RX at `0x24A8` moves bytes from a FIFO containing multiple bytes into the
buffer, leaving the last byte until timeout. With the actual FIFO threshold 6,
several tail bytes can initially remain without a timeout. Only the timeout flag
(status bit 21, `0x2506–0x252E`) permits completion, state 4. EMU1101-EXT `hook_rx`
behaves accordingly. State 1 appends additional bytes, including a fresh `~` or
`55` start; it does not resynchronize at the new start.

Schematic example for a listening pack: a foreign 168-byte `42` response followed
by its own 20-byte `42` query without a timeout creates one 188-byte buffer with
the foreign address first. Its own query is never parsed separately and receives
no answer. The archived study reproduces this in OEM and its pinned custom images; the maintained receive state machine retains this limitation. A timeout and
subsequent processing between the frames allow the query to be answered. Mixed
ASCII/EMU1101-EXT binary frames are affected too.

**EMU1101-EXT does not fix case A.** This is the established reason why 100 ms of
actual bus silence can be too short.

## 3. Case B: timeout occurred, completed frame not yet processed

| Receive sequence | OEM 16.06.13 | EMU1101-EXT Light 1.5.3+ / Full 1.6.3+ state machine |
|---|---|---|
| Completed own query, then foreign frame before main-loop processing | New start can overwrite own query; own answer is lost | Own completed query remains available and is answered |
| Completed foreign frame, then own query before main-loop processing | Own query can replace foreign frame and be answered | Own bytes are discarded until the foreign frame is processed |

Outside state 1, the OEM byte path accepts new start characters even in state 4.
EMU1101-EXT accepts bytes only in states 0/1, preserving the completed or processing
buffer. The difference is visible at `.Lrx_byte` in
[`mod/firmware/patcher/seplos/payload.s`](../../mod/firmware/patcher/seplos/payload.s).

**This fixes an OEM buffer-overwrite bug.** Its tradeoff is that EMU1101-EXT does not queue a second query while the only buffer is occupied. OEM success in the reverse test therefore does not establish correct pipelining. Mandatory tests independently check ready-buffer ownership and IRQ activity during actual parameter processing ([`seplos/selftest.py`](../../mod/firmware/patcher/seplos/selftest.py)). The [firmware changelog](../../mod/firmware/CHANGELOG.md) records development history separately from versioned release availability.

UART1 is dispatched at `0x628E–0x6298`, at the end of the main loop and outside
the one-second work block. There is no fixed additional one-second receive lock.
No hard maximum main-loop latency was established. The archived counterexample
intentionally delays main-loop processing: it proves a state property, not how
often it occurs in operation.

## 4. Runtime implications and host recommendation

**Established in the emulator:** query loss without the required frame separation,
and both different reactions of a ready buffer. Subsequent correctly separated
queries succeed without restarting; this does not create a permanently stuck
receive lock. The probe shows no effect on SOC or MOSFETs.

**Plausible effects not yet measured on the bus:** missing answers/timeouts,
alternating responsive packs and OEM/EMU1101-EXT differences under tight timing. A host
timeout after a lost query may create enough silence for the next pack to answer.
Without a wire trace, the contribution of either mechanism to a particular
gateway/installation observation remains open.

Release-specific validation must identify the exact application SHA and build report. Archived counterexamples and maintained-source inspection are separate evidence; neither substitutes for mandatory checks on the selected image.

Use **200 ms after receiving a complete answer before the next UART1 query** as
a practical initial margin, consistently across ASCII, binary service, Modbus and
raw `64/03`/maintenance paths. This exceeds the nominal 104.17 ms receive timeout;
it cannot guarantee service under an arbitrarily long main-loop stall. Never
insert a timeout-length gap inside one frame. Allow only one host at a time.

A 100 ms PC-side pause does not necessarily mean 100 ms of wire silence: gateway,
TCP/USB, scheduling and extra application steps can extend the actual gap. It
would be incorrect to claim every application query must therefore fail. The
OpenBMS transport revision examined defines `timing::GAP=100ms` and sleeps after
receiving an ASCII response. Raw/maintenance paths need separate consideration;
this analysis did not modify the application.

A pack after its **own** fully transmitted response is a different case: the OEM
sender sets state 2, then resets state/direction to receive after TX completes
(`0x25B2`, `0x2554–0x257E`). Without hearing its own echo, `42`→`44` to the same
pack succeeds in the four pinned archived images without an additional simulated pause. A
missing own `44` response is therefore not explained by case A alone. Intervening
foreign bytes or actually received echo need separate evidence; physical echo
was not established here.

## 5. Counterexample evidence and replay limits

The archived final report (`UART1-Empfangspause-2026-10-21-final.json`) contains 228 passed cases. It executes actual SHA-bound Thumb routines for initialization, RX IRQ, parser, dispatcher and sender, modeling the configured FIFO threshold and timeout interrupt. Fixtures use local addresses 0 and 3, foreign synthetic response address 2, gaps of 0/100/105/120/150/200 ms, delayed main-loop evaluation, release after own transmission, both ownership directions, recovery, and mixed ASCII/binary traffic. This is neither cycle-accurate CPU/RX wire simulation nor a hardware measurement.

The exact compared image identities, source location, dependency arrangement and historical build-report inputs are retained in `local/research/ext-consistency-audit-20261113/topic-analysis.md`. The archived probe and its private fixtures are absent from a fresh public checkout. Invoking one moved script does not reconstruct that workspace; it is not a maintained public tool. Current native checks are part of the [patcher validation workflow](../../mod/docs/firmware/build-and-validation.md).
