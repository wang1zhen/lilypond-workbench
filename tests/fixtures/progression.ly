\version "2.24.4"

progression = \relative c' {
  \time 4/4
  <c e g>1 |
  <f a c>1 |
  <g b d f>1 |
  <c e g>1 |
}

\score {
  \new Staff \progression
  \layout { }
  \midi { }
}
