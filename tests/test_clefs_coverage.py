"""Focused clef coverage: rule tables, seams, explicit locks, CLI wrapper and rendering."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from lilypond_workbench.clefs import (
    PITCHES,
    ClefAnalysis,
    ClefTrackEvent,
    _Rule,
    _add_track,
    _skip,
    _weighted_stats,
    analyze_clef_index,
    analyze_clefs,
    clef_track_name,
    render_clef_track,
)
from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.semantic import IndexedEvent, SourceLocation, build_semantic_index


def _index(tmp_path: Path, body: str) -> tuple[Path, object]:
    source = tmp_path / "music.ly"
    source.write_text(f"music = \\absolute {{ {body} }}\n", encoding="utf-8")
    return source, build_semantic_index(source, "music")


def test_violin_has_no_clef_rules(tmp_path: Path) -> None:
    _, index = _index(tmp_path, r"\time 4/4 c'4 d' e' f' |")
    analysis = analyze_clef_index(index, "violin")

    assert not analysis.changes
    assert [event.clef for event in analysis.track] == ["treble"]


def test_long_rest_end_is_a_safe_seam_and_beats_gate_it(tmp_path: Path) -> None:
    _, index = _index(tmp_path, r"\time 4/4 c'4 r2 c'4 |")
    analysis = analyze_clef_index(index, "viola", initial_clef="alto")

    # The r2 ends inside the measure, so that seam is shorter than one beat group.
    assert not analysis.changes
    rest = next(event for event in index.events if event.kind == "rest")
    assert rest.end == Fraction(3, 4)


def test_explicit_clef_mid_measure_locks_out_a_crossing_recommendation(tmp_path: Path) -> None:
    _, index = _index(tmp_path, r"\time 4/4 c''2 \clef treble c''2 |")
    analysis = analyze_clef_index(index, "viola", initial_clef="alto")

    assert not analysis.changes
    assert [(event.offset, event.clef) for event in analysis.track] == [(0, "alto"), (Fraction(1, 2), "treble")]


def test_up_rule_rejects_a_window_where_the_target_clef_costs_more(tmp_path: Path) -> None:
    # The top note reaches C5, but the C4 half of each dyad costs more in treble.
    _, index = _index(tmp_path, r"\time 4/4 <c' c''>1 | <c' c''>1 |")
    analysis = analyze_clef_index(index, "viola", initial_clef="alto")

    assert not analysis.changes


def test_down_rule_rejects_a_window_where_alto_costs_more(tmp_path: Path) -> None:
    _, index = _index(tmp_path, r"\time 4/4 b'1 | b'1 |")
    analysis = analyze_clef_index(index, "viola", initial_clef="treble")

    assert not analysis.changes


def test_zero_duration_event_cannot_contribute_to_a_window(tmp_path: Path) -> None:
    source, index = _index(tmp_path, r"\time 4/4 <c' c''>1 | <c' c''>1 |")
    zero = IndexedEvent(
        "chord",
        Fraction(1, 2),
        Fraction(0),
        (28, 35),
        SourceLocation(str(source), 1, 1, 0),
    )
    patched = replace(index, events=index.events + (zero,))
    rule = _Rule("treble", "up", PITCHES["C5"], "C5 or above")
    before = _weighted_stats(index, Fraction(0), Fraction(2), current="alto", rule=rule)
    after = _weighted_stats(patched, Fraction(0), Fraction(2), current="alto", rule=rule)

    # The zero-length onset must not inflate attacks or any weighted cost.
    assert before is not None and after is not None
    assert before.attacks == after.attacks == 2
    assert after == before
    assert not analyze_clef_index(patched, "viola", initial_clef="alto").changes


def test_unsupported_instrument_is_a_configuration_error(tmp_path: Path) -> None:
    _, index = _index(tmp_path, "c'1")

    with pytest.raises(WorkbenchError) as error:
        analyze_clef_index(index, "flute")

    assert error.value.code == "UNSUPPORTED_INSTRUMENT"
    assert error.value.exit_code == 2


def test_nonstandard_initial_clef_is_preserved_with_a_warning(tmp_path: Path) -> None:
    _, index = _index(tmp_path, r"\time 4/4 c'4 d' e' f' |")
    analysis = analyze_clef_index(index, "violin", initial_clef="bass")

    assert analysis.initial_clef == "bass"
    assert analysis.track[0].clef == "bass"
    assert any(item.code == "CLEF_NONSTANDARD" for item in analysis.diagnostics)


def test_analyze_clefs_writes_a_versioned_report(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text("music = \\absolute { \\time 4/4 c'4 d' e' f' }\n", encoding="utf-8")
    destination = tmp_path / "clefs.json"

    result = analyze_clefs(source, variable="music", instrument="viola", output_path=destination)

    assert result.ok
    assert result.command == "analyze-clefs"
    assert result.artifacts == [str(destination)]
    assert result.metadata["changes"] == 0
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["variable"] == "music"
    assert payload["instrument"] == "viola"


def test_explicit_clef_wins_at_a_shared_offset() -> None:
    track = [ClefTrackEvent(Fraction(0), "treble", "explicit")]

    _add_track(track, ClefTrackEvent(Fraction(0), "alto", "recommended"))

    assert track == [ClefTrackEvent(Fraction(0), "treble", "explicit")]


def test_clef_track_name_normalizes_part_ids() -> None:
    assert clef_track_name("violin 1") == "workbenchViolin1Clefs"
    assert clef_track_name("---") == "workbenchPartClefs"


def test_skip_spells_whole_and_fractional_durations() -> None:
    assert _skip(Fraction(1)) == "s1"
    assert _skip(Fraction(2)) == "s1*2"
    assert _skip(Fraction(1, 2)) == "s1*1/2"


def test_render_clef_track_fills_both_whole_and_fractional_gaps() -> None:
    analysis = ClefAnalysis(
        schema_version=1,
        source="score.ly",
        variable="music",
        instrument="viola",
        initial_clef="alto",
        duration=Fraction(3),
        changes=(),
        track=(
            ClefTrackEvent(Fraction(0), "alto", "initial"),
            ClefTrackEvent(Fraction(2), "treble", "recommended"),
            ClefTrackEvent(Fraction(5, 2), "bass", "recommended"),
        ),
        diagnostics=(),
        index_fingerprint="fp",
    )

    rendered = render_clef_track("workbenchViolaClefs", analysis)

    assert rendered == "\n".join(
        [
            "workbenchViolaClefs = {",
            "  \\clef alto",
            "  s1*2",
            "  \\clef treble",
            "  s1*1/2",
            "  \\clef bass",
            "  s1*1/2",
            "}",
            "",
        ]
    )
