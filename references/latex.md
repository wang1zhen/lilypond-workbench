# LaTeX documents with LilyPond

Copy `assets/documents/article.lytex`. Write notation inline with a `lilypond` environment or include a complete file with `\lilypondfile{score.ly}`.

Build with:

```bash
uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/workbench.py" \
  build-document article.lytex --output-dir build/document
```

The command runs `lilypond-book --pdf --latex-program=lualatex`, then `latexmk -lualatex`. Keep the source outside the build directory because `lilypond-book` must not overwrite its own input.

Use the `ctexart` template for Chinese and Unicode content. Keep document assets and included scores at stable paths relative to the `.lytex` source. Inspect both LilyPond and LaTeX logs when a build fails.
