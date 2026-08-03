# Harmonic analysis

Run `analyze-harmony` on MusicXML, MIDI, or LilyPond. For `.ly`, select the intended score with `--score-index`; the tool creates a temporary analysis source and MIDI without retaining the temporary file.

The default pipeline performs measure-aware chord reduction, uses a four-measure local-key window, retains at most three chords per measure, and computes chord symbols, inversions, local keys, and Roman numerals. Use `--key C` or `--key a` when the analytical key is known.

Outputs:

- `harmony.ily` defines `workbenchChordNames`, `workbenchRomanRhythm`, and `workbenchRomanNumerals`.
- `harmony.analysis.json` records source positions, local key, symbols, inversion, confidence, and alternatives.

Low-confidence events become skips in the include and remain candidates in JSON. Review them before adding:

```lilypond
\include "harmony.ily"
\new ChordNames \workbenchChordNames
\new Staff <<
  \new Voice = "music" \melody
  \new NullVoice = "analysis" \workbenchRomanRhythm
  \new Lyrics \lyricsto "analysis" \workbenchRomanNumerals
>>
```

Treat MIDI spelling, chromatic passing tones, pedal tones, polychords, modal music, microtones, and post-tonal material as review-sensitive. The v1 analyzer targets common-practice, pop, and jazz harmony in 12-tone equal temperament.
