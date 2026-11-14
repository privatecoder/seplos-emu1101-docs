# Early UART0 master poll completion

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

EMU1101-EXT Light 1.5.6+ and Full 1.6.6+ allow the master to consume a complete valid slave response before the native 30-tick polling deadline. There is still exactly one outstanding request. The next main-loop polling pass can then start the next request. The firmware does not send requests in parallel or transmit the next request from the receive interrupt.

## Completion and timeout

The OEM evaluator waits for the expiry flag even when reception has finished. With nominal 5 ms timer ticks, this imposes approximately 150 ms per slave. Eleven slaves therefore require approximately 1.65 seconds of polling dwell before round-complete aggregation can run.

The extension resets the timer for each new request and checks the native completed-reception state. Early acceptance requires the complete 82-byte OEM `5A` response, matching address, version/type/length fields, uppercase hexadecimal encoding, terminator and additive checksum. Only then does the original parser and snapshot decoder run. The shared RX buffer is owned exclusively during validation and native parsing by temporarily masking UART0 alone. Short flag updates save and restore PRIMASK; other enabled interrupts remain available during the frame scan.

Malformed, truncated, overlong, bad-checksum and foreign-address candidates do not advance the poll. Discarding a completed invalid candidate does not restart the deadline. A subsequent valid response can still complete the same transaction. Missing responses reach the original 30-tick expiry path and its failure/offline handling once. Broadcast On/Off transactions retain the native evaluation and turnaround behavior because they do not expect a normal slave reply.

The deadline is a timer-based fallback serviced by the main loop, not an exact physical cut-off or response timestamp. A ready valid response encountered when expiry is also pending can be consumed once. No new transaction identifier is added: a sufficiently delayed response with the same address and layout cannot be distinguished from a later request to that address. The extension does not create a second receive buffer.

The native UART0 FIFO threshold, timeout-driven receive completion, transmit direction changes, address-chain discovery, and master/slave dispatch are retained. Full reception still includes the native end-of-frame silence decision. The change does not make the last byte immediately visible as a completed response independently of that mechanism.

## Aggregation and charge-current limits

A completed poll round still gates the native aggregate update in the slow main-loop pass. There is no aggregate update for each individual reply and no new CAN transmission schedule. A faster round may fit within an earlier slow pass; its duration depends on slave response latency, native RX silence and main-loop scheduling.

Light 1.5.6 and Full 1.6.6 retain an ordinary CCL ramp of **one ampere per online pack per aggregate update**, in both directions. Full 1.6.7 retains that default but allows a separate downward factor of 1–20. With factor 1 and twelve online packs, a pure warning-driven decrease from 1560 A toward 10 A requires 130 updates; update 60 reaches 840 A. These numbers are arithmetic test cases, not recommended operating limits. Earlier round completion can reduce the elapsed interval between eligible aggregate updates, but cannot make this ramp instantaneous. Full's existing Off/no-charge-path override remains separate and can bypass the ordinary descent.

The optimization affects the board acting as master. Slaves continue using their existing response protocol; all packs need not be updated merely to understand the faster request cadence. Hardware coexistence with mixed firmware still needs a physical bus test.

## Calculated timing across firmware versions

The reference below uses OEM **16.06.13** (application SHA-256 `5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95`) and EXT releases based on it. The retained `.3` contracts inherit the native polling/ramp behavior; `.4` adds diagnostics and `.5` fixes scheduler flag loss, neither intentionally changes the nominal CCL step or polling dwell. This does not establish identical timing under a triggered race. Earlier development images require exact image identification and are not assigned new version numbers here. Older OEM 16.04.06/16.06.03/.04/.05/.11/.12 have version-specific baud, limit and protection behavior: the seconds estimates below are not a measured or individually verified timing catalogue for those images. See [OEM differences](../../../analysis/protocols/can.md#6-can-version-history-confirmed).

| Master firmware | Successful slave poll | Downward / upward step per online pack per update | Nominal 12-pack aggregate interval |
|---|---|---|---|
| OEM 16.06.13 | Wait for 30 ticks, about 150 ms | 1 A / 1 A | About 2 s |
| Light 1.5.3, 1.5.4, 1.5.5 | Same fixed window | 1 A / 1 A | About 2 s |
| Full 1.6.3, 1.6.4, 1.6.5 | Same fixed window; separate Full override | 1 A / 1 A | About 2 s |
| Light 1.5.6 | Validated early completion; original expiry on missing/invalid reply | 1 A / 1 A | About 1 s **if** the entire round fits; otherwise 2 s or longer |
| Full 1.6.6 | Same early completion; separate Full override | 1 A / 1 A | Same conditional interval |
| Full 1.6.7 | Same early completion; separate Full override | Configured 1–20 A / fixed 1 A; default 1 | Same conditional interval; setting the factor does not change scheduling |

### Round duration and the one-second gate

Let `S` be the number of slave slots actually polled, `N` the online count including the master, and `P` the aggregate-update interval. They are separate quantities. Missing configured slaves can still consume timeout slots; warning packs may remain online. A completed round is consumed once, then polling resumes. The nominal aligned model is:

```text
fixed-window round R ≈ S × 0.150 s
early-completion round R ≈ sum(actual transaction durations)
P ≈ max(1, ceil(R / 1 s)) × 1 s
```

This model assumes a stable round starting just after a slow pass, no extra broadcasts/discovery, and negligible additional main-loop delay. Close to a one-second boundary, a small delay can add a whole slow pass. There is no hard upper bound on real execution latency in this table.

| Configured packs, including master | Polled slaves S | Fixed-window round | Fixed-window P | Early-poll wire time alone at nominal 19,200 baud |
|---:|---:|---:|---:|---:|
| 1 | 0 | No slave round | About 1 s | Not applicable |
| 4 | 3 | 0.45 s | About 1 s | 0.156 s |
| 8 | 7 | 1.05 s | About 2 s | 0.365 s |
| 12 | 11 | 1.65 s | About 2 s | 0.573 s |
| 16 | 15 | 2.25 s | About 3 s | 0.781 s |

Each 18-character request plus 82-character reply needs `100 × 10 / 19200 ≈ 52.1 ms` on an 8N1 wire. That is not a complete transaction duration. The modeled native master RX completion alone adds approximately 5.2 ms of silence after reception; slave processing, its request reception, turnaround and main-loop work also contribute. The [native timing test](../../firmware/patcher/seplos/polling_tests.py) derives the divider and ten-character timeout from initialization. It does not measure a real round. A faster UART wire therefore does not imply a CCL update after every 52 ms or after every slave reply.

For eleven slaves, illustrative complete transaction durations give:

| Assumed complete transaction duration | Round duration | Nominal aligned P |
|---:|---:|---:|
| 70 ms | 0.77 s | 1 s |
| 80 ms | 0.88 s | 1 s |
| 100 ms | 1.10 s | 2 s |
| 150 ms | 1.65 s | 2 s |

These are conditional examples, not measured performance or guaranteed timeout service. Missing/invalid replies, stale snapshots, a busy main loop or broadcasts can eliminate the nominal speed gain. Even with very fast valid replies, the ordinary aggregate calculation still uses the one-second slow pass.

### Step counts and seconds

For a constant lower target `T`, initial transmitted limit `C0`, constant online count `N >= 1` and downward factor `d`, with no direct override:

```text
CCL(k) = max(T, C0 - k × N × d)
K_down = ceil((C0 - T) / (N × d))   when C0 > T; otherwise 0
K_up   = ceil((T - C0) / N)         when T > C0; otherwise 0
scenario duration ≈ K × P
```

The target need not be divisible by the step. The final update saturates exactly at the target. For `K >= 1`, the time from the **first affected update** to the final one is `(K - 1) × P`. From a real warning event it is `delay_to_first_affected_update + (K - 1) × P`; detection, snapshot refresh and polling phase make that initial delay unknown here. The `K × P` columns below are rounded scenario budgets, not warning-to-inverter deadlines. CAN may send repeated unchanged limits between aggregate updates; those transmissions are not extra ramp steps.

The following generic examples use twelve continuously online packs and a fixed ordinary target. Values are examples, not installation settings or recommended current limits.

| Ramp scenario | Updates at d=1 | OEM / Light .3–.5 / Full .3–.5 at P=2 s | Light .6 / Full .6 / Full .7 default at P=1 s | Same early-poll profiles if P=2 s |
|---|---:|---:|---:|---:|
| 1560 A toward 10 A: first value at or below 840 A | 60 | ≈120 s | ≈60 s | ≈120 s |
| 1560 → 10 A, exact target | 130 | ≈260 s | ≈130 s | ≈260 s |
| 900 A toward 10 A: first value at or below 840 A | 5 | ≈10 s | ≈5 s | ≈10 s |
| 900 → 10 A, exact target | 75 | ≈150 s | ≈75 s | ≈150 s |
| 840 → 10 A, exact target | 70 | ≈140 s | ≈70 s | ≈140 s |
| 130 → 10 A, exact target | 10 | ≈20 s | ≈10 s | ≈20 s |

Full 1.6.7 changes only the downward step when configured above 1:

| d, A per online pack/update | Bank step, N=12 | Updates until ≤840 A from 1560 A toward 10 A | Updates 1560 → 10 A | Seconds for exact 10 A at P=1 s / P=2 s | Updates 900 → 10 A | Seconds for exact 10 A at P=1 s / P=2 s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 (default) | 12 A | 60 | 130 | ≈130 / 260 | 75 | ≈75 / 150 |
| 2 | 24 A | 30 | 65 | ≈65 / 130 | 38 | ≈38 / 76 |
| 3 | 36 A | 20 | 44 | ≈44 / 88 | 25 | ≈25 / 50 |
| 5 | 60 A | 12 | 26 | ≈26 / 52 | 15 | ≈15 / 30 |
| 10 | 120 A | 6 | 13 | ≈13 / 26 | 8 | ≈8 / 16 |
| 20 | 240 A | 3 | 7 | ≈7 / 14 | 4 | ≈4 / 8 |

At d=3, 1560 → 10 A reaches 12 A after 43 updates, then clamps to 10 A on update 44. At d=20, it reaches 120 A after six updates, then 10 A on update seven. Neither target divisibility nor a special step multiple is required. Across all factors, recovery from 10 → 900 A still takes 75 updates and 10 → 1560 A takes 130 updates at N=12. With P=1 s these are approximately 75/130 s; at P=2 s, approximately 150/260 s. Earlier polling can accelerate the elapsed rise, but the Full 1.6.7 setting itself does not increase the upward step.

### Meaning in operation

- **The target must actually fall.** One warning pack does not by itself select a 10 A bank target. If each eligible pack contributes a hypothetical 130 A, eleven eligible packs still request 1430 A. With an assumed aggregate inverter envelope of 840 A, even an immediate reduction to 1430 A would not reduce charging at that envelope. Six eligible packs target 780 A; that is below the envelope. A faster ramp cannot compensate for an unchanged or still-high target.
- **Crossing the inverter envelope and reaching the target differ.** With 1560 A initially requested and an 840 A envelope, factor 1 needs 60 updates to reach equality and 61 to fall strictly below it. Factor 10 reaches equality after six updates and falls below on seven; factor 20 after three and four respectively. Reaching equality need not reduce actual current. At d=10 and P=1 s, approximately 13 s to 10 A is a useful scenario comparison with the fixed-window 260 s, not a measured twenty-fold improvement.
- **This limits the bank request, not each pack.** Warning packs can remain electrically connected; current sharing does not follow a per-pack CCL allocation. Local hardware limiting and charge-MOSFET protection have separate triggers. Larger downward steps neither establish electrical current response nor eliminate individual-cell overvoltage transients. See [warnings and local limiting](../../../analysis/firmware/states-and-triggers.md#charge-warnings-bank-ccl-and-local-current-limiting).
- **Direct overrides are separate.** In the reference OEM .13 path, all-charge-blocked and highest-cell-over-threshold branches directly write zero; a heating request can raise a minimum under the documented priority order. Full can additionally cap the result when an online record is logically Off and has no charge path. These changes bypass the ordinary descent in that aggregate evaluation; detecting the changed state, collecting it, sending CAN and inverter response still take time. DCL has no corresponding ordinary ramp.
- **Online loss and poll configuration matter.** Fewer online packs reduce `N × d`; remaining configured timeout slots can still prolong the round. Do not compute the new speed from eligible-pack count or a stale online count. A no-slave/maintenance master aggregates only itself and uses N=1: for a hypothetical 900 → 75 A ordinary reduction, d=1 requires 825 updates (≈825 s at P=1 s), d=10 requires 83 updates (≈83 s), and d=20 requires 42 (≈42 s), absent an override. Maintenance is not a bank-wide instantaneous current limit.
- **Choose the factor deliberately.** Higher factors make ordinary reductions larger while recovery remains gradual. If warnings fluctuate, repeated large drops followed by slow recovery may reduce charging throughput. The range 1–20 is an implemented configuration bound, not proof that any one value is optimal for an inverter. Default 1 preserves the previous per-update behavior.

The [version matrix](ext-version-comparison.md#polling-and-ccl-matrix-through-full-167) compares the same conditions by release; the [configuration contract](configurable-ccl-ramp.md) defines the separate master-effective EXT setting. Native tests establish arithmetic and control-flow properties. Real UART0 round duration, CAN delivery and electrical inverter response remain unmeasured.

## Image and host contract

Two guarded main-loop call sites are added in each profile. The polling extension allocates no persistent RAM. Current Light/Full totals, image sizes, build IDs, hashes and mandatory test counts are bound by [release metadata](../../firmware/releases/README.md).

The wrapper uses 16 stack bytes; its validator adds 24 while called. Native callees retain their own stack usage, with the wrapper's 16 bytes added above that call chain. These figures are not a total firmware stack high-water measurement.

The Light 1.5.6 / Full 1.6.6 profiles retain the 21-byte EXT05 layout, image-flag meanings and `000F` remote capability mask. Early polling adds no writable parameters, enable switches, protocol selectors or migration steps. Full 1.6.7 separately adds [CCL configuration](configurable-ccl-ramp.md) and capability `0010`. The firmware version and exact image identity identify this feature. Light/Full .4 and .5 builders remain supported and reproduce their prior image hashes.

## Validation and limits

Mandatory native execution tests cover valid complete responses, rejects and recovery within the same deadline, timeout/offline accounting, per-request reset, broadcasts, transmit turnaround, address-chain discovery and master/slave role gates. They execute the actual native parser and decoder, complete eleven-slave rounds and check the aggregate gate plus ordinary CCL arithmetic and Full overrides.

The UART0 model derives configuration from actual initialization and exercises FIFO delivery and silence under both documented RX-threshold interpretations. Controlled interrupt schedules exercise enabled timer/comparator handlers, UART0 exclusion, saved NVIC/PRIMASK state, deadline orderings and instruction-boundary interleavings. Source guards bind the reachable native contracts, exact main-loop call sites and IRQ ownership; unknown source contracts are refused.

These are offline instruction/peripheral-model checks. The model does not charge elapsed physical time for every executed instruction. Results establish neither measured round latency nor electrical RS485 turnaround, real interrupt latency, stack high-water use or sustained operation across physical packs. No .6 image is hardware-tested or flashed by these checks.

[Build and validation](build-and-validation.md) · [Intra-pack protocol](../../../analysis/protocols/intra-pack.md) · [Version comparison](ext-version-comparison.md)
