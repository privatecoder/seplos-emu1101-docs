# FirmwareUpdate.exe: bootloader protocol and update sequence

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket. The letters in bootloader commands such as `R F L` and `W F D` are literal command bytes, not port selectors.

Source: `BatteryMonitor V2.1.12_20/FirmwareUpdate.exe` inside [BatteryMonitor v2.1.12_20.zip](<../../vendor/software/batterymonitor/BatteryMonitor%20v2.1.12_20.zip>) (.NET Framework 4.5.2, 40,960 bytes), analyzed **statically only**. Decompiled with ILSpy 11.1 (`ilspycmd -p` for C#, `ilspycmd -il` for IL). The Windows PDB was not loaded; names come from metadata. Timing values are historical laboratory-board measurements, distinct from static updater findings.

**Evidence labels:**

- *Confirmed (RVA x, IL_y)*: directly present in code. RVA is the method start; `IL_y` is the offset within the method as emitted by ILSpy.
- *Measured*: observed on the laboratory board.
- *Assumption*: inferred, without confirmation in the updater code or a measurement. The bootloader code itself is unavailable.

Classes involved: `UpdateProgramImpl` (sequence), `BootDataFrame` (binary frames), `AppDataFrame` (ASCII frames), `SourceDealUtil` (file reading), `MainFrm.sendBootDataFrame` (sending and response evaluation), `OperateCommand` (character constants).

## 1. Sequence at a glance

| # | Frame | Purpose | Success according to updater | On failure |
|---|---|---|---|---|
| 1 | ASCII `0x45`, type 6, to `packIndex` | Restart application into bootloader | Always; no ACK expected | – |
| – | Wait 50 ms | | | |
| 2 | `R F L` | Query package size | Response `R F B` | Abort: “获取包大小失败” (could not obtain package size) |
| 3 | `W F E` | Enable flash writing | `R F B` or `W F B` | Abort: “Flash写使能失败” |
| 4 | `W F D` × n | Data blocks | `R F B` or `W F B` | Abort at block i (“写入第 i 条数据出错”); **no retry** |
| 5 | `W F G` | Start program | `R F B` or `W F B` | “下载失败” (download failed) |

*Confirmed (RVA 0x5AEC, `<downLoadProgram>b__14_0`)*: each step is sent **exactly once**. `IsSucess=false` is set before each step, and processing continues only on success. No step has a retry.

## 2. Entry: ASCII restart

- *Confirmed (RVA 0x59FC, `ResetFrame`)*: `AppDataFrame(VER=38=0x26, CID2=69=0x45, INFO 01 06 00)`, `ADR = config.packIndex` (0–15, “Pack Num” selection).
- *Confirmed (RVA 0x5E98, `ToTxdString`)*: Seplos ASCII with `~`, hexadecimal fields, LENGTH with nibble checksum (`getLengthCRC`, RVA 0x5FFC), and CR. Calculated pack-0 example: `~26004645A006010600FC67\r`.
- *Confirmed (`MainFrm.sendAppDataFrame`)*: calls `DiscardInBuffer()` before sending, then immediately sets `IsSucess = true` after writing. No response is read.
- *Measured*: `~20004645A006000600FC6E\r` (VER 0x20, INFO 00 06 00) also opens the bootloader window; the application gives no response.
- *Measured (laboratory result 10)*: on a slave-configured board (DIP address 1), reset to address 1 (`~26014645A006010600FC66`), `R F L`, and a complete update also work. The bootloader is address independent; only reset selects the pack.
- *Confirmed (RVA 0x5AEC, IL_002c)*: followed by `Delay(50)`, a busy wait using `GetTickCount`.

## 3. Binary frames (`BootDataFrame`)

```text
3A 3A 3A 3A | CID1 | CID2 | CID3 | LEN hi lo | ADR hi lo | DATA[LEN] | CHK hi lo | 0D 0D 0D 0D
```

- *Confirmed (RVA 0x6448, `DataFrameToByteArray()`)*: order as above, LEN and ADR encoded as 16-bit big-endian values from `short`. Only this variant is sent. The overload `DataFrameToByteArray(index, offset, count)` (RVA 0x65C8) is never called.
- **Transmit checksum**, *confirmed (RVA 0x6448, IL_0105)*: `s = sum of bytes from CID1 through the final DATA byte; s = s % 65535; CHK = (~s + 1) & 0xFFFF`.
  - The modulus is **65535**, not 65536. They differ only for `s ≥ 65535`, possible with 256-byte blocks only when almost all bytes are `0xFF`. *Calculated*: the largest block sum in all seven original images is 38,380, so this case does not occur there.
  - This is the historical OEM updater's arithmetic. The maintained helpers use two's complement modulo **65536**, including valid `0xFF`-filled blocks whose body sums reach or exceed 65535; see the current host requirements in §8. The arithmetic in the unavailable bootloader code is not established by the OEM executable alone.
- **Receive checksum**, *confirmed (RVA 0x63F8, `getFrameCRC`)*: sum starting at index 4 over `length − 10` bytes, `% 65536`, then two's complement.
- **Response parser**, *confirmed (RVA 0x613C, `Parse`)*: requires `::::`, CID1 in {`R`,`W`}, `LEN == total length − 17`, a valid checksum and four `0D` bytes. CID2/CID3 validation is ineffective: the `&&` conditions are always false. **The buffer must contain exactly one frame**; even one extra byte makes the LEN check fail.

### Command codes

| Character | Constant in `OperateCommand` | Use in updater |
|---|---|---|
| `W` 0x57 / `R` 0x52 | CID1_Write / CID1_Read | Write / read |
| `F` 0x46 | CID2_Flash | Every transmitted frame |
| `E` 0x45 | CID2_**Eprom** | **Only as CID3** in `W F E`, *confirmed (RVA 0x592C, IL_001d)*. No EEPROM command (`x E x`) is ever sent |
| `L` 0x4C | CID3_L | `R F L`: package size |
| `D` 0x44 | CID3_D | `W F D`: data |
| `G` 0x47 | CID3_G | `W F G`: start |
| `B` 0x42 | CID3_B | **Responses only**: success (`R F B`, `W F B`) |
| `N` 0x4E | CID3_N | **Responses only**: `R F N` = error (“响应出错”, response error) |

*Assumption*: `B` and `N` mean ACK/NAK. Using `CID2_Eprom` as CID3 is probably a source-code mix-up; on the wire it simply produces `W F E`.

**The updater has no flash-read, verify or erase command.** The executable cannot establish whether the bootloader supports further commands.

## 4. Individual frames

| Frame | LEN | ADR | DATA | Bytes |
|---|---|---|---|---|
| `R F L` | 0 | 0 | – | `3A3A3A3A 52 46 4C 0000 0000 FF1C 0D0D0D0D` *(measured, identical)* |
| `W F E` | 0 | 0 | – | `3A3A3A3A 57 46 45 0000 0000 FF1E 0D0D0D0D` *(calculated)* |
| `W F D` | PackageLen | 16 × block index | One block | 17 + PackageLen bytes |
| `W F G` | 0 | 0 | – | `3A3A3A3A 57 46 47 0000 0000 FF1C 0D0D0D0D` *(calculated)* |

- *Confirmed (RVA 0x58EC, 0x592C, 0x59BC)*: `R F L`, `W F E` and `W F G` are built with an empty `params byte[]`, producing `Data = null`, LEN = ADR = 0.
- *Confirmed (RVA 0x596C, `ReqWriteFlash`)*: `LEN = sendMsg.Length`, `ADR = (short)addr`.

### Response to `R F L`

- *Measured*: `3A3A3A3A 52 46 42 0002 0000 0100 FF23 0D0D0D0D`: `R F B`, package size 256, about 24 ms after the request.
- *Confirmed (RVA 0x24DC, IL_00a7–IL_00ff)*: only for an `R F L` request is `PackageLen = byteToInt16(Data)` assigned; all data bytes are interpreted big-endian, without a length check.
- *Confirmed (RVA 0x24DC, IL_022b onward)*: if the response arrives only on the second read attempt (+50 ms), it counts as success but `PackageLen` remains at its initial value **512** (`.cctor`, RVA 0x5AC6). Block size and ADR increment then disagree. This is an original-updater bug.

## 5. Transmitted data stream

### 5.1 File to byte stream

*Confirmed (RVA 0x5604, `getValidBytesDataFromFile`; RVA 0x563C, `getValidDataFromString`, IL_000a–IL_001d)*:

- Calls `File.ReadAllLines`; for **every line**, takes the byte count from characters 1–2 and the data field starting at character 9. Record type, address and checksum are **ignored**.
- Concatenates the data fields of **all** records in file order:
  1. The 16 header records: 256 bytes containing `SWM181RCT6_64_M0`, `EMU1101_10D_HW16`, `RS485Y19200N9600` and 208 × `0x55`. **The header is transmitted.**
  2. Type-00 data: a contiguous image starting at address 0.
  3. The four data bytes of the type-05 record, `00 00 00 C1` (start address).
  4. Type 01 (EOF) contributes zero bytes.
- *Confirmed (`MainFrm.browseBtn_Click`)*: a file is loaded only if its name **contains** `.ehex`; a plain `.hex` name is rejected.

*Calculated from the seven original images*: stream length = 256 + image length + 4 bytes. For example, 16.06.13 gives 256 + 53,092 + 4 = 53,352 bytes: 209 blocks of 256 bytes, with 152 padding bytes in the last block. All images end in `00 00 00 C1`; none has type-04 records or gaps.

**Consequence for a replacement:** the original would transmit images containing gaps or type-04 records incorrectly, with displaced data. A replacement should reject such files rather than silently transmit a different stream.

### 5.2 Blocks

*Confirmed (RVA 0x5810, `getRealWriteFlashBytes`)*:

- Block count = ⌈length / PackageLen⌉.
- Each block is a new `byte[PackageLen]` (IL_0060, IL_0089): **the last block is padded with `0x00`, not `0xFF`**. LEN always equals PackageLen, including the final block.
- Blocks are sent in ascending order. Block 0 is the first 256 bytes, the header.

### 5.3 ADR per block

*Confirmed (RVA 0x5AEC, IL_019a–IL_019e)*: ADR starts at zero and increases **by 16 for each block**, regardless of PackageLen (`num += 16`).

- At PackageLen 256, ADR is the stream offset in **16-byte units**: block i → ADR = 16·i, offset = 256·i. *Assumption*: the bootloader multiplies ADR by 16.
- PackageLen 512, the initial value retained after a late `R F L` response, does not fit this increment. A replacement must require 256-byte blocks or adjust ADR. Without bootloader code, **accept only 256**.
- *Assumption*: the bootloader validates MCU/device/interface information in block 0 (ADR 0, header), then writes the application from stream offset 256 to flash address 0. Whether the header itself is written into flash and what happens to the final `00 00 00 C1` remain **open**.

## 6. Original timing and error handling

*Confirmed (RVA 0x24DC, `MainFrm.sendBootDataFrame`)*:

- Calls `DiscardOutBuffer()` before sending (IL_0027); it **does not clear the input buffer**.
- Sends the frame, then waits a **fixed** `delay` milliseconds (IL_0059; `FirmwareUpdate.exe.config` sets `delay = 350`).
- If bytes are available, reads everything and parses/evaluates it once:
  - `R F B` → success (IL_00a7–IL_0106).
  - `W F B` → success (IL_0118–IL_013d).
  - `R F N` → “Response error” (IL_014f–IL_0174).
  - Anything else → “Unknown error”.
- If no bytes are available, waits 50 ms (IL_022b) and checks once more. Evaluation is similar but only `R F B` succeeds and `R F N` is recognized; **`W F B` does not count as success in this branch**. Otherwise: “Receive data fail”.
- Exceptions, including parser errors or incomplete frames, cause failure.
- *Confirmed (`OpenSerialCom`, RVA 0x2B48)*: ReadTimeout 2200 ms, WriteTimeout 4000 ms; these have little practical effect because reception only checks `BytesToRead`. Default serial settings: 19200 8N1.
- *Confirmed (`stopDownloadProgram`)*: Cancel ends the thread with `Thread.Abort()` and sends **nothing** to the board.

*Calculated*: 16.06.13 needs about 103 s: 209 blocks × (273 bytes ≈ 142 ms at 19200 baud + 350 ms).

*Measured 2026-10-11 (laboratory result 8)*: the fixed waiting period is **unnecessary**. Waiting zero additional time after each `W F B` response allowed a complete update in 33.4 s without errors. Response times (`W F D` median 156 ms from start of transmission) were the same with 0, 100 and 350 ms extra pauses. The bootloader acknowledges only after writing.

**Initial timeline**, *confirmed and measured*: reset → 50 ms → `R F L` (response after about 24 ms) → 350 ms wait → `W F E` about 0.4–0.45 s after reset. This is within the measured 0.65–0.8 s entry window. *Assumption*: `R F L` establishes a session, so later frames, even minutes later, are no longer subject to that deadline. Only the entry window for `R F L` was measured.

## 7. Open points and laboratory findings

1. **Responses to `W F E`, `W F D`, `W F G`: resolved by measurement**, 2026-10-11 (laboratory result 7): consistently **`W F B`**, `3A3A3A3A 57 46 42 0000 0000 FF21 0D0D0D0D`. Time from transmission start: `W F E` 23 ms, `W F D` 153–233 ms (median 156 ms, including about 142 ms transmission), `W F G` 100 ms. A complete 16.04 → 16.06.13 update succeeded; parameter-flash records were unchanged.
2. **What does `W F E` erase?** *Measured 2026-10-11 (results 7 and 9), interpretation probable*: not the entire application area, given its 23 ms response. Block 0 (header) and every 16th block starting at block 1 (stream offset 256 + k·4 KiB) receive slower acknowledgments. The bootloader probably erases each 4-KiB sector when first writing at its boundary, placing the application at flash address 0 from stream offset 256. An interruption could leave a mixture of new and old application data.
3. **After interruption:** does the bootloader start automatically after reset when the application is absent or incomplete, perhaps using the reset vector or an identifier? Can the update be restarted? This determines recovery logic.
4. **May a block be repeated?** The updater never does so. It is unknown whether a duplicate write to the same ADR is safe; flash writes without erasure only change 1→0.
5. **Header validation:** does an incorrect header produce `R F N`? What is present at flash ADR 0 afterwards?
6. **Window after `R F L`:** how long can the bootloader wait between frames before starting the application or aborting?
7. **Several packs on one bus:** OEM16.06.13 parser replay discards bootloader traffic without replying for all seven vendor streams when the master is silent; see the addressed-update conditions below. Electrical behavior on a complete shared bus remains unmeasured.

## 8. Consequences for an OpenBMS updater

Current host requirements follow the maintained [flashing guide](../../mod/docs/tools/flashing.md), [entry helper](../../mod/tools/device/boot_entry.py), [local flasher](../../mod/tools/device/flash_gap.py) and [recovery helper](../../mod/tools/device/flash_recovery.py). The OEM observations above describe the original executable; its permissive response handling and checksum quirk are not the maintained host policy.

- Validate the complete EHEX and selected release identity before opening the device. Preserve the original stream construction: the 256-byte header, contiguous application, type-05 data, final `0x00` padding and ADR = 16 × block index. The maintained frame checksum is **`(-sum(body)) & 0xFFFF`** (modulo 65536). Valid `0xFF`-filled blocks with sums ≥ 65535 are supported; [regressions](../../mod/tools/device/tests/test_flash_gap.py) cover sums 65535 and 65551. Reaching those sums is not a rejection condition.
- For application entry, reset the selected pack **once**, then use bounded **read-only `R F L` probes**. Collect fragmented responses completely before another probe; preserve pending bytes while entry is in progress. A fixed 50 ms probe cannot bound MAINT pre-reset SOC-save time. A valid reset error such as RTN08 aborts entry. For an already reachable bootloader, use `R F L` directly, without another application reset.
- Before any `W F E` or `W F D`, require a **complete valid `R F B` response**, bootloader ADR **0**, LEN **2**, DATA **`01 00`** (256 bytes), correct checksum and four trailing `0D` bytes. Require a **complete empty `W F B`** (LEN **0**, ADR **0**, valid checksum/trailer) for **every** `W F E`, `W F D` and `W F G`. An `R F B` response cannot acknowledge a write. Absent, malformed, foreign, nonempty or unexpected responses abort; `R F N` is an error.
- Await each complete ACK with a bounded timeout before sending the next frame. Preserve an in-flight fragmented or delayed reply; blanket input flushing before every frame is not a response-validation strategy. Never replay reset, erase or program operations automatically. `W F B` carries no block sequence identifier, so a delayed ACK after an uncertain transfer cannot safely be assigned to another block. These local serial helpers do not establish gateway UART timing or recovery after every possible interruption.
- Before `W F E`, the measured bootloader can time out back to the application. From `W F E`, treat the programming outcome as uncertain until the application returns and is independently verified. `flash_gap.py` checks a checksummed, addressed **0x51** response before reset and after return; that proves application responsiveness and a version field, not the exact MAINT build or parameter preservation. `flash_recovery.py` finishes after write ACKs and requires application verification separately. Follow the [post-programming checks](../../mod/docs/tools/flashing.md#after-programming): validate the fresh typed 0x51 identity response, query **64/03 MNT** where supported (current **MNT04, 19-byte** layout), compare exact build ID/flags with the selected image, and compare **0x47 and 0xA2/0xA4** with the saved parameter/serial baseline. Retain manual verification where the helper does not implement these checks.


## 9. Manufacturer entry instructions

The [manufacturer update guide](<../../vendor/docs/batterymonitor/BatteryMonitor%20Firmware%20updating%20Guide.pdf>), also supplied in the 16.06.11 ZIP, gives these entry instructions:

- **Reason according to Seplos:** "BatteryMonitor cannot connect" or "with two parallel packs, only one is online at the inverter". The cause is said to be a "communication interference in the previous firmware". The remedy is said to be the update to "16.6". This is the **only official statement about a change**. What is meant is apparently the firmware line **16.06** (as opposed to 16.04), not specifically 06.11. A comparison 06.05 → 06.11 shows: the master polling functions (request, evaluation, snapshot, 0x5A response) are identical apart from shifted addresses. *(confirmed)* The rework 04.06 → 06.03, by contrast, affects large parts of the communication code (see [OEM changelog](../firmware/firmware-changelog.md)).
- **Procedure:**
  1. Disconnect the parallel connection, switch off the pack.
  2. Set DIP switch 1 to ON, then back to OFF (described this way).
  3. Switch on the pack. This must happen before the update, otherwise reading the pack capacity fails. *Presumably* this means the bootloader's package size: `FirmwareUpdate.exe` reports "Get package capacity fail" (.NET `#US` heap, file offset `0x8845`) when the first bootloader query `R F L` after the reset fails; the download sequence does not read the battery capacity from the app.
  4. In the "Firmware Update" tool, connect via a USB-RS485 adapter at **19200 baud**.
  5. Select the `.ehex`, "Download". In case of errors, press the reset button or repeat.
- The update guide and lab board use 19200 baud. The header alone does not establish the bootloader rate; no measurement binds it to the 04.06-9600 image.

## 10. Addressed updates and shared-bus conditions

With no bootloader command, the first application reply was observed approximately 4.8 s after reset on the laboratory board. This startup observation is separate from the 0.65–0.8 s bootloader entry deadline; it is not a universal timing guarantee.

- **Entry by software:** ASCII 0x45 type 6 (watchdog reset, `0x0A22`) is enough; the DIP sequence from the guide is not needed. VER and INFO byte 0 do not matter (`~20004645A006000600FC6E` and the updater's variant `~26004645A006010600FC67` behave the same).
- **Parameters were kept in the measured update:** the parameter block (0x47) was byte-identical afterwards, and the flash records from `0x25000` were unchanged. This is laboratory evidence for the tested update, not proof of an unknown bootloader’s behavior on every board.
- **Master, slave or single pack makes no difference:** only the address in the reset command matters (the pack's own DIP address; `FF` would reset every pack and must be avoided). Tested with address 0 (no slaves) and address 1 (slave configuration). A changed DIP address is taken over by the running application without a restart (cyclic read in `0x2112`). **Exception: a master with configured slaves (DIP 5–8 ≠ 0).** It polls and does not call the UART0 dispatcher (`0x6264–0x628A`), so it ignores 0x45 as well *(measured: after the command the polls continued at the 1 s pace without a gap)*. For this pack, stop polling first. DIP 5–8 OFF does this only when automatic addressing is disabled and the effective slave count becomes 0; see [intra-pack mode selection](intra-pack.md#taking-the-master-off-the-bus-during-operation-dip-58-to-0).
- **Other packs on the same bus** (application 16.06.13, master silent): they do not answer the bootloader traffic. Random frames starting at a `0x7E` inside the data are discarded without a reply at the latest at the length check (`0xF90`); computed for all 7 vendor images *(confirmed for this code; not yet measured on a real multi-pack bus)*. Never have more than one pack in the bootloader **at the same time** (no reset to `FF`, no second reset while an update is running). Sequential addressed updates follow the measured single-board sequence: after `W F G` the tested pack starts its application, and likewise if no `R F L` arrives within ≈ 0.7 s after reset. A complete shared-bus update sequence has not been electrically validated.
