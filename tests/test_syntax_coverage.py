"""Boundary coverage for syntax.py's text-level structure helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.syntax import (
    check_measure_durations,
    find_command_blocks,
    insert_midi_block,
    matching_brace,
    reformat_lilypond,
    rewrite_relative_includes,
    sanitize_definitions,
)


def codes(diagnostics: list) -> set[str]:
    return {item.code for item in diagnostics}


def test_unmatched_opening_brace_is_an_input_error() -> None:
    with pytest.raises(WorkbenchError) as raised:
        matching_brace("\\score { c4", 7)
    assert raised.value.code == "UNMATCHED_DELIMITER"


def test_command_without_brace_and_nested_command_blocks() -> None:
    assert find_command_blocks('\\score "no braces"', "score") == []
    nested = r"\book { \score { c4 } }"
    assert len(find_command_blocks(nested, "score")) == 1
    assert find_command_blocks(nested, "score", top_level_only=True) == []


def test_sanitize_without_score_blocks_keeps_source_unchanged() -> None:
    source = "music = { c4 d e f }\n"
    assert sanitize_definitions(source) == source


def test_insert_midi_requires_a_score_block() -> None:
    with pytest.raises(WorkbenchError) as raised:
        insert_midi_block("music = { c4 }")
    assert raised.value.code == "SCORE_NOT_FOUND"


def test_insert_midi_rejects_an_out_of_range_score_index() -> None:
    for index in (-1, 1):
        with pytest.raises(WorkbenchError) as raised:
            insert_midi_block("\\score { c4 }", index)
        assert raised.value.code == "SCORE_INDEX"
        assert raised.value.exit_code == 2


def test_reformat_lilypond_returns_indented_text_with_final_newline() -> None:
    output = reformat_lilypond("melody = { c4 d e f }")
    assert output == "melody = { c4 d e f }\n"


def test_rewrite_relative_includes_resolves_only_relative_paths(tmp_path: Path) -> None:
    source = '\\include "music.ily"\n\\include "/opt/shared/common.ily"\n'
    output = rewrite_relative_includes(source, tmp_path)

    assert f'\\include "{(tmp_path / "music.ily").resolve().as_posix()}"' in output
    assert '\\include "/opt/shared/common.ily"' in output


def test_duration_checker_wraps_a_document_without_variables() -> None:
    issues = check_measure_durations("\\absolute { \\time 4/4 c'2 | }")
    assert [item.code for item in issues] == ["BAR_DURATION"]
    assert issues[0].file is None
    assert issues[0].details["variable"] == "document"


def test_duration_checker_honours_global_and_inline_partials() -> None:
    global_partial = (
        "global = { \\time 4/4 \\partial 4 }\n"
        "melody = \\absolute { \\global c'4 | d'1 | }\n"
    )
    inline_partial = "melody = \\absolute { \\time 4/4 \\partial 4 c'4 | d'1 | }\n"

    assert not codes(check_measure_durations(global_partial))
    assert not codes(check_measure_durations(inline_partial))


@pytest.mark.parametrize(
    "body",
    [
        r"<< { c4 d } \\ { e4 f } >> |",
        r"#(set-octavation 1) c1 |",
        r"\compoundMeter #'((3 8) (2 8)) c4 d e f |",
    ],
)
def test_duration_checker_defers_constructs_it_cannot_count(body: str) -> None:
    issues = check_measure_durations(f"melody = \\absolute {{ \\time 4/4 {body} }}")
    assert [item.code for item in issues] == ["DURATION_PARTIAL_ANALYSIS"]
    assert "compiler validation" in issues[0].message


def test_duration_checker_scales_nested_braces() -> None:
    source = "melody = \\absolute { \\time 4/4 { c'4 d'4 } e'2 | f'1 | }\n"
    issues = check_measure_durations(source)

    assert not [item for item in issues if item.code == "BAR_DURATION"]


def test_duration_checker_warns_about_an_incomplete_final_bar() -> None:
    issues = check_measure_durations(
        "melody = \\absolute { \\time 4/4 c'2 d'2 c'1 }"
    )
    assert [item.code for item in issues] == ["FINAL_BAR_DURATION"]
    assert issues[0].details["actual"] == "2"
