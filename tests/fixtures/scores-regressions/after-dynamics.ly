\version "2.24.4"

music = {
  \time 6/8
  \after 8 -\> \after 1024*641 \! g'2. -\f |
}

#(ly:message "EXPECTED 3/4; ACTUAL ~a" (ly:music-length music))
\score { \new Staff { \music \barNumberCheck #2 } }
