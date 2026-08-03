from fractions import Fraction

from music21 import chord

from lilypond_workbench.harmony import _chord_token, _confidence, _duration_suffix


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
