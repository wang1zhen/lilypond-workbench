# LilyPond Workbench

[中文说明](README_CN.md)

A Codex skill and local CLI for LilyPond scores: create and edit music, import
files, check changes, extract parts, analyze harmony, and render or publish.
The agent handles musical judgment; the CLI handles repeatable checks and builds.

## Quick start

Requires **Python 3.11+**, [uv](https://docs.astral.sh/uv/), and system-installed
**LilyPond 2.24.x** (tested with 2.24.4). LilyPond's converters are needed for
imports; `lilypond-book`, LuaLaTeX, and `latexmk` are optional publishing tools.

From the repository root, run all Python commands through uv:

```sh
uv sync --group dev
uv run python scripts/workbench.py doctor
uv run python scripts/workbench.py new piano my-score.ly
uv run python scripts/workbench.py validate my-score.ly
uv run python scripts/workbench.py lint my-score.ly --output my-score.lint.json
uv run python scripts/workbench.py render my-score.ly --output-dir build/score
```

`doctor` reports available tools; `doctor --strict` requires every import and
publishing executable. Use `COMMAND --help` for options.

## Use as a skill

Place or symlink this repository at `.agents/skills/lilypond-workbench` in a
project, or `~/.agents/skills/lilypond-workbench` for personal use. The repository
itself is the skill package; [SKILL.md](SKILL.md) is its entry point.

Describe the musical result to Codex:

> Use $lilypond-workbench to create a violin étude in E minor, add two alternative
> fingering systems, validate the measures, and render a PDF.

## Commands

Run `uv run python scripts/workbench.py COMMAND`:

| Command | Purpose |
| --- | --- |
| `doctor` | Check tools and versions |
| `new` | Create a score from a template |
| `render` | Compile one score to PDF, PNG, SVG, or PostScript |
| `batch-render` | Compile multiple scores, optionally in parallel |
| `validate` | Check durations and compile without pages |
| `lint` | Check structure, ranges, clefs, and part consistency |
| `parse-log` | Turn compiler logs into structured diagnostics |
| `import-score` | Import MusicXML/MXL, MIDI, or ABC |
| `clean` | Normalize version and formatting |
| `parts-manifest` | Discover parts and write a reviewable manifest |
| `extract-parts` | Generate part wrappers and optional PDFs |
| `analyze-harmony` | Infer chords, keys, and Roman numerals with confidence reports |
| `analyze-clefs` | Recommend violin, viola, or cello clef changes |
| `index` | Report one music variable's semantic index |
| `diff` | Compare musical content and locate changes |
| `build-document` | Publish notation with lilypond-book and LuaLaTeX |

### Common workflows

Import and clean:

```sh
uv run python scripts/workbench.py import-score input.musicxml --output imported.ly
uv run python scripts/workbench.py clean imported.ly --output imported-clean.ly
```

Generate parts, reviewing names, transpositions, and `needs_review` entries first:

```sh
uv run python scripts/workbench.py parts-manifest full-score.ly --output parts.yaml
uv run python scripts/workbench.py extract-parts parts.yaml --compile
```

Check an edit's scope:

```sh
uv run python scripts/workbench.py diff before.ly after.ly \
  --variable violinMusic --expect-measures 37-40 --output changes.json
```

`diff` ignores formatting and comments. Use `--fail-on-change` to require no
musical changes, or `--new-variable` after renaming a variable. Moved events and
markers are checked against both their old and new measures.

Add `--json` for automation. Responses contain `schema_version`, `ok`, `command`,
`inputs`, `artifacts`, `diagnostics`, and `metadata`.
Exit codes: **0** success; **1** findings/tool failure; **2** invalid input,
configuration, or missing tool; **130** interruption.

## Safety and limits

**LilyPond sources can execute Guile/Scheme. Do not compile untrusted files
directly on the host.** For supported commands, build the isolated runner and
keep output outside the source directory:

```sh
docker build -t localhost/lilypond-workbench:2.24.4 -f containers/Dockerfile .
uv run python scripts/workbench.py --runner container render score.ly \
  --output-dir /tmp/lilypond-output
```

- The image is **Linux amd64 only**. ARM hosts need amd64 emulation and
  `docker build --platform linux/amd64`. Overriding `LILYPOND_VERSION` also requires
  the verified `LILYPOND_SHA256`; downloads are checked before extraction.
- Container mode supports only `render`, `batch-render`, `validate`, `lint`, and
  `analyze-harmony`. It is not a sandbox for every CLI command.
- `--force` and `--in-place` overwrite files. Review targets before using them.
- Imports are drafts. Harmony analysis targets common-practice, pop, and jazz in
  12-tone equal temperament; low-confidence chords stay in JSON, not the generated
  include. `--score-index` selects only non-nested scores declared in the input
  file; ambiguous MIDI output is rejected.
- Parts need review before compilation. Manifests use schema v3 (v1/v2 remain
  readable), with `source` relative to the manifest. IDs and `output_name` must be
  safe filenames; IDs must be unique and `_shared` is reserved. Invalid range or
  transpose settings are configuration errors, not suppressible findings.
- Static duration checks defer includes and `\cadenzaOn` to compiler validation.
  A successful static check alone does not prove that a score is correct.
- `index` and `diff` inspect **one variable at a time**, using written pitches.
  Transposed accidentals are not respelled. A `\repeat` directly after `\tempo`
  triggers a parser-limit warning. Literal-duration `\after` dynamics/articulations
  and default `\afterGrace` are supported; other `\after` forms, explicit
  afterGrace fractions, and `afterGraceFraction` overrides are rejected.
- Clef recommendations never edit the source; explicit clefs remain authoritative.

## Guides and templates

Task guides: [comparison](references/comparison.md), [diagnostics](references/diagnostics.md),
[imports](references/imports.md), [parts](references/parts.md),
[clefs and ranges](references/instruments.md), [harmony](references/harmony.md),
[annotations](references/annotations.md), [engraving](references/engraving.md),
[linting](references/linting.md), and [LaTeX](references/latex.md).

Templates for `new`: `single-staff`, `piano`, `lead-sheet`, `satb`,
`string-quartet`, `orchestra`, `parts-project`, `guitar`, `ukulele`, `bass`,
`drum-kit`, and `annotations`. House style: `assets/styles/house-style.ily`;
document starter: `assets/documents/article.lytex`.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Use `uv add`, `uv remove`, or `uv add --dev`
for dependency changes; do not hand-edit dependency lists or `uv.lock`.

```sh
uv run pytest -m "not integration"          # Fast tests; no system toolchain needed
uv run pytest                               # Full suite; LilyPond + LaTeX required
uv run python scripts/validate_skill.py .
uv run python scripts/run_evals.py           # All eight regression scenarios
uv run python scripts/run_evals.py --id 8    # Timing/diagnostic regressions
```

Evals run mapped pytest tests, **not agent prompts**. Passing them does not verify
every stated task goal, page count, playability, or agent editing quality.

Project map: `scripts/lilypond_workbench/` contains the CLI implementation,
`tests/` holds tests and fixtures, `evals/evals.json` maps regression scenarios,
and `references/` holds task-specific guidance.
