# Engraving, contexts, and Scheme

Prefer semantic notation and LilyPond's automatic engraving. Add manual
controls only after compiling and inspecting the actual collision or ambiguity.

## Intervention order

Use the least invasive level that solves the problem:

1. Correct the musical semantics: voice, duration, articulation, tie, slur, or
   context.
2. Set a context property with `\set`.
3. Adjust page or score policy in `\paper` or `\layout`.
4. Apply a local `\once \override`.
5. Use a scoped persistent `\override`, followed by `\revert`.
6. Add or remove an engraver.
7. Use Scheme or a custom music function only when ordinary syntax is
   insufficient.

Keep repeated project-wide decisions in a shared `.ily` style file instead of
copying offsets into every score.

## Contexts and grobs

Common contexts include `Score`, `Staff`, `Voice`, `Lyrics`, `ChordNames`,
`PianoStaff`, `StaffGroup`, and `ChoirStaff`. Most note-level graphical objects
belong to a `Voice`; staff names, clefs, and many line-level settings belong to
a `Staff`.

```lilypond
\set Staff.instrumentName = "Violin I"
\set Staff.midiInstrument = "violin"

\once \override TextScript.extra-offset = #'(0 . 1)
c'4^\markup \italic "solo"

\override Staff.TimeSignature.style = #'numbered
% ... scoped music ...
\revert Staff.TimeSignature.style
```

An override in the wrong context may compile but have no effect. Scope global
overrides tightly, and prefer `\once` for a single event.

To change engravers, place the change in the relevant layout context:

```lilypond
\layout {
  \context {
    \Staff
    \remove "Time_signature_engraver"
  }
}
```

## Frequent notation traps

- Attach dynamics and hairpins to rhythmic events: use `c4\p`, `c4\<`, and
  `d4\!`; do not leave a dynamic command without an attachment point.
- Make the final measure match the active meter. A fermata does not make a
  four-beat whole note valid in `3/4`.
- Use `~` only between the same written pitch. Use `( ... )` for ordinary slurs
  and `\( ... \)` for phrasing slurs. Do not nest two active slurs of the same
  type in one voice.
- Remember that omitted durations inherit the previous duration and `|` checks
  a bar boundary rather than creating missing time.
- In relative mode, inspect octave inference after large leaps, chords, voice
  changes, and copied passages. Use explicit apostrophes/commas or switch a
  register-sensitive block to `\absolute`.
- Consolidate repeated `extra-offset`, padding, and direction tweaks only after
  confirming that a semantic or context-level fix cannot solve the layout.

## Scheme and music functions

LilyPond embeds Guile. Treat every `#(...)`, `#'symbol`, and custom music
function as executable code. Do not compile untrusted Scheme outside an
appropriately isolated environment.

Use Scheme sparingly and comment why normal LilyPond syntax was insufficient:

```lilypond
repeatTwice =
#(define-music-function (music) (ly:music?)
   #{ \repeat unfold 2 $music #})
```

Avoid OS-interacting forms such as `#(system ...)` in shared scores. When a
Scheme error occurs, check parentheses, quoting, expected argument types, and
the LilyPond/Guile API version before changing unrelated music.
