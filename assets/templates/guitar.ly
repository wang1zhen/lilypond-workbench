\version "2.24.4"

\header { title = "Guitar Piece" composer = "Composer" }
global = { \key c \major \time 4/4 }

guitarMusic = \relative c' {
  \global
  \clef "treble_8"
  c4 d e f |
  g2 g |
}

\score {
  <<
    \new Staff \with { instrumentName = "Guitar" midiInstrument = "acoustic guitar (nylon)" } \guitarMusic
    \new TabStaff \with { instrumentName = "Tab" } \guitarMusic
  >>
  \layout { }
  \midi { }
}
