# Import and cleanup

Use `import-score` for `.xml`, `.musicxml`, `.mxl`, `.mid`, `.midi`, and `.abc`. The command calls the converter shipped with LilyPond 2.24.4, updates the version, and runs `python-ly` formatting.

MusicXML defaults discard exact page layout, explicit stem directions, and imported beaming so LilyPond can engrave cleanly. Pass `--preserve-layout` or `--preserve-beams` when those details are intentional.

MIDI defaults quantize note starts to sixteenth notes and durations to thirty-second notes. Inspect live-performance MIDI closely; it lacks enharmonic spelling and may create excessive voices, rests, and tuplets.

ABC conversion preserves musical structure supported by `abc2ly`, but dialect-specific fields may require manual repair.

After every import:

1. Inspect key/meter/tempo, voice separation, tuplets, ties, repeats, lyrics, and accidentals.
2. Rename generated variables semantically and move shared settings into `global`.
3. Remove redundant layout boilerplate only after visual comparison.
4. Run `validate`, repair diagnostics, and render PDF.
