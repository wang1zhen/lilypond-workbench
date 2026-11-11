"""Boundary coverage for semantic.py's index model and parser edge cases."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
from ly.music import items

import lilypond_workbench.semantic as semantic
from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.comparison import diff_scores
from lilypond_workbench.semantic import (
    Measure,
    SourceLocation,
    _EventCollector,
    _RawRecord,
    _key_name,
    _local_dependencies,
    _remap_locations,
    _tempo_text,
    build_semantic_index,
    pitch_label,
)


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def diagnostics_of(index) -> set[str]:
    return {item.code for item in index.diagnostics}


def test_empty_music_uses_a_synthetic_measure(tmp_path: Path) -> None:
    index = build_semantic_index(write(tmp_path, "empty.ly", "music = \\absolute { }"), "music")

    assert index.events == ()
    assert index.measures == ()
    assert index.measure_at(Fraction(0)) == Measure(1, Fraction(0), Fraction(1), Fraction(1), Fraction(1, 4), False)
    assert index.position(Fraction(0)) == {"offset": "0", "measure": 1, "beat": "1"}
    assert index.to_dict()["duration"] == "0"


def test_measure_at_past_the_end_returns_the_last_measure(tmp_path: Path) -> None:
    index = build_semantic_index(
        write(tmp_path, "short.ly", "music = \\absolute { \\time 4/4 c'1 }"),
        "music",
    )

    assert index.measure_at(Fraction(0)) is index.measures[0]
    assert index.measure_at(Fraction(999)) is index.measures[-1]


@pytest.mark.parametrize(
    ("alter", "label"),
    [
        (Fraction(0), "C4"),
        (Fraction(1, 2), "C#4"),
        (Fraction(-1, 2), "Cb4"),
        (Fraction(1), "C##4"),
        (Fraction(-1), "Cbb4"),
        (Fraction(1, 4), "C+0.254"),
    ],
)
def test_pitch_label_respells_standard_and_unusual_accidentals(alter: Fraction, label: str) -> None:
    assert pitch_label(28, alter) == label


class _FakeKey:
    def __init__(self, mode: str | None, pitch: object | None) -> None:
        self._mode = mode
        self._pitch = pitch

    def mode(self) -> str | None:
        return self._mode

    def pitch(self) -> object | None:
        return self._pitch


def test_key_name_without_a_pitch_falls_back_to_the_mode() -> None:
    assert _key_name(_FakeKey("major", None)) == "major"
    assert _key_name(_FakeKey(None, None)) == ""


class _NoPlaintext:
    pass


class _FakeTempo:
    def text(self) -> object:
        return _NoPlaintext()

    def tempo(self) -> list[int]:
        return [60]

    def fraction(self) -> Fraction:
        return Fraction(1, 4)


def test_tempo_text_survives_a_text_node_without_plaintext() -> None:
    assert _tempo_text(_FakeTempo()) == "1/4=60"


def test_missing_non_music_and_ambiguous_variables_are_input_errors(tmp_path: Path) -> None:
    with pytest.raises(WorkbenchError) as missing:
        build_semantic_index(write(tmp_path, "missing.ly", "other = { c4 }"), "music")
    assert missing.value.code == "VARIABLE_NOT_FOUND"
    assert missing.value.exit_code == 2

    with pytest.raises(WorkbenchError) as not_music:
        build_semantic_index(write(tmp_path, "text.ly", 'music = "words"'), "music")
    assert not_music.value.code == "VARIABLE_NOT_MUSIC"

    write(tmp_path, "a.ily", "music = \\absolute { c'1 }")
    write(tmp_path, "b.ily", "music = \\absolute { d'1 }")
    ambiguous = write(tmp_path, "ambiguous.ly", '\\include "a.ily"\n\\include "b.ily"\n')
    with pytest.raises(WorkbenchError) as raised:
        build_semantic_index(ambiguous, "music")
    assert raised.value.code == "VARIABLE_AMBIGUOUS"


def test_duplicate_include_is_walked_once(tmp_path: Path) -> None:
    write(tmp_path, "music.ily", "music = \\absolute { c'1 }")
    source = write(tmp_path, "twice.ly", '\\include "music.ily"\n\\include "music.ily"\n')

    index = build_semantic_index(source, "music")

    assert len(index.events) == 1


def test_user_commands_follow_assignments_and_break_recursion(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "commands.ly",
        "a = { \\b c'4 }\n"
        "b = { \\a d'4 }\n"
        "music = \\absolute { \\a e'4 \\unknownthing f'4 }\n",
    )

    index = build_semantic_index(source, "music")

    # a -> b -> a stops at the second a, then the surrounding notes play on.
    assert [event.pitches for event in index.events] == [(29,), (28,), (30,), (31,)]
    assert index.duration == 1
    assert index.markers == ()


class _MarkDocument:
    filename = None

    def plaintext(self) -> str:
        return ""


class _MarkUserCommand(items.UserCommand):
    def name(self) -> str:
        return "mark"

    def value(self):
        return None


def test_user_command_named_mark_still_records_a_rehearsal_seam() -> None:
    # python-ly currently parses \mark as Command, but the collector keeps a
    # UserCommand path in case that classification changes.
    node = _MarkUserCommand()
    node.document = _MarkDocument()
    node.position = 0
    collector = _EventCollector()

    assert collector.traverse(node, Fraction(0), Fraction(1)) == 0
    assert [(record.kind, record.value) for record in collector.records] == [
        ("seam", "rehearsal")
    ]


def test_grace_chords_are_flagged_without_advancing_time(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "grace-chord.ly",
        "music = \\absolute { \\time 4/4 \\grace { <c' e'>8 } d'1 | }\n",
    )

    index = build_semantic_index(source, "music")

    assert [(event.kind, event.duration, event.grace, event.pitches) for event in index.events] == [
        ("chord", Fraction(0), True, (28, 30)),
        ("note", Fraction(1), False, (29,)),
    ]
    assert index.duration == 1


def test_comparison_sees_a_grace_note_pitch_change(tmp_path: Path) -> None:
    old = write(tmp_path, "old.ly", "music = \\absolute { \\time 4/4 \\grace { c''16 } d'1 | }\n")
    new = write(tmp_path, "new.ly", "music = \\absolute { \\time 4/4 \\grace { e''16 } d'1 | }\n")

    result = diff_scores(old, new, variable="music")

    change = result.metadata["report"]["changes"][0]
    assert change["old"]["grace"] is True
    assert change["kind"] == "pitch_changed"
    assert change["detail"] == "pitch C5 became E5"


def test_indexes_rests_skips_articulations_keys_tempo_partials_and_phrasing(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "markers.ly",
        r"""music = \absolute {
  \time 4/4
  r4 s4 c'4-> d'4\fermata
  \key bes \minor
  \tempo "Allegro" 4=120
  \partial 8
  e'8\p f'4\( g'4\)
}
""",
    )

    index = build_semantic_index(source, "music")

    assert [(event.kind, event.pitches) for event in index.events] == [
        ("rest", ()),
        ("skip", ()),
        ("note", (28,)),
        ("note", (29,)),
        ("note", (30,)),
        ("note", (31,)),
        ("note", (32,)),
    ]
    values = {(marker.kind, marker.value) for marker in index.markers}
    assert ("articulation", ">") in values
    assert ("articulation", "fermata") in values
    assert ("dynamic", "p") in values
    assert ("key", "B-flat minor") in values
    assert ("tempo", "Allegro 1/4=120") in values
    assert ("partial", "") in values
    assert ("seam", "phrase-start") in values
    assert ("seam", "phrase-stop") in values
    report = index.to_dict()
    assert report["events"][2]["pitches"] == ["C4"]
    assert report["markers"][0]["kind"] == "meter"


def test_repeat_dropped_by_tempo_is_reported(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "dropped.ly",
        "music = \\absolute { \\tempo 4=120 \\repeat unfold 2 { c'1 } }\n",
    )

    index = build_semantic_index(source, "music")

    assert index.events == ()
    assert diagnostics_of(index) == {"SEMANTIC_REPEAT_DROPPED"}


def test_repeat_warning_skips_documents_where_the_variable_cannot_be_located(tmp_path: Path) -> None:
    # The assignment shares a line with \version, so the line-anchored variable
    # scan cannot find it and the dropped-repeat warning has no source to point at.
    source = write(
        tmp_path,
        "inline.ly",
        '\\version "2.24.4" music = \\absolute { \\tempo 4=120 \\repeat unfold 2 { c\'1 } }\n',
    )

    index = build_semantic_index(source, "music")

    assert "SEMANTIC_REPEAT_DROPPED" not in diagnostics_of(index)


def test_remap_locations_refuses_structurally_different_records() -> None:
    absolute = [
        _RawRecord("note", Fraction(0), Fraction(1), (28,), "", SourceLocation("abs", 1, 0, 0))
    ]
    original = [
        _RawRecord("rest", Fraction(0), Fraction(1), (), "", SourceLocation("orig", 1, 0, 0))
    ]

    records, mapped = _remap_locations(absolute, original)

    assert records is absolute
    assert mapped is False


def test_remap_locations_copies_original_locations_when_shapes_match() -> None:
    absolute = [
        _RawRecord("note", Fraction(0), Fraction(1), (28,), "", SourceLocation("abs", 1, 0, 0))
    ]
    original = [
        _RawRecord("note", Fraction(0), Fraction(1), (28,), "", SourceLocation("orig", 2, 3, 4))
    ]

    _, mapped = _remap_locations(absolute, original)

    assert mapped is True
    assert absolute[0].source == SourceLocation("orig", 2, 3, 4)


def test_local_dependencies_skips_missing_and_duplicate_includes(tmp_path: Path) -> None:
    write(tmp_path, "music.ily", "music = \\absolute { c'1 }")
    source = write(
        tmp_path,
        "deps.ly",
        '\\include "music.ily"\n\\include "missing.ily"\n\\include "./music.ily"\n',
    )

    assert _local_dependencies(source) == sorted({source.resolve(), (tmp_path / "music.ily").resolve()})


def test_source_map_warning_when_absolute_parsing_changes_event_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write(tmp_path, "structure.ly", "music = \\absolute { c'1 }\n")
    real_collect = semantic._collect
    calls: list[list[_RawRecord]] = []

    def collect(assignment, **kwargs):
        records = real_collect(assignment, **kwargs)
        calls.append(records)
        if len(calls) == 2:
            records = records + [
                _RawRecord("rest", Fraction(0), Fraction(0), (), "", SourceLocation("<memory>", 1, 0, 0))
            ]
        return records

    monkeypatch.setattr(semantic, "_collect", collect)

    index = build_semantic_index(source, "music")

    assert "SEMANTIC_SOURCE_MAP" in diagnostics_of(index)
