\version "2.24.4"

\header { title = "Orchestral Score" composer = "Composer" }
global = { \key c \major \time 4/4 \tempo 4 = 112 }
fluteMusic = \relative c'' { \global c4 d e f | g2 g | }
clarinetMusic = \relative c'' { \global \transposition bes d4 e fis g | a2 a | }
hornMusic = \relative c' { \global \transposition f g4 a b c | d2 d | }
violinIMusic = \relative c'' { \global c4 d e f | g2 g | }
violaMusic = \relative c' { \global \clef alto e4 f g a | b2 b | }
celloMusic = \relative c { \global \clef bass c4 e g c | g2 g | }

\score {
  <<
    \new StaffGroup = "Woodwinds" <<
      \new Staff \with { instrumentName = "Flute" } \fluteMusic
      \new Staff \with { instrumentName = "Clarinet in Bb" } \clarinetMusic
    >>
    \new StaffGroup = "Brass" <<
      \new Staff \with { instrumentName = "Horn in F" } \hornMusic
    >>
    \new StaffGroup = "Strings" <<
      \new Staff \with { instrumentName = "Violin I" } \violinIMusic
      \new Staff \with { instrumentName = "Viola" } \violaMusic
      \new Staff \with { instrumentName = "Cello" } \celloMusic
    >>
  >>
  \layout { }
  \midi { }
}
