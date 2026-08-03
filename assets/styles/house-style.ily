% Shared publishing defaults for LilyPond 2.24.4.
\paper {
  tagline = ##f
}

\layout {
  \context {
    \Score
    \override BarNumber.break-visibility = ##(#f #f #t)
  }
}
