\version "2.24.4"

\header { title = "String Quartet" composer = "Composer" }
global = { \key c \major \time 4/4 }
violinIMusic = \relative c'' { \global c4 d e f | g2 g | }
violinIIMusic = \relative c'' { \global g4 a b c | d2 d | }
violaMusic = \relative c' { \global \clef alto e4 f g a | b2 b | }
celloMusic = \relative c { \global \clef bass c4 e g c | g2 g | }

\score {
  \new StaffGroup <<
    \new Staff \with { instrumentName = "Violin I" } \violinIMusic
    \new Staff \with { instrumentName = "Violin II" } \violinIIMusic
    \new Staff \with { instrumentName = "Viola" } \violaMusic
    \new Staff \with { instrumentName = "Cello" } \celloMusic
  >>
  \layout { }
  \midi { }
}
