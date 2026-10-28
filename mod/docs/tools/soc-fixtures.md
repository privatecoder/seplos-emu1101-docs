# SOC emulator fixtures

The SOC tools execute original Cortex-M0 instructions with synthetic RAM, GPIO and storage inputs. `soc_profile_v16.py` supplies named functions, RAM fields, units and invariants; `probe_soc.py` and `probe_soc_cutoffs.py` exercise the counter and cutoff paths. The profile is research/test support, not a hardware SOC setter.

## Image and dependency scope

The profile binds OEM16.06.13 and the historical MAINT1.6 build `18daf61d8a93671d`. It verifies image hashes, build identity, selected unchanged code ranges and RAM bindings. That scope does not automatically extend to every MAINT1.6 image or to1.6.3. The current firmware's behavior and planned-reset extension are described in [SOC analysis](../../../analysis/firmware/soc-capacity-and-persistence.md) and [storage/reset](../firmware/storage-and-reset.md).

Inputs include the OEM image, the fixed historical release and its preserved report under ignored `local/`. These are intentional version-bound research fixtures; they are separate from the maintained patcher unit-test fixture boundary. Required historical inputs must remain available. The profile refuses a different image rather than silently applying known addresses.

Use the external patcher interpreter with Unicorn 2.1.4 and LLVM. Native execution needs a process that permits Unicorn JIT; no device or network connection is used. From a neutral directory:

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
export SEPLOS_PYTHON="$HOME/.local/share/seplos-oem-patcher/venv/bin/python"
cd /private/tmp
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PROJECT/mod/tools/firmware-analysis/probe_soc.py" \
  --out /private/tmp/soc-counter-new.json
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PROJECT/mod/tools/firmware-analysis/probe_soc_cutoffs.py" \
  --out /private/tmp/soc-cutoff-new.json
```

Output files must be new. Keep new reports under ignored `local/research/soc/evidence/<date-topic>/` or `local/builds/runs/<date-topic>/`.

## Reuse the fixture API

Load the profile by absolute path with `importlib`, which also works under Python `-I`:

```python
import importlib.util
import os
from pathlib import Path

path = Path(os.environ['SEPLOS_PROJECT']) / 'mod/tools/firmware-analysis/soc_profile_v16.py'
spec = importlib.util.spec_from_file_location('soc_fixture', path)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

loaded = profile.load_images()
board = profile.new_board(loaded, 'MAINT1.6')
profile.seed_soc(board, 44)  # Synthetic 4.4%, in tenths of a percent.
profile.run(board, 'soc_update')
profile.run(board, 'soc_alarms')
profile.run(board, 'discharge')
result = profile.read_state(board)
assert not result['discharge_permitted']
```

`new_board` creates a synthetic 16S state and starts from documented test values. These are not universal defaults or values to upload to a real pack. `seed_soc(board, tenths, full=28000)` seeds the counter consistently; `full` is in 0.01 Ah. It does not implement a new counting rule. `write(board, name, value, width, signed=False)` writes another named synthetic RAM field. Names and bit masks are in `RAM`, `FUNCTIONS`, `BITS` and `PROFILE`.

`run` calls the actual mapped firmware routine. `read_state` returns tenths/whole-percent SOC, event bytes, discharge/precharge permission, GPIO state and SOC flags. Permission/GPIO results establish software decisions, not electrical isolation or actual battery current.

## Extending coverage

For a new scenario, state the units and initial conditions explicitly, execute the relevant native routines in firmware order, and assert both the intended transition and relevant unaffected state. Record image, profile and test hashes with the result. Distinguish voltage-rule eligibility, hold timers, whole-percent rounding, charge counter units and learned/rated capacity.

For a new firmware image, resolve functions and RAM fields first, compare code/data contracts, and introduce a separately bound profile before running expectations. Do not remove hash checks to make an unknown image load. Preserve the original profile for reproducible historical cases.

IAP acceptance/storage and GPIO registers are modeled. These fixtures do not establish flash power-failure behavior, ISR latency, electrical gates, bootloader behavior or multi-pack current sharing. Use the [validation methods and limits](../firmware/validation-methods-and-limits.md) with the separate historical image/version qualifications.
