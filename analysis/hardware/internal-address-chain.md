# Internal address lines in the RS485 sockets

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

Updated2026-10-24. **The firmware contains a GPIO pulse chain for automatic
address assignment that fits the purpose of the contacts labelled “Internal
communication”.** Exact physical wiring from RJ45 pins4/5 to individual MCU
signals remains unproven.

Code addresses below refer to OEM16.06.13, application SHA256
`5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95`.
The relevant native routines remain byte-identical in MAINT1.5.2/1.6.3.
No board was accessed or reconfigured for this investigation.

## Manufacturer evidence

The [48150 manual](<../../vendor/docs/specs/Seplos%20BMS%2048150-1101-10E%20%28EN%29.pdf>) **PDF p.28** labels
RS485 socket pins4/5 internal communication. Its cable drawing connects4→4
and5→5. **PDF p.31**,§10.5 shows a directed COM OUT/COM IN chain;§3.22 calls
automatic DIP addressing optional.

The [48200 manual](<../../vendor/docs/specs/EEL%2048200-1101-10E%20%28EN%29.pdf>) **PDF p.33 / printed p.28**
instead labels these contacts NC. Neither drawing proves the exact electrical
implementation on every10E board.

## Confirmed firmware mechanism

The numbers7/8/9 below are **bits of MCU GPIO port `0x50002000`**, not RJ45
contact numbers.

|GPIO bit|Native role|Evidence|
|---|---|---|
|7|Address-pulse output|`0x92F4` configures output/idle high;`0x9410` drives low during a pulse and high afterward.|
|8|Address-pulse input|`0x9334` measures high/low duration and decodes a value from low-pulse length;`0x944C` assigns it as the local address.|
|9|Debounced peer/successor-status input|`0x93D0` updates `0x200000F6.bit3`;`0x944C` starts forwarding when that bit is set and no output pulse is active. “Successor present/request” is the inferred meaning of this use.|

The gate at `0x607C` controls calls at `0x6080/0x6084/0x6088`, guarded by **Group7.bit5=1**. Assignment
at `0x944C`,called from `0x620E`,also checks bit5. The fast-handler period is
nominally5ms:timer setup at `0x5FC4` divides the core clock by200. This is
derived from code,not a physical jitter measurement.

These routines handle GPIO levels and pulse lengths,not UART byte frames.
They are not additional parameter commands on UART0's normal RS485 wires
(pins 1/2 and 7/8).

1. `0x9334` divides measured low duration by10,rounding up only for remainder
   **greater than5**;an exact remainder5 rounds down.
2. `0x944C` assigns the decoded value to `0x20000027`,clamped to21. Group7.bit6
   changes decoded0 to1,preventing that pack from becoming master.
3. When GPIO9 is debounced low and no pulse is running, the next
   pulse length is **(local address+1)×10** fast-handler calls.
4. `0x9410` sends that low pulse on GPIO7:nominally50ms for address0,100ms for
   address1,and so on.

This fits a chain in which each board receives its position and forwards the
next position. Group7.bit5=0 skips ongoing pulse processing and keeps ordinary
DIP addressing. It does not prove the contacts are electrically unused or safe
for arbitrary other connections:GPIO7 is still initialized at startup.

## More precise boundary behavior

|GPIO8 condition|After500 fast calls|Nominal duration|
|---|---|---|
|Continuously high|Decoded address0|2.5s|
|Continuously low|Decoded address21|2.5s|

A quiet high input is therefore compatible with determining the first board.
The circuit that establishes the input level is not known from this code.

GPIO9 debounce checks the count before incrementing it. Starting with zero
counters,it sets flag bit3 after **11low calls** and clears it after
**201high calls**,nominally55ms and1005ms. The comparison thresholds are10/200; the counts above include the check-before-increment order.

In intra-pack0x5A,event8.bit7 is the inverse of `0x200000F6.bit3` (16.06.12: `0x200000EF`; response write `0x1348` in16.06.13). With Group7.Bit5=0, the producer `0x93D0` is skipped, the flag remains0, and event8.Bit7 is normally `0x80` independently of GPIO9. This value is not a fault. It is consistent with24 historical captures.

In automatic-addressing mode, the master uses
successor status to extend its slave count,with the already documented limit
of21slaves. A complete physical multiboard chain was not exercised here.

## What remains unknown about pins4/5

Manual and code evidence strongly suggest automatic address chaining,but do
not identify which contact in each socket reaches GPIO7/8/9. Intermediate
transistors/optoisolators,voltage levels,pullups,output type and differences
between input/output sockets remain unknown.

Two contacts **per socket** can accommodate three MCU signals if the two
sockets are wired differently. This is a possible explanation of COM IN/OUT,
not a measured circuit. Power-off continuity tracing or a passive logic
capture on a suitable laboratory board would resolve the physical mapping.
The firmware contains no text or pin diagram that unambiguously assigns an
RJ45 contact to a GPIO signal.

## Persistent offline checks

The [address-chain probe](../../mod/tools/firmware-analysis/probe_address_chain_v16.py) uses the source image and the ignored evidence directory `local/research/address-chain/evidence/Interne-Adressleitungen-2026-10-24/`, with disassembly, source snapshot, dependency hashes and results.
The probe executes actual OEM Thumb in the existing Unicorn machine with
synthetic GPIO levels;it opens no serial ports and changes no image or NVM.

**50 groups passed:**receive1..21,stable high/low limits,exact debounce
boundaries,assignment plus forwarding0..21,Group7.bit6,and byte-identical native
routines in the verified MAINT1.5.2/1.6.3 images. The Group7.bit5 call gate is
checked statically;physical timing and RJ45 wiring are not simulated.

Run with the existing patcher venv/Unicorn,Python `-I` from `/private/tmp`:

```sh
"$PATCHER_PYTHON" -I "$PROJECT/mod/tools/firmware-analysis/probe_address_chain_v16.py" \
  --out /private/tmp/seplos-address-chain-new.json
```

`PATCHER_PYTHON` is the venv Python executable;`PROJECT` is the project root. Output is created exclusively and is not overwritten.
The probe is bound to OEM .13 and does not silently accept unknown firmware. It also loads the retained MAINT 1.6.3 build report and MAINT 1.5.2/1.6.3 images from ignored `local/`; those historical fixtures are required and are absent from a fresh checkout.
