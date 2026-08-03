\version "2.24.4"

\header { title = "Piano Piece" composer = "Composer" }

global = { \key c \major \time 4/4 \tempo 4 = 88 }

rightHand = \relative c' {
  \global
  c4 e g c |
  b2 g |
}

leftHand = \relative c {
  \global
  \clef bass
  c2 <g' c e> |
  g,2 <g' b d> |
}

\score {
  \new PianoStaff \with { instrumentName = "Piano" } <<
    \new Staff = "right" \rightHand
    \new Staff = "left" \leftHand
  >>
  \layout { }
  \midi { }
}
