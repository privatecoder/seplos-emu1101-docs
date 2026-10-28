# UART1 receive gap and buffer ownership

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Verified 2026-10-21. UART1 uses the RS485 pair in the CAN socket at
9600 baud. Images checked: OEM16.06.13, selected MAINT1.5 Power/RTC, original
MAINT1.6 and MAINT1.6 CUTOFF_POSITIVE. Offline only; no firmware changes or
device access. The bit-3/bit-4 polarity does not affect this receive sequence.
Synthetic probe frames and addresses only.

**Result:** MAINT protects a completed receive buffer against overwriting,
fixing an OEM weakness. However, two frames can still merge without a receive
timeout in both OEM and MAINT. These are separate mechanisms; protecting the
buffer can discard a new query in the second case below.

## 1. What the firmware configures

OEM16.06.13 initializes UART1 at `0x23DC`. Instructions `0x2438–0x243C` request
9600 baud; `0x2452–0x2454` set TimeoutTime to 100; `0xB9FC–0xBA04` write it to
CTRL[31:24]. Executed initialization returns configuration
`80250000000000060100006401`, CTRL `64006210`: timeout 100, timeout interrupt
enabled, RX FIFO threshold 6. Initialization and UART-driver code are identical
in all four checked images. The 24 MHz system clock used in this probe is an
emulator fixture, **not a measurement of the BMS clock**; the requested 9600
baud comes from the actual instructions.

The [manufacturer SDK header](https://github.com/Synwit-Co-Ltd/SWM181_Lib/blob/main/SWM181_StdPeriph_Driver/CSL/SWM181_StdPeriph_Driver/SWM181_uart.h)
defines TimeoutTime/(Baudrate/10) seconds with a nonempty RX FIFO and no new
reception. Nominally:

```text
100 × 10 / 9600 seconds = 104.1667 ms
```

These are 100 character times at 8N1, **not 100 individual bit times**. CR does
not end a frame in the receive ISR; the parser checks CR later.

## 2. Case A: no receive timeout between two frames

OEM RX at `0x24A8` moves bytes from a FIFO containing multiple bytes into the
buffer, leaving the last byte until timeout. With the actual FIFO threshold 6,
several tail bytes can initially remain without a timeout. Only the timeout flag
(status bit 21, `0x2506–0x252E`) permits completion, state 4. MAINT `hook_rx`
behaves accordingly. State 1 appends additional bytes, including a fresh `~` or
`55` start; it does not resynchronize at the new start.

Schematic example for a listening pack: a foreign 168-byte `42` response followed
by its own 20-byte `42` query without a timeout creates one 188-byte buffer with
the foreign address first. Its own query is never parsed separately and receives
no answer. This happens in OEM and all three checked MAINT builds. A timeout and
subsequent processing between the frames allow the query to be answered. Mixed
ASCII/MAINT binary frames are affected too.

**MAINT does not fix case A.** This is the established reason why 100 ms of
actual bus silence can be too short.

## 3. Case B: timeout occurred, completed frame not yet processed

| Receive sequence | OEM16.06.13 | selected MAINT1.5/1.6 builds |
|---|---|---|
| Completed own query, then foreign frame before main-loop processing | New start can overwrite own query; own answer is lost | Own completed query remains available and is answered |
| Completed foreign frame, then own query before main-loop processing | Own query can replace foreign frame and be answered | Own bytes are discarded until the foreign frame is processed |

Outside state 1, the OEM byte path accepts new start characters even in state 4.
MAINT accepts bytes only in states 0/1, preserving the completed or processing
buffer. The difference is visible at `.Lrx_byte` in
[`mod/firmware/patcher/seplos/payload.s`](../../mod/firmware/patcher/seplos/payload.s).

**This fixes an OEM buffer-overwrite bug.** The fix already exists in the selected
MAINT1.5 build; it was not introduced with 1.6 and is unchanged between the two
1.6 variants. It is recorded in the [MAINT changelog](../../mod/firmware/CHANGELOG.md);
documenting it changes no firmware bytes or version. Its tradeoff is that MAINT
does not queue a second query while the only buffer is occupied. OEM success in
the reverse test therefore does not establish correct pipelining. Older required
tests independently check ready-buffer ownership and IRQ activity during actual
parameter processing ([`seplos/selftest.py`](../../mod/firmware/patcher/seplos/selftest.py)).

UART1 is dispatched at `0x628E–0x6298`, at the end of the main loop and outside
the one-second work block. There is no fixed additional one-second receive lock.
No hard maximum main-loop latency was established. The new counterexample
intentionally delays main-loop processing: it proves a state property, not how
often it occurs in operation.

## 4. Runtime implications and host recommendation

**Established in the emulator:** query loss without the required frame separation,
and both different reactions of a ready buffer. Subsequent correctly separated
queries succeed without restarting; this does not create a permanently stuck
receive lock. The probe shows no effect on SOC or MOSFETs.

**Plausible effects not yet measured on the bus:** missing answers/timeouts,
alternating responsive packs and OEM/MAINT differences under tight timing. A host
timeout after a lost query may create enough silence for the next pack to answer.
Without a wire trace, the contribution of either mechanism to a particular
gateway/installation observation remains open.

The four-image proof below covers the explicitly named historical builds; it does not independently establish every later MAINT release. The maintained [MAINT payload](../../mod/firmware/patcher/seplos/payload.s) retains the ready-buffer ownership guard, but release-specific validation must still identify the exact image.

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
pack succeeds in all four images without an additional simulated pause. A
missing own `44` response is therefore not explained by case A alone. Intervening
foreign bytes or actually received echo need separate evidence; physical echo
was not established here.

## 5. Repeatable counterexample probe

[Probe script](../../mod/tools/firmware-analysis/probe_uart1_receive_gap.py),
[final report](../../local/research/uart1-reception/evidence/UART1-Empfangspause-2026-10-21-final.json).
The report is local evidence and is unavailable in a fresh public clone.

There are 228 passed cases. The probe executes actual SHA-bound Thumb routines
for initialization, RX IRQ, parser, dispatcher and sender, modeling the configured
FIFO threshold and timeout interrupt. Fixtures use local addresses 0 and 3,
foreign synthetic response address 2, gaps of 0/100/105/120/150/200 ms, delayed
main-loop evaluation, release after own transmission, both ownership directions,
recovery, and mixed ASCII/binary traffic. This is neither cycle-accurate CPU/RX
wire simulation nor a new hardware measurement.

The probe uses the project’s `vendor/firmware/`, `local/releases/` and hash-bound historical build reports under `local/builds/oem16.06.13/`. Those private fixtures are required; a fresh public clone alone does not contain them. See the [tool instructions](../../mod/docs/tools/README.md) for dependencies.

```sh
cd /private/tmp
"$PATCHER_PYTHON" -I "$PROJECT/mod/tools/firmware-analysis/probe_uart1_receive_gap.py" \
  --out /private/tmp/uart1-gap-check.json
```

`PROJECT` is the project root; `PATCHER_PYTHON` is the external venv interpreter. The output path must not already exist. The probe models initialization, FIFO thresholds, mixed traffic and completed-frame ownership with synthetic inputs. It does not modify firmware or open devices.

The verified 1.5 image is the selected Power/RTC build `d75a7b24cb6e8590`;
this evidence does not automatically cover every historical image labeled 1.5.
