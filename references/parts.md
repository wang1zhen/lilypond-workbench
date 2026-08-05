# Score-to-parts workflow

Keep shared music variables outside top-level `\score`, `\book`, and `\bookpart` blocks. Generate a manifest:

```bash
uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/workbench.py" \
  parts-manifest score.ly --output parts.yaml
```

New manifests use schema v2:

```yaml
schema_version: 2
source: score.ly
source_mode: strip-score-blocks
output_dir: build/parts
parts:
  - id: violin-i
    name: Violin I
    instrument: violin
    variable: violinIMusic
    staff_type: Staff
    clef:
      initial: treble
      policy: suggest
    transpose: {from: c, to: d}
    tags: [violin-i]
```

Clef policy is `preserve`, `suggest`, or `auto`. `suggest` writes a
`PART_ID.clefs.json` report without changing the part. `auto` also creates a
skip-based clef track for violin, viola, or cello and combines it with the
shared music in the generated wrapper. It never edits the score source.
Explicit source clefs remain authoritative. Schema v1 remains readable and is
treated as `preserve` so existing output does not change.

Review every `needs_review` entry and clef report. Fix names, instruments,
initial clefs, transpositions, MIDI instruments, and tag selection before
extraction.

Run `extract-parts parts.yaml --compile`. The tool creates `_shared.ily`, one
wrapper per part, clef reports for supported policies, and optional PDFs
without copying music variables into divergent sources. If required variables
exist only inside a book/score block, refactor them to top level first; the
tool stops rather than generating incomplete parts.
