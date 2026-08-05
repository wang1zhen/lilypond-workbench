from pathlib import Path

from lilypond_workbench.clefs import analyze_clef_index, render_clef_track
from lilypond_workbench.semantic import build_semantic_index


def _analyze(tmp_path: Path, body: str, instrument: str, *, initial: str | None = None):
    source = tmp_path / f"{instrument}.ly"
    source.write_text(f"music = \\absolute {{ {body} }}\n", encoding="utf-8")
    index = build_semantic_index(source, "music")
    return index, analyze_clef_index(index, instrument, initial_clef=initial)


def test_viola_uses_hysteresis_and_returns_to_alto(tmp_path: Path) -> None:
    index, analysis = _analyze(
        tmp_path,
        r"\time 4/4 \clef alto c'4 d' e' f' | c''4 d'' e'' f'' | d'' e'' f'' g'' | a' b' a' g' |",
        "viola",
    )

    assert [(item.offset, item.from_clef, item.to_clef) for item in analysis.changes] == [
        (1, "alto", "treble"),
        (3, "treble", "alto"),
    ]
    assert analysis.to_dict(index)["changes"][0]["start"]["measure"] == 2


def test_cello_moves_through_bass_tenor_treble_and_back(tmp_path: Path) -> None:
    _, analysis = _analyze(
        tmp_path,
        r"\time 4/4 \clef bass c4 d e f | d'4 e' f' g' | a'4 b' c'' d'' | c4 d e f |",
        "cello",
    )

    assert [(item.offset, item.from_clef, item.to_clef) for item in analysis.changes] == [
        (1, "bass", "tenor"),
        (2, "tenor", "treble"),
        (3, "treble", "bass"),
    ]
    track = render_clef_track("workbenchCelloClefs", analysis)
    assert "\\clef tenor" in track
    assert "\\clef treble" in track
    assert "s1*3/1" not in track


def test_one_bar_two_note_spike_does_not_change_clef(tmp_path: Path) -> None:
    _, analysis = _analyze(
        tmp_path,
        r"\time 4/4 c'4 d' e' f' | c''2 d'' | c'4 d' e' f' |",
        "viola",
        initial="alto",
    )

    assert not analysis.changes


def test_two_bar_sustained_high_passage_is_long_enough(tmp_path: Path) -> None:
    _, analysis = _analyze(tmp_path, r"\time 4/4 c''1 | c''1 |", "viola", initial="alto")

    assert [(item.offset, item.to_clef) for item in analysis.changes] == [(0, "treble")]


def test_violin_preserves_but_warns_about_nonstandard_explicit_clef(tmp_path: Path) -> None:
    _, analysis = _analyze(tmp_path, r"\time 4/4 \clef alto c'4 d' e' f' |", "violin")

    assert not analysis.changes
    assert analysis.track[0].clef == "alto"
    assert any(item.code == "CLEF_NONSTANDARD" for item in analysis.diagnostics)


def test_cue_sized_high_music_does_not_trigger_change(tmp_path: Path) -> None:
    _, analysis = _analyze(
        tmp_path,
        r'''\time 4/4 c'1 | \cueDuring "violin" #UP { c''4 d'' e'' f'' } | c'1 |''',
        "viola",
        initial="alto",
    )

    assert not analysis.changes

