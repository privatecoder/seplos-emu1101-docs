# Regression metadata fixtures

Patcher regression tests read the JSON files in this directory through `corpus.fixture`. Each file must match its byte count and SHA-256 in [registry.json](registry.json). Missing metadata and integrity failures raise explicit errors. Historical build reports are provenance records; current tests never open them.

- [oem-16.06.13-facts.json](oem-16.06.13-facts.json) contains the consumed static function, RAM, hook, power/RTC and APP identity facts for the named OEM image. The selected fields are identical in the four source reports. Hook evidence retains opcode checks; the oracle contains only the OEM major/minor version. Guard proof arrays, emulator response dumps, generated assembly, payload entries, timestamps and absolute paths are excluded. Builders rediscover version-specific marker, cutoff, service and hard-stop roles from the actual OEM APP.
- [supported-recovery-oems.json](supported-recovery-oems.json) contains the three supported OEM names, source hashes, charge-path facts and expected recovery counters needed by configurable hard-stop discovery. These are OEM code facts, with no battery or installation captures.

The two current metadata fixtures are OEM code facts; current-profile identities come from public release metadata. Historical profile hash fixtures remain in the preserved source snapshot.

The registry records the original project-relative report names, complete source sizes and SHA-256 values, and selected fields. Those report files remain under ignored `local/`; their availability does not affect fixture loading. To change a fixture, verify its named OEM input and the relevant source-derived discovery/build behavior, review the selected data, update the fixture and registry hash together, and rerun the regressions and release verifier.

## Binary prerequisites

[corpus.json](../../corpus.json) is the authoritative list of all 16 required binary inputs, with exact filenames, sizes and SHA-256 values. The seven OEM images remain under `vendor/firmware`; historical regression images remain under `local/fixtures/corpus`; the access-control regression image remains under `local/releases`. Current release EHEX files also remain under `local/releases`. No firmware binary belongs in this metadata directory.

`corpus.corpus_groups()` checks every named input and rejects missing or changed files. Extra EHEX files do not extend the regression corpus. The normal test suite exercises the OEM images and the historical images as explicit compatibility/refusal inputs. Missing inputs are prerequisites to restore, never a reason to skip tests.

## Release identity verification

Run from any working directory with the patcher's configured Python environment:

```sh
export SEPLOS_PROJECT='/absolute/path/to/Seplos V2 10E BMS'
export SEPLOS_PYTHON="$HOME/.local/share/seplos-oem-patcher/venv/bin/python"
cd /private/tmp
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PROJECT/mod/firmware/patcher/verify_releases.py" --out /private/tmp/seplos-identities-new
"$SEPLOS_PYTHON" -I -B "$SEPLOS_PROJECT/mod/firmware/patcher/verify_releases.py" --rebuild --out /private/tmp/seplos-rebuild-new
```

Both commands use the two current JSON files under `mod/firmware/releases` as identity authorities and require the pinned OEM source and exact release EHEX files. The first checks existing EHEX/APP hashes, APP extent, MNT template, version, flags and build ID. The second additionally reconstructs each profile through the real CLI worker, including its mandatory emulator suite, checks identical EHEX bytes, and publishes the worker evidence into the fresh output directory. Metadata-only verification does not execute emulator tests. No existing output directory is overwritten.

The MNT APP template reserves two zero bytes for OEM major/minor. Its handler fills those bytes when answering INFO=03. Verification checks the template and reconstructs those two bytes from the pinned OEM version facts before comparing `info_hex`.

`--metadata-dir` selects reviewed metadata for either supported current profile. Retired profile versions are rejected. A metadata `build_report` locator is never followed. `--images` and `--source` accept explicit input locations; the source must still match the reviewed OEM digest. All generated artifacts belong in a fresh local or temporary directory, never alongside immutable fixtures.
