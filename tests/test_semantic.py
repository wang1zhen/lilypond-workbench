from pathlib import Path
from fractions import Fraction

from lilypond_workbench.semantic import build_semantic_index


def test_indexes_relative_music_across_include_and_transpose(tmp_path: Path) -> None:
    included = tmp_path / "music.ily"
    included.write_text(
        r'''global = { \time 3/4 }
celloMusic = \relative c { \global \clef bass c4 d e | \transpose c d { f g a } | }
''',
        encoding="utf-8",
    )
    source = tmp_path / "score.ly"
    source.write_text(
        '\\version "2.24.4"\n\\include "music.ily"\n\\score { \\new Staff \\celloMusic }\n',
        encoding="utf-8",
    )

    index = build_semantic_index(source, "celloMusic")

    assert index.duration == 3 / 2
    assert [event.pitches for event in index.events] == [(21,), (22,), (23,), (25,), (26,), (27,)]
    assert [measure.meter for measure in index.measures] == [3 / 4, 3 / 4]
    assert {event.source.file for event in index.events} == {str(included)}


def test_fingerprint_invalidates_when_an_include_changes(tmp_path: Path) -> None:
    included = tmp_path / "music.ily"
    included.write_text(r"music = \absolute { c'1 }", encoding="utf-8")
    source = tmp_path / "score.ly"
    source.write_text('\\include "music.ily"\n', encoding="utf-8")
    first = build_semantic_index(source, "music")

    included.write_text(r"music = \absolute { d'1 }", encoding="utf-8")
    second = build_semantic_index(source, "music")

    assert first.fingerprint != second.fingerprint
    assert first.events[0].pitches != second.events[0].pitches


def test_marks_cue_during_music_for_exclusion(tmp_path: Path) -> None:
    source = tmp_path / "cue.ly"
    source.write_text(
        r"""music = \absolute {
  \time 4/4
  c'1 |
  \cueDuring "violin" #UP { c'''4 d''' e''' f''' } |
}
""",
        encoding="utf-8",
    )

    index = build_semantic_index(source, "music")

    assert [event.cue for event in index.events] == [False, True, True, True, True]


def test_indexes_simultaneous_chords_tuplets_repeats_and_ignores_grace(tmp_path: Path) -> None:
    source = tmp_path / "structures.ly"
    source.write_text(
        r"""music = \absolute {
  \time 4/4
  << { <c' e'>2 \tuplet 3/2 { d'4 e' f' } } \\ { g2 a } >> |
  \repeat unfold 2 { c'1 | }
  \grace { c''''16 } d'1 |
  \mark \default
}
""",
        encoding="utf-8",
    )

    index = build_semantic_index(source, "music")

    assert index.duration == 4
    assert index.events[0].kind == "chord"
    assert index.events[0].pitches == (28, 30)
    assert [event.duration for event in index.events if event.offset < 1] == [
        Fraction(1, 2),
        Fraction(1, 6),
        Fraction(1, 6),
        Fraction(1, 6),
        Fraction(1, 2),
        Fraction(1, 2),
    ]
    assert all(49 not in event.pitches for event in index.events)
    assert any(marker.kind == "seam" and marker.value == "rehearsal" for marker in index.markers)
