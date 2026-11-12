\version "2.24.4"

music = {
  \time 6/8
  R1*3/4 |
  <>\! R1*3/4 |
}

#(ly:message "EXPECTED 3/2; ACTUAL ~a" (ly:music-length music))
\score { \new Staff { \music \barNumberCheck #3 } }
