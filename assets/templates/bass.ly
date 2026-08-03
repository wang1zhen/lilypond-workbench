\version "2.24.4"

\header { title = "Bass Piece" composer = "Composer" }
global = { \key c \major \time 4/4 }
bassMusic = \relative c { \global \clef "bass_8" c4 d e f | g2 g | }

\score {
  \new Staff \with { instrumentName = "Bass" midiInstrument = "electric bass (finger)" } \bassMusic
  \layout { }
  \midi { }
}
