# Fingerings and bowings

## Fingerings

Use normal finger events such as `c4-1`. Force direction with `^` or `_` when placement matters. Two alternative systems can share one note, for example `c4^1_3 d^2_4`; keep the upper system consistently above and the lower system consistently below.

For chords, attach fingers to individual chord pitches, for example `<c-1 e-3 g-5>4`. Use `\set fingeringOrientations` only when chord fingering collisions require it. Add comments naming each alternative fingering system and compile a dense passage to check collisions.

## String bowing and curves

- Add `\upbow` and `\downbow` to the affected rhythmic events.
- Use `( ... )` for ordinary slurs within one voice.
- Use `\( ... \)` for longer phrasing slurs that must overlap ordinary slurs.
- Use `~` only for ties joining the same written pitch.
- Start and end a slur in the same voice. Label genuinely overlapping slurs rather than creating invalid nesting.

Prefer semantic bowing marks before manual control points or offsets. Use `\slurUp`, `\slurDown`, `\tieUp`, or `\tieDown` only when automatic placement is unclear.

Use `assets/templates/annotations.ly` as a compiled example.
