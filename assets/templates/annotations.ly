\version "2.24.4"

\header { title = "Fingerings and Bowings" }
global = { \key c \major \time 4/4 }

annotatedMusic = \relative c' {
  \global
  % Two alternative fingering sets: upper and lower.
  c4^1_3( d^2_4 e^3_1 f^4_2) |
  g4\upbow( a b\downbow c~ |
  c1) |
}

\score {
  \new Staff \annotatedMusic
  \layout { }
  \midi { }
}
