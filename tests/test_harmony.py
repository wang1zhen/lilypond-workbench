from fractions import Fraction

import pytest
from music21 import chord

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.harmony import _chord_token, _confidence, _duration_suffix, _select_score


def test_duration_conversion() -> None:
    assert _duration_suffix(1) == "4"
    assert _duration_suffix(Fraction(3, 2)) == "4."
    assert _duration_suffix(Fraction(5, 2)) == "1*5/8"


def test_chord_token_major_minor_and_inversion() -> None:
    assert _chord_token(chord.Chord(["C3", "E3", "G3"]), "1") == "c1"
    assert _chord_token(chord.Chord(["E3", "G3", "C4"]), "2") == "c2/e"
    assert _chord_token(chord.Chord(["A3", "C4", "E4"]), "1") == "a1:m"


def test_dyad_is_below_default_confidence_threshold() -> None:
    confidence, reason = _confidence(chord.Chord(["C4", "G4"]), "C5")
    assert confidence < 0.60
    assert reason


def test_select_score_keeps_only_the_selected_score_and_adds_midi() -> None:
    text = (
        '\\version "2.24.4"\n'
        'first = { c\'1 }\n'
        'second = { g\'1 }\n'
        '\\score { \\new Staff \\first \\layout { } }\n'
        '\\score { \\new Staff \\second \\layout { } }\n'
    )
    result = _select_score(text, 1)
    assert result.count("\\score") == 1
    assert "\\new Staff \\second" in result
    assert "\\new Staff \\first" not in result
    assert "\\midi" in result


def test_select_score_leaves_single_score_untouched() -> None:
    text = '\\score { \\new Staff { c\'1 } \\layout { } \\midi { } }\n'
    assert _select_score(text, 0) == text


def test_select_score_removes_outer_block_containing_nested_score() -> None:
    text = (
        "\\score { \\new Staff { c'1^\\markup { \\score { \\new Staff { d'4 } \\layout { } } } } "
        "\\layout { } \\midi { } }\n"
        "\\score { \\new Staff { <a' cis'' e''>1 } \\layout { } \\midi { } }\n"
    )
    result = _select_score(text, 2)
    assert result.count("\\score") == 1
    assert "<a' cis'' e''>1" in result
    assert "d'4" not in result
    assert result.count("{") == result.count("}")


def test_select_score_rejects_nested_selected_score() -> None:
    text = (
        "\\score { \\new Staff { c'1^\\markup { \\score { \\new Staff { d'4 } \\layout { } } } } "
        "\\layout { } }\n"
    )
    with pytest.raises(WorkbenchError) as exc:
        _select_score(text, 1)
    assert exc.value.code == "SCORE_ISOLATION_UNSUPPORTED"
    assert exc.value.exit_code == 2
