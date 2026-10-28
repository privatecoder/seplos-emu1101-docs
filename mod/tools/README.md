# Tools

Reusable offline analysis and device tooling. [Tool changes](CHANGELOG.md) records tooling and test-boundary updates; firmware release history stays in `mod/firmware/CHANGELOG.md`.

- [Knowledge library](../docs/tools/knowledge-library.md): exact firmware identity, retained topic/evidence lookup, build outcomes and input/model freshness.
- [Firmware analysis](firmware-analysis/README.md): image inspection, native firmware probes, emulation and the current capability renderer.
- [Device tools](device/README.md): explicit device commands, flash/recovery codecs, parameter/identity clients and offline mocked regressions.

Source and input paths derive from [_paths.py](_paths.py), independently of the
working directory. Vendor images remain in `vendor/firmware`; generated releases,
historical fixtures, reports and captures remain under ignored `local/`.
No binary links are needed inside `mod/`. Native research probes resolve the reviewed reports through [research-inputs.json](research-inputs.json); `_paths.research_input()` rejects missing or changed input bytes before emulation. This registry does not replace the mandatory patch tests.

Use Python 3.11 or newer with `-I -B`, normally from `/private/tmp`.
The established patcher environment location is `~/.local/share/seplos-oem-patcher/venv`;
device wrappers use `~/.local/share/seplos-firmware-tools/venv`, which requires
pyserial 3.5 and Unicorn 2.1.4.
Unicorn 2.1.4 and LLVM are required by native probes and legacy firmware tests;
basic protocol framing, JSON/Markdown output and current device mocked tests use
the standard library. Serial transports using `import serial` require pyserial
3.5; no dependency is installed automatically by these commands.

## Public documentation checks

[check_markdown.py](check_markdown.py) validates relative Markdown file/directory targets and heading anchors against Git-visible files. Ignored private files cannot satisfy a public link. Only regular files are eligible; symlinks are excluded so they cannot borrow private targets. Fenced and inline-code examples are skipped. By default it includes tracked files and non-ignored new files in the working tree; `--index-only` restricts eligibility to index paths. It reads worktree content in both modes. External URLs are counted without a network request.

```sh
python3 -I -B "$PROJECT/mod/tools/check_markdown.py"
python3 -I -B "$PROJECT/mod/tools/check_markdown.py" --index-only
```

`PROJECT` is the checkout root; `--project DIR` selects another checkout. Run the default check while editing and the index-path check after adding the intended files to Git. Private evidence references in public documents use plain text marked as unpublished.

## Historical regression workspace

The current tools and extracted metadata stay in `mod/`. The complete frozen source/dependency arrangement remains under ignored `local/history/snapshots/mod-before-current-cleanup-2026-10-26/project`. [run_historical_tests.py](run_historical_tests.py) verifies that workspace against its source inventory and executes only explicitly selected suites. Running it without arguments lists prerequisites without executing tests. See the [device guide](device/README.md#historical-builders-and-laboratory-work) for commands. Generated output belongs in a new temporary directory or under `local/`.
