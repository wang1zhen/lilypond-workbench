from lilypond_workbench.syntax import (
    check_measure_durations,
    extract_music_variables,
    insert_midi_block,
    sanitize_definitions,
)


VALID = r'''\version "2.24.4"
global = { \time 4/4 }
melody = \relative c' {
  \time 4/4
  c4 d e f |
  \tuplet 3/2 { g4 a b } c2 |
}
\score { \new Staff \melody \layout { } }
'''


def test_extracts_variables_and_sanitizes_score() -> None:
    variables = extract_music_variables(VALID)
    assert [item.name for item in variables] == ["global", "melody"]
    shared = sanitize_definitions(VALID)
    assert "melody =" in shared
    assert "\\score" not in shared


def test_inserts_midi_only_once() -> None:
    inserted = insert_midi_block(VALID)
    assert inserted.count("\\midi") == 1
    assert insert_midi_block(inserted).count("\\midi") == 1


def test_duration_checker_accepts_valid_tuplet() -> None:
    issues = check_measure_durations(VALID)
    assert not [item for item in issues if item.code in {"BAR_DURATION", "FINAL_BAR_DURATION"}]


def test_duration_checker_finds_short_bar() -> None:
    source = r'''melody = \relative c' { \time 4/4 c4 d e | }'''
    issues = check_measure_durations(source)
    assert any(item.code == "BAR_DURATION" for item in issues)


def test_duration_checker_uses_global_meter() -> None:
    source = r'''global = { \time 3/4 }
melody = \relative c' { \global c4 d e | f2. | }'''
    issues = check_measure_durations(source)
    assert not [item for item in issues if item.code in {"BAR_DURATION", "FINAL_BAR_DURATION"}]


def test_duration_checker_ignores_transposition_pitch_and_defers_drums() -> None:
    pitched = r'''music = \relative c' { \time 4/4 \transposition bes d4 e fis g | }'''
    assert not [item for item in check_measure_durations(pitched) if item.code == "BAR_DURATION"]
    drums = r'''drums = \drummode { \time 4/4 bd4 sn bd sn | }'''
    issues = check_measure_durations(drums)
    assert any(item.code == "DURATION_PARTIAL_ANALYSIS" for item in issues)
    assert not any(item.code == "BAR_DURATION" for item in issues)
