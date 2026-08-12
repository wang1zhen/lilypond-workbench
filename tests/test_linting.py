import json
from pathlib import Path

from lilypond_workbench.linting import lint_score


def _score(tmp_path: Path) -> Path:
    source = tmp_path / "score.ly"
    source.write_text(
        r"""\version "2.24.4"
violinMusic = \absolute { \time 4/4 c'''''1 | }
\score { \new Staff \violinMusic }
""",
        encoding="utf-8",
    )
    return source


def _manifest(tmp_path: Path, *, suppression: bool = False) -> Path:
    path = tmp_path / "parts.yaml"
    suffix = """
suppressions:
  - rule_id: range.above-absolute
    part: violin
    reason: Intentional extended-technique test
""" if suppression else ""
    path.write_text(
        """schema_version: 3
source: score.ly
parts:
  - id: violin
    name: Violin
    instrument: violin
    variable: violinMusic
    pitch_basis: written
    staff_type: Staff
    clef: {initial: treble, policy: suggest}
""" + suffix,
        encoding="utf-8",
    )
    return path


def test_lint_reports_absolute_range_and_writes_schema(tmp_path: Path) -> None:
    source = _score(tmp_path)
    output = tmp_path / "lint.json"

    result = lint_score(source, manifest_path=_manifest(tmp_path), output_path=output, static_only=True)

    assert not result.ok
    report = json.loads(output.read_text(encoding="utf-8"))
    finding = next(item for item in report["findings"] if item["rule_id"] == "range.above-absolute")
    assert finding["severity"] == "error"
    assert finding["pitch_basis"] == "written"
    assert finding["measure"] == 1


def test_lint_suppression_requires_reason_and_does_not_fail(tmp_path: Path) -> None:
    source = _score(tmp_path)

    result = lint_score(source, manifest_path=_manifest(tmp_path, suppression=True), static_only=True)

    assert result.ok
    assert result.metadata["report"]["summary"]["suppressed"] == 1


def test_fail_on_warning_controls_exit_status(tmp_path: Path) -> None:
    source = tmp_path / "warning.ly"
    source.write_text(r"""music = \absolute { e''''1 | }""", encoding="utf-8")
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        """schema_version: 3
source: warning.ly
parts:
  - id: violin
    name: Violin
    instrument: violin
    variable: music
    pitch_basis: written
    clef: {initial: treble, policy: suggest}
""",
        encoding="utf-8",
    )

    default = lint_score(source, manifest_path=manifest, static_only=True)
    strict = lint_score(source, manifest_path=manifest, static_only=True, fail_on="warning")

    assert default.ok
    assert not strict.ok


def test_broken_source_still_returns_combined_lint_report(tmp_path: Path) -> None:
    source = tmp_path / "broken.ly"
    source.write_text("music = { c1\n\\score { \\new Staff \\music }\n", encoding="utf-8")

    result = lint_score(source, static_only=True)

    assert not result.ok
    rules = {item["rule_id"] for item in result.metadata["report"]["findings"]}
    assert "structure.unmatched-delimiter" in rules
    assert "compiler.unmatched-delimiter" in rules


def test_unused_suppression_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text("music = { c'1 | }\n", encoding="utf-8")
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        """schema_version: 3
source: score.ly
parts:
  - id: violin
    name: Violin
    instrument: violin
    variable: music
    pitch_basis: written
    clef: {initial: treble, policy: suggest}
suppressions:
  - rule_id: range.above-practical
    part: violin
    reason: Kept to verify stale suppression detection
""",
        encoding="utf-8",
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    rules = {item["rule_id"] for item in result.metadata["report"]["findings"]}
    assert "lint.unused-suppression" in rules
