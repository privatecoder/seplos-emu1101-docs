# Synwit SWM181: MCU reference documents

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

These are the MCU references for Seplos BMS 2.0 (EMU1101, hardware V16). The
firmware container's vendor header names the chip `SWM181RCT6_64_M0`. The
retained files were acquired on 2026-11-12. They define the register names in
[startup, clock and timers](../../../analysis/firmware/startup-clock-timers.md).

| File | Source | SHA-256 |
|---|---|---|
| `SWM181_V2.07_official.pdf`: SWM181 reference manual V2.07, 225 pages | <https://www.synwit.cn/uploads/soft/20220722/1-220H21TRIJ.pdf> (download page <https://www.synwit.cn/wendang334/>) | `cc77cd795b4d2af2cd64fbfd14c89abfb741f54ac3c29de23444fca256055d7f` |
| `SWM181_Lib_06e1694.zip`: SDK from GitHub, state of commit `06e1694bb1a8c670ca444a7874544ab37f5663c6`, without git history (663 files) | GitHub archive download <https://codeload.github.com/Synwit-Co-Ltd/SWM181_Lib/zip/06e1694bb1a8c670ca444a7874544ab37f5663c6> from <https://github.com/Synwit-Co-Ltd/SWM181_Lib>; downloaded by the P2 analyst with `curl` | `81901e8f82475a19e0d37c032ea92cdea0ebf36807139462d8ec182c3673dda9` |
| `SWM181_Lib_synwit-bb694f6.zip`: SDK from the manufacturer website, a git clone with history (`.git`, 2016 files). Local `main` is at `bb694f69314985ec81958864c9fd1676a5dcee82` ("make SDADC cali_fast work"); `origin/main` is at `a8310e74863a443314b5eefb446d220bb862dd6c` | Synwit download page <https://www.synwit.cn/wendang334/>, original file name `1-250PG51514448.zip`, downloaded by the user on 2026-11-12 | `95adb2828852886bed7195b3d40f2f5c430f5360f3687db5181d9cd716767ac2` |
| `ARM_DUI0497A_Cortex-M0_r0p0_Generic_User_Guide.pdf`: Arm Cortex-M0 (r0p0) Generic User Guide, 140 pages | <https://documentation-service.arm.com/static/5ea6ce5e9931941038def8c1> | `416e6a43e9fc0bc231211c3e8c3741da7a3c589836465c3419e80f69d2c587f9` |

## The two SDK versions

Both archives contain the same SDK at different versions. Of the 663 files they share,
626 are identical. 37 differ: mostly Keil/IAR project files and examples, plus `SWM181.h`
(access attributes of some GPIO interrupt registers, a `CTSCR` union),
`system_SWM181.c` (delay helpers) and `SWM181_gpio.c` (helper functions). **All 45
base-address definitions in `SWM181.h` are identical**, including:

- GPIOB `APB_BASE + 0x02000` = 0x50002000
- TIMR0 `APB_BASE + 0x07000` = 0x50007000
- WDT `APB_BASE + 0x09000` = 0x50009000
- IRQMUX `AHB_BASE + 0x5000000` = 0x45000000

Both versions have the `LDVAL` and `FEED` registers. The reviewed base-address,
IRQ-routing, timer and watchdog definitions agree in both snapshots; this is
not a claim that every peripheral field is identical. The paths below refer to
commit 06e1694. They also exist in the Synwit archive, below `SWM181_Lib/`.

## Places in the SDK (commit 06e1694) used for the firmware analysis

- Register map and base addresses (GPIOB DATA/DIR, TIMR, IRQMUX, WDT): `SWM181_StdPeriph_Driver/CSL/CMSIS/DeviceSupport/SWM181.h`
- Clock / SystemCoreClock: `…/DeviceSupport/system_SWM181.c`
- Vector table: `…/DeviceSupport/startup/arm/startup_SWM181.s`
- Timer load value, no −1: `SWM181_StdPeriph_Driver/CSL/SWM181_StdPeriph_Driver/SWM181_timr.c` (line 44)
- IRQ multiplexer: the same driver directory, `SWM181_irqmux.c/.h`
- Watchdog (FEED at offset 0x10, value 0x55): the same driver directory, `SWM181_wdt.c/.h`
- UART structure, integer divider and receive timeout: the same driver directory, `SWM181_uart.c/.h`
- CAN configuration, filters and bit timing: the same driver directory, `SWM181_can.c/.h`

## Places in the manual

- p. 36: clock tree
- p. 87: timer timing (one zero-count state between reloads)
- p. 97: watchdog timing
- pp. 49–53: IRQMUX sources/routing
- pp. 104–109: UART receive timeout, baud divider and register details
- pp. 176–183: CAN mode, filters, command/status fields and bit timing

## Source discrepancies

The reference manual and SDK must be checked against the actual image rather
than treated as interchangeable register specifications:

- Both SDK watchdog drivers halve the requested reset period when writing LOAD;
  manual p.97 figure 6-16 depicts one LOAD countdown before reset. This leaves
  the physical reset timeout unresolved by static inspection alone.
- RSTSR is at SYSCON+0x308 (`0x40000308`) in both SDKs and manual p.40. Page 45
  instead prints `0x50000308` and WDT cause bit 1; the SDK defines bit 3.
- Both SDKs and detailed manual p.109 put UART CFG at offset `0x18`, whereas the
  p.105 summary prints `0x14`. The older header reserves `0x14`; the newer one
  defines flow-control fields there.
- The p.36 ADC-clock prose repeats CLKSEL bit 3 = 0 for both branches; its
  diagram and the SDK distinguish internal 0 from external 1.

The source comparison, selected original SDK members and rendered watchdog
figure are retained under `local/research/swm181-source-review-20261112/`.
These discrepancies are not evidence that any particular board has a hardware
fault or that a software workaround is required.
