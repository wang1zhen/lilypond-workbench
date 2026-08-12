# LilyPond Workbench

[中文说明](README_CN.md)

LilyPond Workbench is a Codex skill and a deterministic command-line toolkit
for creating, editing, diagnosing, analyzing, importing, engraving, and
publishing LilyPond scores. It combines an agent-facing workflow with local
tools that make repeatable operations—validation, conversion, part extraction,
harmonic analysis, and rendering—reliable and scriptable.

The project targets the locally installed LilyPond 2.24 series and is tested
with LilyPond 2.24.4. Its Python environment and dependencies are managed
exclusively by [uv](https://docs.astral.sh/uv/).

## What it can do

- Create `.ly` scores from natural-language musical instructions.
- Make semantic edits to existing LilyPond sources while preserving reusable
  variables, includes, comments, and project structure.
- Add lyrics, chord symbols, fingerings, multiple directed fingering systems,
  bowings, slurs, phrasing slurs, and ties.
- Diagnose LilyPond compilation failures and measure-duration problems.
- Import MusicXML, compressed MusicXML, MIDI, and ABC, then normalize the
  generated LilyPond source for further review.
- Extract independent parts from a shared full-score source using a versioned
  manifest.
- Semantically index written pitches across relative music, includes,
  transposition, tuplets, repeats, and simultaneous voices; recommend stable
  violin, viola, and cello clef changes and optionally apply them to parts.
- Infer chord symbols, local keys, inversions, and Roman numerals, with a JSON
  confidence report for human review.
- Render one score or batch-render a directory to PDF, PNG, SVG, or PostScript.
- Build LuaLaTeX documents containing LilyPond notation through
  `lilypond-book`.

Musical creation and judgment remain agent-driven. The CLI handles operations
that should be deterministic and verifiable.

## Requirements

| Requirement | Notes |
| --- | --- |
| Python 3.11 or newer | Selected by `.python-version` |
| uv | The only supported Python environment and dependency manager |
| LilyPond 2.24.x | Tested with 2.24.4 |
| `musicxml2ly`, `midi2ly`, `abc2ly`, `convert-ly` | Normally installed with LilyPond |
| `lilypond-book`, LuaLaTeX, `latexmk` | Required only for LaTeX document builds |

LilyPond must be installed by the operating system or another system-level
package manager; it is not a Python dependency.

## Setup

From the repository root:

```sh
uv sync --group dev
uv run python scripts/workbench.py doctor
```

`doctor` reports the versions of uv, LilyPond, its converters, and the optional
LaTeX toolchain. Missing optional tools are warnings; use `doctor --strict` to
require every import and publishing executable.

To make the repository discoverable from another project, place or symlink it
at `.agents/skills/lilypond-workbench` in that repository. For personal use
across repositories, use `~/.agents/skills/lilypond-workbench`.

The directory itself is the skill package; `SKILL.md` is its agent entry point.

## Using the skill

Ask Codex to use `$lilypond-workbench` and describe the musical result rather
than a sequence of LilyPond commands. For example:

```text
Use $lilypond-workbench to create a two-page violin étude in E minor,
add two alternative fingering systems above and below the staff,
validate the measures, and render a PDF.
```

```text
Use $lilypond-workbench to import this MusicXML file, clean the result,
infer chord symbols, and generate separate transposed parts.
```

```text
Use $lilypond-workbench to diagnose this LilyPond log and repair only the
source lines responsible for the compilation and bar-length errors.
```

The skill routes specialized work to the references under `references/` and
uses the CLI for reproducible checks and output generation.

## CLI quick start

All Python commands must run through uv:

```sh
uv run python scripts/workbench.py --help
```

Create and render a score from a bundled template:

```sh
uv run python scripts/workbench.py new piano my-score.ly
uv run python scripts/workbench.py validate my-score.ly
uv run python scripts/workbench.py lint my-score.ly --output my-score.lint.json
uv run python scripts/workbench.py render my-score.ly --output-dir build/score
```

Import and clean an interchange file:

```sh
uv run python scripts/workbench.py import-score input.musicxml \
  --output imported.ly
uv run python scripts/workbench.py clean imported.ly \
  --output imported-clean.ly
```

Batch-render scores concurrently:

```sh
uv run python scripts/workbench.py batch-render scores \
  --recursive --jobs 4 --output-dir build/scores
```

Generate independent parts:

```sh
uv run python scripts/workbench.py parts-manifest full-score.ly \
  --output parts.yaml
# Review names, clefs, transpositions, and any needs_review entries first.
uv run python scripts/workbench.py extract-parts parts.yaml --compile
```

Analyze a string part's clefs without modifying it:

```sh
uv run python scripts/workbench.py analyze-clefs full-score.ly \
  --instrument cello --variable celloMusic \
  --output cello.clefs.json
```

New parts manifests use schema v3 and declare `pitch_basis: concert|written`.
Leave `clef.policy` at `suggest` to produce
a source-located report, or set it to `auto` to add a generated clef track to
that part. Schema v1 and v2 remain readable and preserve their previous behavior.

Analyze harmony:

```sh
uv run python scripts/workbench.py analyze-harmony progression.ly \
  --key C --output harmony.ily --report harmony.analysis.json
```

Build a document containing notation:

```sh
uv run python scripts/workbench.py build-document article.lytex \
  --output-dir build/document
```

Add `--json` to any command that supports it when another program or agent step
will consume the result.

Every JSON command response uses a versioned envelope with `schema_version`,
`ok`, `command`, `inputs`, `artifacts`, `diagnostics`, and `metadata`. Exit 0
means success, exit 1 means the operation completed with failing findings or a
tool failure, exit 2 means invalid input/configuration or a missing required
tool, and exit 130 means interruption. `lint` reports have their own schema
version under `metadata.report` and in the optional report file.

## Command reference

| Command | Purpose |
| --- | --- |
| `doctor` | Check local executables and versions |
| `new` | Copy a bundled score template |
| `render` | Compile one `.ly` file |
| `batch-render` | Compile multiple scores, optionally in parallel |
| `validate` | Check durations and run a no-page LilyPond compile |
| `lint` | Check structure, ranges, clefs, transposition metadata, and part consistency |
| `parse-log` | Convert LilyPond output into structured diagnostics |
| `import-score` | Convert MusicXML, MIDI, or ABC to LilyPond |
| `clean` | Normalize LilyPond version and formatting |
| `parts-manifest` | Discover part candidates and create a reviewable manifest |
| `extract-parts` | Generate part wrappers from a reviewed manifest |
| `analyze-harmony` | Produce chord/Roman-numeral includes and an analysis report |
| `analyze-clefs` | Recommend violin, viola, or cello clef changes from a semantic index |
| `build-document` | Run `lilypond-book` and LuaLaTeX |

Run `uv run python scripts/workbench.py COMMAND --help` for all options.

## Bundled templates

`new` accepts these template names:

- `single-staff`, `piano`, `lead-sheet`, `satb`
- `string-quartet`, `orchestra`, `parts-project`
- `guitar`, `ukulele`, `bass`, `drum-kit`, `annotations`

Reusable house style lives in `assets/styles/house-style.ily`. The document
starter is `assets/documents/article.lytex`.

## Project layout

```text
.
├── SKILL.md                 # Concise instructions loaded by Codex
├── agents/openai.yaml       # Skill UI metadata
├── assets/                  # Score and document templates
├── references/              # Task-specific agent guidance
├── scripts/
│   ├── workbench.py         # CLI entry point
│   └── lilypond_workbench/  # Deterministic implementation
├── tests/                   # Unit and toolchain integration tests
└── evals/evals.json         # Realistic skill evaluation prompts
```

## Development

Use uv for every dependency change and every Python invocation:

```sh
uv add PACKAGE
uv remove PACKAGE
uv add --dev PACKAGE
uv run pytest
```

Do not edit dependency lists in `pyproject.toml` or `uv.lock` by hand. Do not
invoke `python`, `pytest`, or project scripts outside `uv run`.

Run only the fast tests when the system toolchain is unavailable:

```sh
uv run pytest -m "not integration"
```

Run the complete integration surface on a machine with LilyPond and the LaTeX
requirements installed:

```sh
uv run pytest
```

Run the seven executable skill evaluations with:

```sh
uv run python scripts/run_evals.py
```

For untrusted LilyPond input, build the isolated runner and keep generated
outputs outside the source directory:

```sh
docker build -t localhost/lilypond-workbench:2.24.4 -f containers/Dockerfile .
uv run python scripts/workbench.py --runner container render score.ly \
  --output-dir /tmp/lilypond-output
```

The full suite compiles every bundled score template and exercises imports,
batch rendering, error detection, part extraction, harmonic analysis, and
LaTeX document generation.

## Important behavior and limitations

- Converter output is always a draft. MusicXML layout, MIDI quantization and
  enharmonic spelling, and ABC dialect details require musical review.
- Harmonic analysis targets common-practice, pop, and jazz harmony in
  12-tone equal temperament. Low-confidence events are omitted from the
  LilyPond include and retained in JSON for review.
- Part extraction deliberately stops when the shared source cannot be isolated
  safely; review the manifest before compiling parts.
- Automatic clef tracks never edit the score source. Existing explicit clefs
  are preserved, and reports should be reviewed before publication.
- LilyPond input can contain Guile/Scheme and must be treated as executable
  code. Compile untrusted sources only in an appropriately isolated environment.
- `--force` and `--in-place` overwrite files. Confirm the intended target
  before using either option.
