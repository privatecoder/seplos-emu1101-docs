# SOC emulator fixtures

The current patcher executes native Cortex-M0 instructions with synthetic RAM, GPIO and storage inputs to verify SOC storage diagnostics and planned-reset behavior. These models provide software evidence for the exact selected image; they are not hardware SOC setters.

## Current image and fixture scope

Light 1.5.3 and later provide read-only storage diagnostics. Full 1.6.3 and later additionally verify SOC saving before targeted planned reset. Light 1.5.4 and later and Full 1.6.4 and later expose persisted capacity contents and full-width live energy. The [storage/reset contract](../firmware/storage-and-reset.md) and [remote diagnostics](../firmware/remote-diagnostics.md) define these separate capabilities.

The maintained [storage diagnostic tests](../../firmware/patcher/seplos/storage_diagnostics_tests.py), [service tests](../../firmware/patcher/seplos/service_tests.py) and [remote diagnostic tests](../../firmware/patcher/seplos/remote_diagnostics_tests.py) construct explicit records and failure states. Native serializers, loaders, CRC routines and guarded hooks execute where covered. Expected record shape and native CRC acceptance remain separate checks. Full-profile cases include checkpoint failures, interrupted mirror writes and boot restore; read-only cases check that querying storage does not repair or save it.

Use the [build and validation procedure](../firmware/build-and-validation.md) with the selected profile and pinned input. Preserve the exact application SHA, build report, resolved source and fixture bindings with results. The [fixture registry](../../firmware/patcher/tests/fixtures/registry.json) and [binary corpus](../../firmware/patcher/corpus.json) define maintained dependencies; a historical report or another image cannot replace them.

## Reuse and extension

For new scenarios, state units and initial conditions, execute native routines in firmware order, and verify intended transitions and unaffected state. Keep image, profile, source and test hashes with results. Resolve new code/RAM contracts and create a separately bound profile before applying expectations to a new image. Never remove identity guards to admit an unknown image.

Historical research profiles are not distributed and require their complete source/dependency arrangement, exact inputs and reviewed reports. Their scope does not extend to current releases. The [historical test runner](../../tools/run_historical_tests.py) lists retained prerequisites and explicit suites.

Synthetic counter/GPIO state establishes software decisions rather than electrical isolation or actual current. Modeled IAP/storage does not establish physical flash interruption behavior, ISR latency, bootloader behavior or multi-pack sharing. See [validation limits](../firmware/validation-methods-and-limits.md).
