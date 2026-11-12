"""Compiler cross-checks for the 2026-11-11 scores regressions."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lilypond_workbench.rendering import validate_file
from lilypond_workbench.semantic import build_semantic_index


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "tests" / "fixtures" / "scores-regressions"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected"),
    [("empty-chord.ly", "3/2"), ("after-dynamics.ly", "3/4")],
)
def test_fixture_duration_matches_the_compiler(name: str, expected: str) -> None:
    source = CASE / name

    result = validate_file(source)
    index = build_semantic_index(source, "music")

    assert result.ok, result.metadata.get("stderr")
    assert index.duration == Fraction(expected)
    assert f"EXPECTED {expected}; ACTUAL #<Mom {expected}>" in result.metadata["stderr"]


@pytest.mark.integration
def test_compiler_confirms_an_explicitly_lengthened_empty_chord_takes_no_time(tmp_path: Path) -> None:
    source = tmp_path / "empty-chord-duration.ly"
    source.write_text(
        '\\version "2.24.4"\n'
        "music = { \\time 4/4 r4 <>4 r4 }\n"
        '#(ly:message "EXPECTED 1/2; ACTUAL ~a" (ly:music-length music))\n'
        "\\score { \\new Staff { \\music \\barNumberCheck #2 } }\n",
        encoding="utf-8",
    )

    result = validate_file(source)

    assert result.ok, result.metadata.get("stderr")
    assert "EXPECTED 1/2; ACTUAL #<Mom 1/2>" in result.metadata["stderr"]
