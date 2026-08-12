---
name: lilypond-workbench
description: Create, edit, debug, semantically analyze, import, clean, extract parts from, compile, batch-render, and publish LilyPond 2.24 scores and LilyPond-enabled LaTeX documents. Use whenever Codex works with .ly/.ily files, music engraving, natural-language score creation, compilation errors, lyrics, chord symbols or harmonic analysis, instrument ranges or clef changes, fingerings, bowings, slurs, ties, MusicXML/MIDI/ABC conversion, score-to-part extraction, PDF output, measure-duration validation, LilyPond logs, or .lytex documents containing music.
---

# LilyPond Workbench

Use natural-language musical judgment for composition and semantic edits. Use the bundled CLI for deterministic conversion, validation, extraction, analysis, and rendering.

## Core workflow

1. Inspect all relevant `.ly`, `.ily`, manifest, and style files before editing. Locate `\version`, includes, reusable variables, headers, paper/layout blocks, books/scores, voices, lyrics, chords, and MIDI blocks.
2. Preserve variable boundaries, comments, pitch language, relative/absolute style, instrumentation, and local formatting. Make the smallest semantic edit that satisfies the request.
3. Target LilyPond 2.24.4. Prefer ordinary LilyPond syntax over Scheme and shared variables over copied music.
4. Run Python only through uv. Set `SKILL_DIR` to the directory containing this file, then invoke:
   ```bash
   uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/workbench.py" <command>
   ```
5. Run `lint` after every modification. Repair fatal diagnostics first, then review warnings. Render the requested PDF or other artifacts again so outputs are never stale.
6. Report changed source files, generated artifacts, unresolved musical choices, and any warnings that remain.

Run `doctor` before the first tool-assisted task in an unfamiliar environment. Treat LilyPond input as executable because embedded Guile/Scheme can run during compilation; compile untrusted input only in an appropriately isolated environment.

## Task routing

- Create or edit scores, add lyrics/chords, transpose, or repair engraving: read [references/workflows.md](references/workflows.md).
- Choose playable registers, clefs, transpositions, or idiomatic instrumental writing: read [references/instruments.md](references/instruments.md), then use `analyze-clefs` for violin, viola, or cello parts.
- Add one or more fingering systems, bowings, slurs, phrasing slurs, or ties: read [references/annotations.md](references/annotations.md).
- Apply context settings, grob overrides, custom engravers, or Scheme: read [references/engraving.md](references/engraving.md).
- Audit score structure, ranges, transposition metadata, clefs, or part consistency: read [references/linting.md](references/linting.md), then use `lint`.
- Diagnose compiler errors or measure lengths: read [references/diagnostics.md](references/diagnostics.md), then use `validate` or `parse-log`.
- Import or clean MusicXML, MIDI, or ABC: read [references/imports.md](references/imports.md), then use `import-score` and perform semantic review.
- Generate independent parts: read [references/parts.md](references/parts.md), then use `parts-manifest` and `extract-parts`.
- Infer chord symbols, local keys, and Roman numerals: read [references/harmony.md](references/harmony.md), then use `analyze-harmony` and review low-confidence omissions.
- Build a LaTeX document containing notation: read [references/latex.md](references/latex.md), then use the bundled `.lytex` template and `build-document`.

## CLI map

- `new TEMPLATE OUTPUT`: copy a bundled starting score.
- `render FILE`: compile one score; add `--output-dir`, `--format`, or `--json` as needed.
- `batch-render PATH... --output-dir DIR`: compile multiple scores with optional recursion and concurrency.
- `validate FILE`: run static duration checks and a no-page LilyPond validation compile.
- `lint FILE [--manifest parts.yaml]`: create a source-located semantic quality report.
- `parse-log [LOG]`: convert LilyPond output into structured diagnostics.
- `import-score INPUT --output SCORE.ly`: convert and mechanically clean supported interchange formats.
- `clean FILE`: normalize version and formatting without overwriting by default.
- `parts-manifest SOURCE --output parts.yaml`: discover part candidates.
- `extract-parts parts.yaml --compile`: generate and render wrappers from shared definitions.
- `analyze-harmony INPUT --output harmony.ily`: generate chord names, Roman numerals, and JSON analysis.
- `analyze-clefs INPUT --instrument INSTRUMENT --variable MUSIC --output clefs.json`: index written pitches and recommend stable string-part clef changes.
- `build-document FILE.lytex --output-dir build/document`: run lilypond-book and LuaLaTeX.

Prefer `--json` when another tool or agent step will consume results. Never use `--force` or `--in-place` without confirming the target is the intended file.

For untrusted LilyPond input, build `containers/Dockerfile` and place global
`--runner container` before the command. Container rendering requires an output
directory outside the read-only source directory. Stop if no container runtime
or reviewed container image is available.
