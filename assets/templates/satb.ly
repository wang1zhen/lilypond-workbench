\version "2.24.4"

\header { title = "SATB Choir" composer = "Composer" }
global = { \key c \major \time 4/4 }
sopranoMusic = \relative c'' { \global c4 d e f | g2 g | }
altoMusic = \relative c' { \global e4 f g a | b2 b | }
tenorMusic = \relative c' { \global \clef "treble_8" g4 a b c | d2 d | }
bassMusic = \relative c { \global \clef bass c4 d e f | g2 g | }
verseOne = \lyricmode { Sing -- ing to -- geth -- er __ }

\score {
  \new ChoirStaff <<
    \new Staff \with { instrumentName = "Soprano" } <<
      \new Voice = "soprano" \sopranoMusic
      \new Lyrics \lyricsto "soprano" \verseOne
    >>
    \new Staff \with { instrumentName = "Alto" } \altoMusic
    \new Staff \with { instrumentName = "Tenor" } \tenorMusic
    \new Staff \with { instrumentName = "Bass" } \bassMusic
  >>
  \layout { }
  \midi { }
}
