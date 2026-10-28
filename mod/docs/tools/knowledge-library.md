# Offline knowledge library

The library connects exact firmware bytes to retained disassembly, build reports,
models, counterexamples and short topic notes. Use it before repeating an analysis.
Ignored `local/` contains the evidence; [`knowledge.py`](../../tools/knowledge.py)
and its tests are maintained source.

```sh
PROJECT='/path/to/Seplos V2 10E BMS'
KNOWLEDGE="$PROJECT/mod/tools/knowledge.py"
cd /private/tmp
python3 -I -B "$KNOWLEDGE" find soc
python3 -I -B "$KNOWLEDGE" topic soc
python3 -I -B "$KNOWLEDGE" identify '/path/to/firmware.ehex'
python3 -I -B "$KNOWLEDGE" builds
python3 -I -B "$KNOWLEDGE" builds --failures
python3 -I -B "$KNOWLEDGE" dependencies
python3 -I -B "$KNOWLEDGE" verify
```

The queries use Python 3.11 or newer and the standard library. `identify` imports
only the maintained strict EHEX parser. No query starts a native emulator,
disassembler or device connection. Commands work independently of the working
directory; `--project DIR` before the subcommand selects another complete library.
JSON output is suitable for scripts and for handing a small selection to an LLM.
`topic` requires an exact topic or decision ID; `find` searches recorded strings.

## Identity and reuse

`identify` reports both SHA256 digests:

- **File SHA256:** the complete EHEX container, including line endings/header.
- **Application SHA256:** the strict decoded application bytes used for model
  selection. A matching filename, version label or short digest is insufficient.

An exact container, a known application in a different container, and an unknown
application have distinct results. Current-release identity additionally binds
both digests to the public release JSON. Its `hardware_tested` and `flashed`
fields remain visible; a saved passing emulator report does not change them.

For a known application, inspect the matching topic/model scope and run `verify`
before reuse. For an unknown application, retain the original, then use the
[patcher analysis workflow](../firmware/build-and-validation.md) with a fresh output directory.
Transfer an address or RAM model only after its guards have been checked against
that image. Cached findings never replace mandatory patcher tests or release
verification.

## Locations and bindings

| Location | Contents |
|---|---|
| `local/index/images.json` | Strict EHEX identities, current release metadata bindings and decoded artifact pointers. |
| `local/index/topics.json` | Short topic summaries and source-bound decisions/counterexamples. |
| `local/index/builds.json` | Nine retained canonical bundles and individual recorded run outcomes. |
| `local/index/dependencies.json` | File/model SHA256/size bindings, logical research inputs and environment requirements. |
| `local/index/paths.json` | Migration lookup from original locators to canonical retained files. |
| `local/artifacts/firmware/<full-app-sha>/` | Exact decoded OEM application, ELF, disassembly and extraction binding. |
| `local/builds/oem*/maint-VERSION/BUILD-ID/` | Complete build reports, image, resolved payload and saved source/reproduction data. |
| `local/builds/runs/` | Supporting runs, including failures and corrective counterparts. |
| `local/research/` | Short English topic notes with evidence and tool pointers. |
| `local/history/` | Source-bound decisions, sessions, complete frozen snapshots and compatibility inputs. |

Build status comes from report fields, individual test results or explicit log
markers. Deliberate `refused` results stay distinct from test failures. A failing test overrides a declared passing report. `final` and `green`
filenames have no status meaning. Unclassified records remain unclassified;
log-marker results require checking their source/image binding. These are saved
results, rather than fresh emulator or electrical proof.

`verify` hashes the indexed inputs, models and parser sources, reports missing or
changed files, and rejects mixed index generations. It covers the explicit index
bindings. The [historical runner](../../tools/run_historical_tests.py) separately
checks the complete frozen source inventory; selected suite execution separately exercises its retained runtime inputs.

## Updating the library

After deliberately adding or changing canonical inputs, notes or tools:

```sh
python3 -I -B "$KNOWLEDGE" refresh
python3 -I -B "$KNOWLEDGE" verify
python3 -I -B "$PROJECT/mod/tools/test_knowledge.py"
```

`refresh` rebuilds only the four generated knowledge indexes. It never changes
firmware, evidence, source snapshots or the relocation map. It scans explicit
canonical roots and excludes the historical compatibility view; old inputs are
not recursively counted again. Each generated file is replaced atomically, and
shared generation tags reveal an interrupted multi-file update. Saved report/log
outcomes also include `local/history/sessions/*/reports/`; migration copies and
frozen source trees are excluded from that scan.

Keep conclusions in `local/research/<topic>/README.md` and source-bound decisions
in `local/history/decisions.json`. Additional manually curated entries in
`topics.json` belong in its `curated_topics` array, which refresh preserves.
The research-input registry in `mod/tools/research-inputs.json` pins the inputs
used by maintained probes; its expected digests are not rewritten by refresh.
If an input binding changes unexpectedly, investigate the cause before refreshing.

Exit codes: `0` successful query/verification; `1` no exact topic or recorded
verification/refresh problem; `2` invalid input, missing index or unreadable data.
An unknown but structurally valid EHEX is a successful identity query and is
explicitly marked `unknown-application`.

## Reusing decoded comparisons

The seven OEM artifact folders already contain decoded application bytes and disassembly. Select the exact application SHA returned by `identify`; verify its `binding.json` before reuse. The classic comparison tools expect names such as `v13.raw` and `v13.dis`. In a fresh comparison directory, create `v13.raw` as a symlink to the selected `app.bin` and `v13.dis` as a symlink to `app.dis`, then pass that directory through `--data-dir`. The label `13` is a local comparison key; the full hash in the binding identifies the actual image. This reuses the saved decoding without invoking LLVM again.

The [strict preparation recipe](../../tools/firmware-analysis/README.md#strict-comparison-input-preparation) produces a fresh bound extraction when the application is unknown or the existing extraction is unsuitable. The [capture verifier](../../tools/firmware-analysis/verify_intra_pack_fixtures.py) checks retained real 0x5A fixture framing and expectations offline.
