"""\\afterGrace positioning and its unsupported static-index forms."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.comparison import diff_scores
from lilypond_workbench.semantic import build_semantic_index


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_default_after_grace_sits_three_quarters_into_the_main_note(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "after-grace.ly",
        "music = \\absolute { \\time 4/4 \\afterGrace c'1 { d'16 } e'1 }\n",
    )

    index = build_semantic_index(source, "music")

    assert [(event.kind, event.offset, event.duration, event.grace, event.pitches) for event in index.events] == [
        ("note", Fraction(0), Fraction(1), False, (28,)),
        ("note", Fraction(3, 4), Fraction(0), True, (29,)),
        ("note", Fraction(1), Fraction(1), False, (30,)),
    ]
    assert index.duration == 2
    assert index.position(Fraction(3, 4))["measure"] == 1
    assert index.measures[1].start == 1


def test_after_grace_diff_change_belongs_to_measure_one(tmp_path: Path) -> None:
    old = write(
        tmp_path,
        "old.ly",
        "music = \\absolute { \\time 4/4 \\afterGrace c'1 { d'16 } e'1 }\n",
    )
    new = write(
        tmp_path,
        "new.ly",
        "music = \\absolute { \\time 4/4 \\afterGrace c'1 { f'16 } e'1 }\n",
    )

    accepted = diff_scores(old, new, variable="music", expect_measures="1")
    rejected = diff_scores(old, new, variable="music", expect_measures="2")

    assert accepted.ok
    assert rejected.ok is False
    assert "DIFF_OUTSIDE_EXPECTED" in {item.code for item in rejected.diagnostics}


def test_ordinary_grace_belongs_to_the_following_measure(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "grace.ly",
        "music = \\absolute { \\time 4/4 c'1 \\grace { d'16 } e'1 }\n",
    )

    index = build_semantic_index(source, "music")

    grace = next(event for event in index.events if event.grace)
    assert grace.offset == 1
    assert index.position(grace.offset)["measure"] == 2


def test_after_grace_is_scaled_inside_a_tuplet(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tuplet.ly",
        "music = \\absolute { \\time 4/4 \\tuplet 3/2 { \\afterGrace c'4 { d'16 } e'4 } f'2 }\n",
    )

    index = build_semantic_index(source, "music")

    assert [(event.offset, event.duration, event.grace) for event in index.events] == [
        (Fraction(0), Fraction(1, 6), False),
        (Fraction(1, 8), Fraction(0), True),
        (Fraction(1, 6), Fraction(1, 6), False),
        (Fraction(1, 3), Fraction(1, 2), False),
    ]
    assert index.duration == Fraction(5, 6)


def test_nested_after_grace_does_not_advance_past_the_main_note(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "nested.ly",
        "music = \\absolute { \\time 4/4 \\afterGrace \\afterGrace c'1 { d'16 } { e'16 } f'1 }\n",
    )

    index = build_semantic_index(source, "music")

    grace = [event for event in index.events if event.grace]
    assert [event.offset for event in grace] == [Fraction(3, 4), Fraction(3, 4)]
    assert [event.pitches for event in grace] == [(29,), (30,)]
    assert index.duration == 2


def test_after_grace_source_locations_survive_include_and_absolute_mapping(tmp_path: Path) -> None:
    included = write(
        tmp_path,
        "music.ily",
        "melody = \\absolute { \\time 4/4 \\afterGrace c'1 { d'16 } e'1 }\n",
    )
    source = write(tmp_path, "score.ly", '\\include "music.ily"\n')

    index = build_semantic_index(source, "melody")

    grace = next(event for event in index.events if event.grace)
    assert grace.source.file == str(included)
    assert grace.source.line == 1
    assert grace.offset == Fraction(3, 4)


@pytest.mark.parametrize(
    ("after_grace", "name"),
    [
        ("\\afterGrace", "empty"),
        ("\\afterGrace c'4", "missing-grace"),
    ],
)
def test_incomplete_after_grace_is_rejected(
    tmp_path: Path, after_grace: str, name: str
) -> None:
    source = write(
        tmp_path,
        f"{name}.ly",
        f"music = \\absolute {{ {after_grace} }}\n",
    )

    with pytest.raises(WorkbenchError) as raised:
        build_semantic_index(source, "music")

    assert raised.value.code == "AFTER_GRACE_SHAPE"
    assert raised.value.exit_code == 2


@pytest.mark.parametrize("fraction", ["7/8", "#7/8", "#(/ 1 2)"])
def test_explicit_after_grace_fraction_is_rejected(tmp_path: Path, fraction: str) -> None:
    source = write(
        tmp_path,
        "explicit.ly",
        f"music = \\absolute {{ \\time 4/4 \\afterGrace {fraction} c'1 {{ d'16 }} e'1 }}\n",
    )

    with pytest.raises(WorkbenchError) as raised:
        build_semantic_index(source, "music")

    assert raised.value.code == "AFTER_GRACE_EXPLICIT_FRACTION"
    assert raised.value.exit_code == 2


@pytest.mark.parametrize(
    "override",
    [
        "afterGraceFraction = 7/8\n",
        "#(define afterGraceFraction (cons 7 8))\n",
        "#(set! afterGraceFraction (cons 7 8))\n",
    ],
)
def test_global_after_grace_fraction_override_is_rejected(
    tmp_path: Path, override: str
) -> None:
    source = write(
        tmp_path,
        "override.ly",
        override
        + "melody = \\absolute { \\time 4/4 \\afterGrace c'1 { d'16 } e'1 }\n",
    )

    with pytest.raises(WorkbenchError) as raised:
        build_semantic_index(source, "melody")

    assert raised.value.code == "AFTER_GRACE_FRACTION_OVERRIDE"
    assert raised.value.exit_code == 2


def test_global_override_without_after_grace_still_indexes(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "override-only.ly",
        "afterGraceFraction = 7/8\nmelody = \\absolute { \\time 4/4 c'1 e'1 }\n",
    )

    index = build_semantic_index(source, "melody")

    assert [event.pitches for event in index.events] == [(28,), (30,)]


def test_override_mentioned_in_a_comment_is_ignored(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "comment.ly",
        "% afterGraceFraction = 7/8\n"
        "music = \\absolute { \\time 4/4 \\afterGrace c'1 { d'16 } e'1 }\n",
    )

    index = build_semantic_index(source, "music")

    assert next(event for event in index.events if event.grace).offset == Fraction(3, 4)
