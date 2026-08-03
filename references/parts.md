# Score-to-parts workflow

Keep shared music variables outside top-level `\score`, `\book`, and `\bookpart` blocks. Generate a manifest:

```bash
uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/workbench.py" \
  parts-manifest score.ly --output parts.yaml
```

The schema is versioned:

```yaml
schema_version: 1
source: score.ly
source_mode: strip-score-blocks
output_dir: build/parts
parts:
  - id: violin-i
    name: Violin I
    variable: violinIMusic
    staff_type: Staff
    clef: treble
    transpose: {from: c, to: d}
    tags: [violin-i]
```

Review every `needs_review` entry. Fix names, clefs, transpositions, MIDI instruments, and tag selection before extraction.

Run `extract-parts parts.yaml --compile`. The tool creates `_shared.ily`, one wrapper per part, and optional PDFs without copying music variables into divergent sources. If required variables exist only inside a book/score block, refactor them to top level first; the tool stops rather than generating incomplete parts.
