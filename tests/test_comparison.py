from __future__ import annotations

import json
from pathlib import Path

import pytest

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.comparison import diff_scores, index_score, parse_measure_selection
from lilypond_workbench.semantic import build_semantic_index


BASE = r'''\version "2.24.4"
music = \relative c' {
  \key c \major
  \time 4/4
  c4 d e f |
  g4 a b c |
  d2 c2 |
}
'''


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def report_of(result) -> dict:
    return result.metadata["report"]


def kinds(result) -> list[str]:
    return [change["kind"] for change in report_of(result)["changes"]]


# --- markers -------------------------------------------------------------


def test_index_captures_key_tempo_dynamics_and_repeats(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "markers.ly",
        r'''\version "2.24.4"
music = \relative c' {
  \key d \major
  \tempo "Allegro" 4 = 120
  \time 3/4
  \clef treble
  c4-.\f d e |
  \key bes \minor
  \tempo 4 = 96
  f2 g4 |
  \repeat volta 2 { a2 b4 }
}
''',
    )
    index = build_semantic_index(source, "music")
    found = {(marker.kind, marker.value) for marker in index.markers}
    assert ("key", "D major") in found
    assert ("key", "B-flat minor") in found
    assert ("tempo", "Allegro 1/4=120") in found
    assert ("tempo", "1/4=96") in found
    assert ("dynamic", "f") in found
    assert ("articulation", ".") in found
    assert ("repeat", "volta 2") in found
    assert ("meter", "3/4") in found
    assert ("clef", "treble") in found


def test_attachments_are_recorded_at_the_onset_of_their_own_note(tmp_path: Path) -> None:
    """A dynamic is a sibling of its note, reached after time has advanced."""
    source = write(tmp_path, "attach.ly", '\\version "2.24.4"\nmusic = { c\'4 d\'\\f e\' f\' }\n')
    index = build_semantic_index(source, "music")
    dynamic = next(marker for marker in index.markers if marker.kind == "dynamic")
    assert index.position(dynamic.offset) == {"offset": "1/4", "measure": 1, "beat": "2"}


def test_index_reports_accidentals_alongside_diatonic_positions(tmp_path: Path) -> None:
    source = write(tmp_path, "alter.ly", '\\version "2.24.4"\nmusic = { ces\'4 c\' cis\' cisis\' }\n')
    payload = report_of(index_score(source, variable="music"))
    assert [event["pitches"][0] for event in payload["events"]] == ["Cb4", "C4", "C#4", "C##4"]
    assert {event["diatonic_pitches"][0] for event in payload["events"]} == {28}


def test_index_command_reports_the_versioned_index(tmp_path: Path) -> None:
    source = write(tmp_path, "base.ly", BASE)
    result = index_score(source, variable="music")
    payload = report_of(result)
    assert result.ok
    assert payload["schema_version"] == 2
    assert payload["variable"] == "music"
    assert payload["duration"] == "3"
    assert len(payload["events"]) == 10


def test_index_writes_a_report_file_and_refuses_to_clobber(tmp_path: Path) -> None:
    source = write(tmp_path, "base.ly", BASE)
    destination = tmp_path / "index.json"
    result = index_score(source, variable="music", output_path=destination)
    assert result.artifacts == [str(destination)]
    assert json.loads(destination.read_text(encoding="utf-8"))["schema_version"] == 2
    with pytest.raises(WorkbenchError) as error:
        index_score(source, variable="music", output_path=destination)
    assert error.value.code == "OUTPUT_EXISTS"
    assert index_score(source, variable="music", output_path=destination, force=True).ok


def test_index_rejects_an_unknown_variable(tmp_path: Path) -> None:
    source = write(tmp_path, "base.ly", BASE)
    with pytest.raises(WorkbenchError) as error:
        index_score(source, variable="absent")
    assert error.value.code == "VARIABLE_NOT_FOUND"
    assert error.value.exit_code == 2


# --- diff ----------------------------------------------------------------


def test_identical_sources_report_no_changes(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE)
    result = diff_scores(old, new, variable="music")
    assert result.ok
    assert report_of(result)["identical"] is True
    assert report_of(result)["summary"] == {
        "changes": 0,
        "changed_measures": [],
        "by_kind": {},
        "duration_changed": False,
    }


def test_reformatting_and_absolute_rewriting_are_not_musical_changes(tmp_path: Path) -> None:
    """The case a text diff cannot answer: every line differs, no music does."""
    old = write(tmp_path, "old.ly", BASE)
    new = write(
        tmp_path,
        "new.ly",
        r'''\version "2.24.4"
% retyped in absolute pitch with different layout
music = {
  \key c \major \time 4/4
  c'4 d' e' f' | g' a' b' c'' |
  % second half
  d''2 c''2 |
}
''',
    )
    assert old.read_text(encoding="utf-8") != new.read_text(encoding="utf-8")
    result = diff_scores(old, new, variable="music", fail_on_change=True)
    assert result.ok
    assert report_of(result)["identical"] is True


def test_an_edited_pitch_inside_relative_is_located_by_measure_and_beat(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    result = diff_scores(old, new, variable="music")
    change = report_of(result)["changes"][0]
    assert change["kind"] == "pitch_changed"
    assert change["detail"] == "pitch A4 became Ab4"
    assert (change["old"]["measure"], change["old"]["beat"]) == (2, "2")
    assert change["new"]["line"] == 6
    # A relative edit must not be reported as a cascade of later differences.
    assert report_of(result)["summary"]["changes"] == 1


def test_a_changed_duration_is_distinguished_from_a_changed_pitch(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("d2 c2", "d2 c4 c4"))
    result = diff_scores(old, new, variable="music")
    assert "duration_changed" in kinds(result) or "event_added" in kinds(result)
    assert report_of(result)["summary"]["duration_changed"] is False


def test_added_and_removed_notes_are_reported_as_such(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("d2 c2 |", "d2 c4 b4 |\n  c1 |"))
    result = diff_scores(old, new, variable="music")
    assert "event_added" in kinds(result)
    assert report_of(result)["summary"]["duration_changed"] is True


def test_a_dropped_dynamic_is_reported(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE.replace("c4 d e f", "c4\\f d e f"))
    new = write(tmp_path, "new.ly", BASE)
    result = diff_scores(old, new, variable="music")
    assert kinds(result) == ["marker_removed"]
    assert report_of(result)["changes"][0]["detail"] == "removed dynamic f"


def test_a_changed_key_signature_is_reported(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("\\key c \\major", "\\key a \\minor"))
    result = diff_scores(old, new, variable="music")
    assert sorted(kinds(result)) == ["marker_added", "marker_removed"]
    details = {change["detail"] for change in report_of(result)["changes"]}
    assert details == {"removed key C major", "added key A minor"}


def test_every_change_reaches_the_diagnostic_channel_with_a_location(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    result = diff_scores(old, new, variable="music")
    diagnostic = next(item for item in result.diagnostics if item.code == "DIFF_PITCH_CHANGED")
    assert diagnostic.severity == "info"
    assert diagnostic.line == 6
    assert "measure 2 beat 2" in diagnostic.message


def test_a_renamed_variable_can_still_be_compared(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("music =", "violinMusic ="))
    result = diff_scores(old, new, variable="music", new_variable="violinMusic")
    assert result.ok
    assert report_of(result)["identical"] is True
    assert report_of(result)["new"]["variable"] == "violinMusic"


def test_fail_on_change_turns_any_difference_into_a_failure(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    result = diff_scores(old, new, variable="music", fail_on_change=True)
    assert not result.ok
    assert any(item.code == "DIFF_UNEXPECTED_CHANGE" for item in result.diagnostics)


def test_changes_inside_the_expected_measures_pass(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    result = diff_scores(old, new, variable="music", expect_measures="2")
    assert result.ok
    assert report_of(result)["expect_measures"] == [2]


def test_changes_outside_the_expected_measures_fail_with_a_location(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    result = diff_scores(old, new, variable="music", expect_measures="3")
    assert not result.ok
    diagnostic = next(item for item in result.diagnostics if item.code == "DIFF_OUTSIDE_EXPECTED")
    assert diagnostic.line == 6
    assert "measure 2" in diagnostic.message


def test_diff_writes_a_report_file(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE.replace("g4 a b c", "g4 aes b c"))
    destination = tmp_path / "diff.json"
    result = diff_scores(old, new, variable="music", output_path=destination)
    assert result.artifacts == [str(destination)]
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["old"]["fingerprint"] != payload["new"]["fingerprint"]


def test_diff_carries_a_fingerprint_for_each_side(tmp_path: Path) -> None:
    """Fingerprints digest the dependency paths, so two files never share one."""
    old = write(tmp_path, "old.ly", BASE)
    new = write(tmp_path, "new.ly", BASE)
    payload = report_of(diff_scores(old, new, variable="music"))
    assert payload["old"]["fingerprint"] != payload["new"]["fingerprint"]
    assert report_of(diff_scores(old, old, variable="music"))["old"]["fingerprint"] == (
        payload["old"]["fingerprint"]
    )


DROPPED_REPEAT = r'''\version "2.24.4"
music = { \tempo 4 = 96 \repeat volta 2 { c'4 d' e' f' } }
'''

KEPT_REPEAT = r'''\version "2.24.4"
music = { \repeat volta 2 { c'4 d' e' f' } }
'''


def test_a_repeat_the_parser_drops_is_reported_not_silently_omitted(tmp_path: Path) -> None:
    """python-ly discards a \\repeat that directly follows a \\tempo mark."""
    source = write(tmp_path, "dropped.ly", DROPPED_REPEAT)
    result = index_score(source, variable="music")
    warning = next(item for item in result.diagnostics if item.code == "SEMANTIC_REPEAT_DROPPED")
    assert warning.severity == "warning"
    assert warning.line == 2
    assert report_of(result)["events"] == []


def test_a_parsed_repeat_raises_no_warning(tmp_path: Path) -> None:
    source = write(tmp_path, "kept.ly", KEPT_REPEAT)
    result = index_score(source, variable="music")
    assert [item.code for item in result.diagnostics] == []
    assert len(report_of(result)["events"]) == 4


def test_reordered_simultaneous_voices_read_as_a_difference(tmp_path: Path) -> None:
    """Documented limitation: voices are indexed in traversal order."""
    old = write(tmp_path, "old.ly", '\\version "2.24.4"\nmusic = << { c\'4 d\' } \\\\ { a4 b4 } >>\n')
    new = write(tmp_path, "new.ly", '\\version "2.24.4"\nmusic = << { a4 b4 } \\\\ { c\'4 d\' } >>\n')
    result = diff_scores(old, new, variable="music")
    assert set(kinds(result)) == {"event_added", "event_removed"}


# --- measure selection ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4", {4}),
        ("1,3", {1, 3}),
        ("37-40", {37, 38, 39, 40}),
        (" 2 , 5-7 ", {2, 5, 6, 7}),
        ("5-5", {5}),
    ],
)
def test_measure_selection_parsing(text: str, expected: set[int]) -> None:
    assert parse_measure_selection(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "3-1", "1-", "-", "2-x"])
def test_invalid_measure_selection_is_a_configuration_error(text: str) -> None:
    with pytest.raises(WorkbenchError) as error:
        parse_measure_selection(text)
    assert error.value.exit_code == 2
