"""Focused comparison coverage: event-kind changes, grace pairing and diagnostic truncation."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from lilypond_workbench.comparison import _pair_change, diff_scores
from lilypond_workbench.semantic import build_semantic_index


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(f'\\version "2.24.4"\nmusic = {{ {body} }}\n', encoding="utf-8")
    return path


def _report(result) -> dict:
    return result.metadata["report"]


def test_a_note_replaced_by_a_rest_reports_the_kind_change(tmp_path: Path) -> None:
    old = _write(tmp_path, "old.ly", "c'4 d'4")
    new = _write(tmp_path, "new.ly", "r4 d'4")

    change = _report(diff_scores(old, new, variable="music"))["changes"][0]

    assert change["kind"] == "event_changed"
    assert "note became rest" in change["detail"]


def _event_index(tmp_path: Path):
    source = _write(tmp_path, "base.ly", "c'4")
    return build_semantic_index(source, "music")


def test_a_paired_event_whose_grace_status_changed_is_reported(tmp_path: Path) -> None:
    index = _event_index(tmp_path)
    event = index.events[0]
    change = _pair_change(index, index, event, replace(event, grace=True))

    assert change is not None
    assert change.kind == "event_changed"
    assert change.detail == "grace status changed"


def test_pairing_two_identical_events_yields_no_change(tmp_path: Path) -> None:
    index = _event_index(tmp_path)
    event = index.events[0]

    assert _pair_change(index, index, event, event) is None


def test_pairing_identical_music_at_a_new_onset_is_a_timing_change(tmp_path: Path) -> None:
    index = _event_index(tmp_path)
    event = index.events[0]
    moved = replace(event, offset=Fraction(1, 4))

    change = _pair_change(index, index, event, moved)

    assert change is not None
    assert change.kind == "timing_changed"
    assert change.detail == "onset 0 became 1/4"


def test_more_than_one_hundred_changes_are_truncated_only_in_diagnostics(tmp_path: Path) -> None:
    old = _write(tmp_path, "old.ly", " ".join(["c'4"] * 101))
    new = _write(tmp_path, "new.ly", "r1")

    result = diff_scores(old, new, variable="music")

    report = _report(result)
    assert len(report["changes"]) == 102
    truncated = next(item for item in result.diagnostics if item.code == "DIFF_TRUNCATED")
    assert "2 further change(s)" in truncated.message
    assert report["summary"]["changes"] == 102
