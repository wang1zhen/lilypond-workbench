\version "2.24.4"

\header { title = "Drum Kit" composer = "Composer" }
global = { \time 4/4 }
drumMusic = \drummode { \global bd4 sn bd sn | hh8 hh hh hh sn4 r | }

\score {
  \new DrumStaff \with { instrumentName = "Drums" } \drumMusic
  \layout { }
  \midi { }
}
