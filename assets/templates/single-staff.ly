\version "2.24.4"

\header {
  title = "Untitled"
  composer = "Composer"
}

global = {
  \key c \major
  \time 4/4
  \tempo 4 = 96
}

melody = \relative c' {
  \global
  c4 d e f |
  g2 g |
}

\score {
  \new Staff \with { midiInstrument = "violin" } \melody
  \layout { }
  \midi { }
}
