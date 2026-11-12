"""Regressions for static structure/duration checks against real LilyPond input."""

from __future__ import annotations

from pathlib import Path

import pytest

from lilypond_workbench.linting import _structural_diagnostics
from lilypond_workbench.rendering import validate_file
from lilypond_workbench.syntax import check_measure_durations


def _codes(diagnostics: list) -> set[str]:
    return {item.code for item in diagnostics}


def _duration_codes(source: str) -> set[str]:
    return _codes(check_measure_durations(source))


# --- structural diagnostics -------------------------------------------------


def test_direct_score_without_variable_is_not_a_missing_music_error(tmp_path: Path) -> None:
    source = tmp_path / "example.ly"
    source.write_text(
        r"""\version "2.24.4"
\score { \new Staff \relative c' { \time 4/4 c1 } \layout { } }
""",
        encoding="utf-8",
    )
    assert "STRUCTURE_NO_MUSIC_VARIABLE" not in _codes(_structural_diagnostics(source))


def test_include_only_entrypoint_is_not_a_missing_music_error(tmp_path: Path) -> None:
    (tmp_path / "music.ily").write_text("music = { c1 }\n", encoding="utf-8")
    source = tmp_path / "entry.ly"
    source.write_text(
        r"""\version "2.24.4"
\include "music.ily"
""",
        encoding="utf-8",
    )
    diagnostics = _structural_diagnostics(source)
    assert "STRUCTURE_NO_MUSIC_VARIABLE" not in _codes(diagnostics)
    assert not [item for item in diagnostics if item.code == "STRUCTURE_INCLUDE_NOT_FOUND"]


def test_commented_or_quoted_include_is_not_a_music_entrypoint(tmp_path: Path) -> None:
    source = tmp_path / "empty.ly"
    source.write_text(
        '% \\include "commented.ily"\n"\\include \\"quoted.ily\\""\n',
        encoding="utf-8",
    )
    diagnostics = _structural_diagnostics(source)
    assert "STRUCTURE_NO_MUSIC_VARIABLE" in _codes(diagnostics)
    assert "STRUCTURE_INCLUDE_NOT_FOUND" not in _codes(diagnostics)


def test_truly_empty_entrypoint_still_warns_about_missing_music(tmp_path: Path) -> None:
    source = tmp_path / "empty.ly"
    source.write_text("% nothing here\n", encoding="utf-8")
    assert "STRUCTURE_NO_MUSIC_VARIABLE" in _codes(_structural_diagnostics(source))


# --- duration counting ------------------------------------------------------


def test_relative_and_fixed_anchors_are_not_counted_as_notes() -> None:
    body = " ".join(["c4"] * 48)
    for wrapper in ("\\relative c'", "\\fixed c'"):
        source = f"{wrapper} {{ \\time 4/4 {body} }}"
        assert "FINAL_BAR_DURATION" not in _duration_codes(source)


def test_transpose_pitch_arguments_are_not_counted_as_notes() -> None:
    source = "music = \\absolute { \\time 4/4 \\transpose c d { c1 } }"
    assert not _duration_codes(source)


def test_complete_bars_without_barlines_do_not_warn() -> None:
    body = " ".join(["c4"] * 48)
    source = f"music = \\absolute {{ \\time 4/4 {body} }}"
    assert "FINAL_BAR_DURATION" not in _duration_codes(source)


def test_real_incomplete_remainder_still_warns() -> None:
    issues = check_measure_durations("music = \\absolute { \\time 4/4 c'2 d'2 c'1 c'2 }")
    final = [item for item in issues if item.code == "FINAL_BAR_DURATION"]
    assert final and final[0].details["actual"] == "1/2"


def test_explicit_barlines_across_complete_bars_do_not_warn() -> None:
    source = "music = \\absolute { \\time 4/4 c1 | d1 | e1 | }"
    assert not _duration_codes(source)


def test_barline_after_multiple_complete_bars_does_not_warn() -> None:
    source = "music = \\relative c' { \\time 4/4 c1 c1 | d1 | }"
    assert not _duration_codes(source)


def test_pickup_plus_complete_bars_before_barline_does_not_warn() -> None:
    source = "music = \\absolute { \\time 4/4 \\partial 4 c4 c1 c1 | d1 | }"
    assert not _duration_codes(source)


def test_final_segment_with_pickup_and_complete_bar_does_not_warn() -> None:
    source = "music = \\absolute { \\time 4/4 \\partial 4 c4 c1 }"
    assert "FINAL_BAR_DURATION" not in _duration_codes(source)


def test_final_segment_with_pickup_still_warns_on_real_remainder() -> None:
    issues = check_measure_durations("music = \\absolute { \\time 4/4 \\partial 4 c4 c2 }")
    final = [item for item in issues if item.code == "FINAL_BAR_DURATION"]
    assert final and final[0].details["actual"] == "1/2"


def test_barline_still_warns_when_segment_has_a_remainder() -> None:
    issues = check_measure_durations("music = \\absolute { \\time 4/4 c1 c2 | d1 | }")
    bar = [item for item in issues if item.code == "BAR_DURATION"]
    assert bar and bar[0].details["remainder"] == "1/2"


def test_commented_notes_do_not_affect_duration() -> None:
    source = "music = \\absolute { \\time 4/4 c1 % d1\n \"e1\" }"
    assert "FINAL_BAR_DURATION" not in _duration_codes(source)


def test_include_defers_duration_checks_to_the_compiler() -> None:
    issues = check_measure_durations('\\include "meter.ily"\nmusic = { c4 }\n')
    assert [item.code for item in issues] == ["DURATION_PARTIAL_ANALYSIS"]
    assert "compiler validation" in issues[0].message


def test_free_meter_defers_duration_checks_to_the_compiler() -> None:
    issues = check_measure_durations("music = \\absolute { \\cadenzaOn c4 d e f }")
    assert [item.code for item in issues] == ["DURATION_PARTIAL_ANALYSIS"]
    assert "cadenzaOn" in issues[0].message


# --- real compiler comparison ----------------------------------------------


@pytest.mark.integration
def test_relative_anchor_source_compiles_without_false_bar_warning(tmp_path: Path) -> None:
    body = " ".join(["c4"] * 48)
    source = tmp_path / "complete.ly"
    source.write_text(
        f'\\version "2.24.4"\n\\relative c\' {{ \\time 4/4 {body} }}\n',
        encoding="utf-8",
    )
    result = validate_file(source)
    assert result.metadata["exit_code"] == 0
    assert not _codes(result.diagnostics) & {"BAR_DURATION", "FINAL_BAR_DURATION"}


@pytest.mark.integration
def test_multiple_complete_bars_before_barline_compile_without_false_bar_warning(tmp_path: Path) -> None:
    source = tmp_path / "collapsed.ly"
    source.write_text(
        "\\version \"2.24.4\"\n\\relative c' { \\time 4/4 c1 c1 | d1 | }\n",
        encoding="utf-8",
    )
    result = validate_file(source)
    assert result.metadata["exit_code"] == 0
    assert not _codes(result.diagnostics) & {"BAR_DURATION", "FINAL_BAR_DURATION"}


@pytest.mark.integration
def test_pickup_plus_complete_bar_without_barlines_compiles_without_false_warning(tmp_path: Path) -> None:
    source = tmp_path / "pickup.ly"
    source.write_text(
        "\\version \"2.24.4\"\n\\absolute { \\time 4/4 \\partial 4 c'4 c'1 }\n",
        encoding="utf-8",
    )
    result = validate_file(source)
    assert result.metadata["exit_code"] == 0
    assert not _codes(result.diagnostics) & {"BAR_DURATION", "FINAL_BAR_DURATION"}


@pytest.mark.integration
def test_real_cadenza_include_compiles_without_false_bar_warning(tmp_path: Path) -> None:
    (tmp_path / "cadenza.ily").write_text(
        "cadenzaMusic = \\relative c' { \\cadenzaOn c4 d e f g a b c \\cadenzaOff \\bar \"|\" }\n",
        encoding="utf-8",
    )
    source = tmp_path / "cadenza.ly"
    source.write_text(
        r"""\version "2.24.4"
\include "cadenza.ily"
\score { \new Staff \cadenzaMusic }
""",
        encoding="utf-8",
    )
    result = validate_file(source)
    assert result.metadata["exit_code"] == 0
    assert not _codes(result.diagnostics) & {"BAR_DURATION", "FINAL_BAR_DURATION"}
