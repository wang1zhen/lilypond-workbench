# Score workflows

## Create from natural language

1. Resolve instrumentation, transposition, key, meter, tempo, pickup, form, approximate length, lyrics, chord-symbol, MIDI, and page needs from the request. Ask only for missing choices that materially change the music.
2. Choose the closest file under `assets/templates/`; use `new` to copy it.
3. Keep shared timing/key/tempo in `global` and musical lines in named variables. Keep concert-pitch sources when parts require multiple transpositions.
4. Check playable ranges and idiomatic registers. LilyPond validates syntax, not playability.
5. Add `\layout { }`; add `\midi { }` when playback or harmonic analysis is useful.
6. Validate and render, then inspect all compiler warnings.

## Edit an existing score

Identify the exact voice, variable, and measure. Preserve includes and comments. Avoid flattening reusable blocks or manually rewriting every pitch when `\transpose` is suitable. Compile after each coherent edit.

## Lyrics and chord names

Attach lyrics to a named voice with `\lyricsto`. Use `--` for syllable splits, `__` for melismas, `_` for a skipped syllable, and separate variables for verses.

Put harmonic content in `\chordmode` and display it with `\new ChordNames`. Use `\set chordChanges = ##t` when repeated symbols should be suppressed.

## Imported notation

Treat converter output as a draft. Review voices, enharmonic spelling, ties, beams, tuplets, repeats, alternatives, lyrics, cue notes, breaks, and layout before publishing.
