"""Regressions from the 2026-11-11 scores run: empty chords and \\after timing."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.comparison import diff_scores
from lilypond_workbench.semantic import build_semantic_index


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "tests" / "fixtures" / "scores-regressions"


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def dynamics(index) -> dict[str, Fraction]:
    return {marker.value: marker.offset for marker in index.markers if marker.kind == "dynamic"}


def codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


def test_empty_chord_has_no_duration_and_keeps_its_dynamic_in_measure_two() -> None:
    index = build_semantic_index(CASE / "empty-chord.ly", "music")

    assert index.duration == Fraction(3, 2)
    assert [(item.start, item.end, item.complete) for item in index.measures] == [
        (Fraction(0), Fraction(3, 4), True),
        (Fraction(3, 4), Fraction(3, 2), True),
    ]
    assert [(item.kind, item.offset, item.duration) for item in index.events] == [
        ("rest", Fraction(0), Fraction(3, 4)),
        ("rest", Fraction(3, 4), Fraction(3, 4)),
    ]
    assert dynamics(index) == {"!": Fraction(3, 4)}
    assert index.diagnostics == ()


def test_after_delays_controls_without_advancing_the_main_note() -> None:
    index = build_semantic_index(CASE / "after-dynamics.ly", "music")

    assert index.duration == Fraction(3, 4)
    assert [(item.start, item.end, item.complete) for item in index.measures] == [
        (Fraction(0), Fraction(3, 4), True)
    ]
    assert [(item.kind, item.offset, item.duration, item.pitches) for item in index.events] == [
        ("note", Fraction(0), Fraction(3, 4), (32,))
    ]
    assert dynamics(index) == {
        "f": Fraction(0),
        ">": Fraction(1, 8),
        "!": Fraction(641, 1024),
    }
    assert index.diagnostics == ()


def test_empty_chord_with_an_explicit_duration_still_takes_no_time(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "explicit.ly",
        "music = \\absolute { \\time 4/4 c'4 <>4 d'4 }\n",
    )

    index = build_semantic_index(source, "music")

    assert index.duration == Fraction(1, 2)
    assert [(item.offset, item.duration) for item in index.events] == [
        (Fraction(0), Fraction(1, 4)),
        (Fraction(1, 4), Fraction(1, 4)),
    ]


def test_direction_dynamic_is_recorded_at_its_note_onset(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "postfix-dynamic.ly",
        "music = \\absolute { \\time 4/4 c'4-\\f d'4-\\> }\n",
    )

    index = build_semantic_index(source, "music")

    assert dynamics(index) == {"f": Fraction(0), ">": Fraction(1, 4)}


def test_after_delay_scales_inside_a_tuplet(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tuplet-after.ly",
        "music = \\absolute { \\time 4/4 \\tuplet 3/2 { \\after 8 \\f c'4 } }\n",
    )

    index = build_semantic_index(source, "music")

    assert dynamics(index) == {"f": Fraction(1, 12)}
    assert [(item.offset, item.duration) for item in index.events] == [
        (Fraction(0), Fraction(1, 6))
    ]


def test_after_articulation_control_is_delayed(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "after-articulation.ly",
        "music = \\absolute { \\time 4/4 \\after 8 \\fermata g'2. }\n",
    )

    index = build_semantic_index(source, "music")

    assert [(item.kind, item.value, item.offset) for item in index.markers if item.kind == "articulation"] == [
        ("articulation", "fermata", Fraction(1, 8))
    ]
    assert index.duration == Fraction(3, 4)


@pytest.mark.parametrize(
    ("music", "code"),
    [
        ("\\after 8", "AFTER_SHAPE"),
        ("\\after 8 \\f", "AFTER_SHAPE"),
        ("\\after #1/8 \\f g'2.", "AFTER_DURATION_UNSUPPORTED"),
        ("\\after 8 c'8 g'2.", "AFTER_CONTROL_UNSUPPORTED"),
        ("\\after 8 -\\markup { x } g'2.", "AFTER_CONTROL_UNSUPPORTED"),
        ("<< \\after 8 \\f c'4 d'4 >>", "AFTER_CONTROL_UNSUPPORTED"),
    ],
)
def test_unsupported_after_shapes_are_rejected(tmp_path: Path, music: str, code: str) -> None:
    source = write(tmp_path, "after-bad.ly", f"music = \\absolute {{ \\time 4/4 {music} }}\n")

    with pytest.raises(WorkbenchError) as raised:
        build_semantic_index(source, "music")

    assert raised.value.code == code
    assert raised.value.exit_code == 2


def test_after_inside_a_simultaneous_voice_still_delays_its_control(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "simultaneous-after.ly",
        "music = \\absolute { \\time 4/4 << { \\after 8 \\f c'4 } { d'4 } >> }\n",
    )

    index = build_semantic_index(source, "music")

    assert dynamics(index) == {"f": Fraction(1, 8)}
    assert index.duration == Fraction(1, 4)


def test_empty_chord_diff_gate_locates_a_dynamic_change_in_measure_two(tmp_path: Path) -> None:
    old = CASE / "empty-chord.ly"
    new = write(
        tmp_path,
        "empty-chord.ly",
        old.read_text(encoding="utf-8").replace("<>\\!", "<>\\p"),
    )

    accepted = diff_scores(old, new, variable="music", expect_measures="2")
    rejected = diff_scores(old, new, variable="music", expect_measures="1")

    assert accepted.ok
    assert accepted.metadata["report"]["summary"]["changed_measures"] == [2]
    assert "DIFF_OUTSIDE_EXPECTED" in codes(rejected)


def test_after_diff_gate_locates_a_control_change_in_measure_one(tmp_path: Path) -> None:
    old = CASE / "after-dynamics.ly"
    new = write(
        tmp_path,
        "after-dynamics.ly",
        old.read_text(encoding="utf-8").replace("\\after 8 -\\>", "\\after 8 -\\f"),
    )

    accepted = diff_scores(old, new, variable="music", expect_measures="1")
    rejected = diff_scores(old, new, variable="music", expect_measures="2")

    assert accepted.ok
    assert accepted.metadata["report"]["summary"]["changed_measures"] == [1]
    assert "DIFF_OUTSIDE_EXPECTED" in codes(rejected)
