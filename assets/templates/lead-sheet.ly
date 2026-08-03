\version "2.24.4"

\header { title = "Lead Sheet" composer = "Composer" }
global = { \key c \major \time 4/4 }
chordNames = \chordmode { c1 | g:7 | }
melody = \relative c' { \global c4 d e f | g2 g | }
verseOne = \lyricmode { Add -- ing lyr -- ics is easy __ }

\score {
  <<
    \new ChordNames { \set chordChanges = ##t \chordNames }
    \new Staff <<
      \new Voice = "melody" { \melody }
      \new Lyrics \lyricsto "melody" \verseOne
    >>
  >>
  \layout { }
  \midi { }
}
