"""Include-only entry manifests resolve variables through the semantic index."""

from pathlib import Path

import yaml

from lilypond_workbench.linting import lint_score


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _part(part_id: str, variable: str, instrument: str, clef: str) -> dict:
    return {
        "id": part_id,
        "name": part_id.title(),
        "instrument": instrument,
        "variable": variable,
        "pitch_basis": "written",
        "clef": {"initial": clef, "policy": "suggest"},
    }


def _lint(tmp_path: Path, parts: list[dict], source: str = "score.ly"):
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        yaml.safe_dump({"schema_version": 3, "source": source, "parts": parts}, sort_keys=False),
        encoding="utf-8",
    )
    return lint_score(tmp_path / source, manifest_path=manifest, static_only=True)


def _rules(result) -> list[str]:
    return [item["rule_id"] for item in result.metadata["report"]["findings"]]


def test_include_only_entry_resolves_voices_through_nested_includes(tmp_path: Path) -> None:
    _write(tmp_path / "score.ly", '\\version "2.24.4"\n\\include "parts/violin.ily"\n\\include "parts/ensemble.ily"\n')
    _write(tmp_path / "parts" / "violin.ily", r"violinMusic = \absolute { \time 4/4 c''1 }" + "\n")
    _write(tmp_path / "parts" / "ensemble.ily", '\\include "cello.ily"\n')
    _write(tmp_path / "parts" / "cello.ily", r"celloMusic = \absolute { c2 }" + "\n")

    result = _lint(
        tmp_path,
        [_part("violin", "violinMusic", "violin", "treble"), _part("cello", "celloMusic", "cello", "bass")],
    )

    assert result.ok
    assert "parts.variable-not-found" not in _rules(result)
    assert "semantic.index-failed" not in _rules(result)


def test_missing_variable_in_include_only_entry_is_still_reported(tmp_path: Path) -> None:
    _write(tmp_path / "score.ly", '\\include "parts/violin.ily"\n')
    _write(tmp_path / "parts" / "violin.ily", r"violinMusic = \absolute { c''1 }" + "\n")

    result = _lint(tmp_path, [_part("viola", "missingMusic", "viola", "alto")])

    assert not result.ok
    finding = next(item for item in result.metadata["report"]["findings"] if item["rule_id"] == "parts.variable-not-found")
    assert finding["details"]["part"] == "viola"
    assert "missingMusic" in finding["message"]


def test_repeated_include_is_not_reported_as_missing_or_ambiguous(tmp_path: Path) -> None:
    _write(
        tmp_path / "score.ly",
        '\\include "parts/violin.ily"\n\\include "parts/violin.ily"\n\\include "parts/ensemble.ily"\n',
    )
    _write(tmp_path / "parts" / "violin.ily", r"violinMusic = \absolute { c''1 }" + "\n")
    _write(tmp_path / "parts" / "ensemble.ily", '\\include "violin.ily"\n')

    result = _lint(tmp_path, [_part("violin", "violinMusic", "violin", "treble")])

    assert result.ok
    assert "parts.variable-not-found" not in _rules(result)
    assert "semantic.index-failed" not in _rules(result)


def test_variable_defined_in_two_included_files_is_ambiguous_not_missing(tmp_path: Path) -> None:
    _write(tmp_path / "score.ly", '\\include "parts/a.ily"\n\\include "parts/b.ily"\n')
    _write(tmp_path / "parts" / "a.ily", r"sharedMusic = \absolute { c''1 }" + "\n")
    _write(tmp_path / "parts" / "b.ily", r"sharedMusic = \absolute { d''1 }" + "\n")

    result = _lint(tmp_path, [_part("violin", "sharedMusic", "violin", "treble")])

    rules = _rules(result)
    assert "parts.variable-not-found" not in rules
    finding = next(item for item in result.metadata["report"]["findings"] if item["rule_id"] == "semantic.index-failed")
    assert "ambiguous" in finding["message"]


def test_missing_include_keeps_structure_diagnostic(tmp_path: Path) -> None:
    _write(tmp_path / "score.ly", '\\include "parts/missing.ily"\nmusic = \\absolute { c\'\'1 }\n')

    result = _lint(tmp_path, [_part("violin", "music", "violin", "treble")])

    assert not result.ok
    assert "structure.include-not-found" in _rules(result)
    assert "parts.variable-not-found" not in _rules(result)
