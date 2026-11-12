from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lilypond_workbench.rendering import validate_file


@pytest.mark.integration
def test_real_version_mismatch_is_not_reported_as_missing_include(tmp_path: Path) -> None:
    if shutil.which("lilypond") is None:
        pytest.skip("LilyPond is not installed")
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "violin1.ily").write_text(
        "violinOne = \\relative c' { c4 d e f }\n", encoding="utf-8"
    )
    score = tmp_path / "haruhikage.ly"
    score.write_text(
        '\\version "999.0.0"\n\\include "parts/violin1.ily"\n\\score { \\new Staff \\violinOne }\n',
        encoding="utf-8",
    )

    result = validate_file(score)

    assert not result.ok
    codes = {issue.code for issue in result.diagnostics}
    assert "VERSION_MISMATCH" in codes
    assert "INCLUDE_NOT_FOUND" not in codes
    assert any(issue.severity == "error" and "failed files" in issue.message for issue in result.diagnostics)


@pytest.mark.integration
def test_real_missing_include_is_still_reported(tmp_path: Path) -> None:
    if shutil.which("lilypond") is None:
        pytest.skip("LilyPond is not installed")
    score = tmp_path / "missing.ly"
    score.write_text(
        '\\version "2.24.4"\n\\include "parts/does-not-exist.ily"\n\\score { \\new Staff { c4 d } }\n',
        encoding="utf-8",
    )

    result = validate_file(score)

    assert not result.ok
    include_issues = [issue for issue in result.diagnostics if issue.code == "INCLUDE_NOT_FOUND"]
    assert len(include_issues) == 1
    assert "does-not-exist.ily" in include_issues[0].message
    assert any(issue.severity == "error" and "failed files" in issue.message for issue in result.diagnostics)
