# Instrument ranges and writing checks

LilyPond validates notation, not playability. Check requested ranges against the
performer level, instrument variant, transposition, clef, and musical context
before writing. Treat the following as practical defaults rather than absolute
limits.

## Common practical ranges

| Instrument | Written range | Writing notes |
| --- | --- | --- |
| Violin | G3–D7 | E7 is possible; avoid sustained extreme-high writing unless requested. |
| Viola | C3–E6 | Use alto clef, changing to treble for extended high passages. |
| Cello | C2–C6 | Use bass clef, then tenor or treble where ledger lines become excessive. |
| Double bass | E2–G5 written | Sounds one octave lower; some instruments have a low-C extension. |
| Flute | C4–C7 | The low octave is soft; C6 and above becomes increasingly brilliant. |
| Oboe | B-flat3–A6 | The lowest notes are strong and exposed; the extreme top is specialized. |
| B-flat clarinet | E3–C7 written | Sounds a major second lower; distinguish written from concert pitch. |
| Bassoon | B-flat1–E5 | Primarily bass and tenor clefs; high writing requires an advanced player. |
| B-flat trumpet | F-sharp3–C6 written | Sounds a major second lower; prolonged high writing is tiring. |
| Horn in F | F-sharp2–C6 written | Sounds a perfect fifth lower; secure range depends strongly on the player. |
| Trombone | E2–F5 | Usually bass clef; tenor clef is useful in sustained high passages. |
| Piano | A0–C8 | Check hand span, voice leading, pedaling, and balance rather than range alone. |

For transposing instruments, decide whether source variables contain concert
or written pitch before editing. Prefer concert-pitch shared variables and
explicit `\transpose` in part wrappers when the project produces both score
and parts.

## String checks

- Do not write below the lowest open string unless a scordatura or extension is
  explicitly part of the instrument setup.
- Select clef changes for readability, not merely because one isolated note has
  ledger lines. Avoid rapid or ambiguous clef changes.
- Distinguish a slur from a requested bow. A long slur can imply one bow in
  string notation, so confirm whether it is phrasing or bow division.
- Check double stops and chords for reachable strings, hand frame, and shifts;
  engraving vertically aligned pitches does not prove they are playable.
- Treat harmonics, sul ponticello, col legno, and other techniques as semantic
  notation that may also need explanatory text.

### Violin, viola, and cello clefs

Analyze written pitch with middle C named C4. Prefer a stable clef over reducing
the ledger lines of one or two notes. Change only at a bar line, a rest of at
least one beat, an explicit phrase boundary, or a rehearsal boundary. Require
the candidate register to last at least one full measure and contain at least
three pitched attacks, unless it lasts two full measures. Ignore grace and cue
music when selecting the main clef.

- Keep violin in treble clef. Preserve a nonstandard explicit clef but report
  it for review.
- Keep viola in alto clef. Enter treble when at least 70 percent of the
  duration-weighted passage is C5 or higher; return when at least 70 percent is
  B4 or lower.
- Keep cello in bass clef. Enter tenor when at least 70 percent is D4 or higher
  and return when at least 70 percent is C4 or lower. From tenor, enter treble
  when at least 70 percent is A4 or higher and return when at least 70 percent
  is G4 or lower. A sufficiently high passage may move directly from bass to
  treble.

Require an upward change to reduce average ledger-line cost by at least one.
Allow a return toward the home clef when it adds no more than half a ledger
line on average. These separate entry and return boundaries provide hysteresis
and prevent bar-by-bar flip-flopping. Interpret every cello treble clef at
modern written pitch; do not apply the historical octave-lower convention.

Use `analyze-clefs` to create a source-located JSON report. Keep the default
part policy at `suggest`; enable `auto` only after reviewing the report.

## Piano register and voicing

Avoid placing accompaniment block chords in the same register as a solo line.
As a default, put supporting close-position chords one or two octaves below a
violin-like melody, then adjust for texture and dynamics.

Close-position chords are clearest in the middle register. Below roughly C3,
spread low chord tones to avoid muddiness; above C5, sustained block chords can
sound thin or compete with a high melody. Check whether a chord fits one hand
or requires redistribution between staves.

For chord-heavy keyboard parts, prefer `\absolute` pitch or use explicit octave
marks. Relative pitch inference follows prior musical material and can move
repeated chord shapes into an unintended octave.

## Wind and brass checks

- Provide breathing opportunities appropriate to tempo, dynamics, and phrase
  length. A rest that is long enough on paper may not be sufficient after a
  demanding high or loud passage.
- Account for register changes in tone color and response, not only nominal
  range.
- Avoid treating all chromatic spellings as equivalent in transposed parts;
  readable written keys and conventional enharmonic spelling matter.
- Check mute changes and instrument doublings for enough transition time.

## Final review

Before rendering, verify lowest and highest notes, clefs, written versus
concert pitch, octave-transposing instruments, chord spans, breathing, and any
extended techniques. Report assumptions whenever performer level or instrument
variant materially affects playability.
