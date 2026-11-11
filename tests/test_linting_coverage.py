"""Focused lint coverage: pitch/transpose boundaries, manifest drift, rules, suppressions."""

import json
from pathlib import Path

import pytest
import yaml

from lilypond_workbench.cli import main
from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.linting import INSTRUMENT_RANGES, _manifest_diagnostics, _ranges, lint_score


def _source(tmp_path: Path, body: str, name: str = "score.ly") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _part(**overrides: object) -> dict:
    part = {
        "id": "violin",
        "name": "Violin",
        "instrument": "violin",
        "variable": "music",
        "pitch_basis": "written",
        "staff_type": "Staff",
        "clef": {"initial": "treble", "policy": "suggest"},
    }
    part.update(overrides)
    return part


def _manifest(
    tmp_path: Path,
    parts: list[dict],
    *,
    source: str = "score.ly",
    suppressions: list[dict] | None = None,
    name: str = "parts.yaml",
) -> Path:
    payload: dict = {"schema_version": 3, "source": source, "parts": parts}
    if suppressions is not None:
        payload["suppressions"] = suppressions
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _rules(result) -> set[str]:
    return {item["rule_id"] for item in result.metadata["report"]["findings"]}


def _finding(result, rule_id: str) -> dict:
    return next(item for item in result.metadata["report"]["findings"] if item["rule_id"] == rule_id)


def _assert_schema_error(source: Path, manifest: Path) -> WorkbenchError:
    with pytest.raises(WorkbenchError) as excinfo:
        lint_score(source, manifest_path=manifest, static_only=True)
    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert excinfo.value.exit_code == 2
    return excinfo.value


def test_unknown_instrument_reports_info_and_no_range(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(id="mystery", name="Mystery", instrument=None, clef={"initial": "treble", "policy": "preserve"})],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert result.ok
    finding = _finding(result, "range.unknown-instrument")
    assert finding["severity"] == "info"
    assert finding["details"] == {"part": "mystery", "instrument": None}


def test_range_override_merges_default_ranges(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c1 c'1 }""")
    part = _part(range_override={"absolute": {"low": "C3", "high": "A7"}})
    manifest = _manifest(tmp_path, [part])

    # Default violin practical range survives; only the absolute boundary is overridden.
    assert _ranges(part) == {"practical": (25, 50), "absolute": (21, 54)}

    result = lint_score(source, manifest_path=manifest, static_only=True)

    # C3 (21) is below the default absolute low (24) but inside the override, so the
    # default practical range must still flag it as a warning rather than an error.
    assert result.ok
    range_rules = {rule for rule in _rules(result) if rule.startswith("range.")}
    assert range_rules == {"range.below-practical"}
    assert _finding(result, "range.below-practical")["details"]["pitch"] == "C3"


def test_range_override_without_scientific_pitches_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": 3, "high": "C6"}})],
    )

    error = _assert_schema_error(source, manifest)

    assert "requires low and high scientific pitches" in str(error)


def test_unknown_instrument_override_needs_both_ranges(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [
            _part(
                id="mystery",
                name="Mystery",
                instrument=None,
                clef={"initial": "treble", "policy": "preserve"},
                range_override={"practical": {"low": "C4", "high": "C5"}},
            )
        ],
    )

    error = _assert_schema_error(source, manifest)

    assert "needs both practical and absolute ranges" in str(error)


def test_inconsistent_range_override_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "C6", "high": "C5"}})],
    )

    error = _assert_schema_error(source, manifest)

    assert "range boundaries are inconsistent" in str(error)


def test_invalid_scientific_pitch_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "H4", "high": "C5"}})],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid scientific pitch: H4" in str(error)


def test_ranges_rejects_non_mapping_override() -> None:
    with pytest.raises(WorkbenchError) as excinfo:
        _ranges({"id": "violin", "instrument": "violin", "range_override": []})

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert excinfo.value.exit_code == 2


def test_concert_transpose_shifts_written_pitch(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c''''1 }""")
    manifest = _manifest(
        tmp_path,
        [
            _part(
                pitch_basis="concert",
                transpose={"from": "c'", "to": "c''"},
            )
        ],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "range.above-absolute")
    assert finding["details"]["written_pitch_shift"] == 7
    assert finding["details"]["pitch"] == "C8"


def test_invalid_transpose_pitch_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(pitch_basis="concert", transpose={"from": "h", "to": "c'"})],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid LilyPond transpose pitch: h" in str(error)


def test_written_basis_invalid_transpose_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(pitch_basis="written", transpose={"from": "h", "to": "c'"})],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid LilyPond transpose pitch: h" in str(error)


def test_unknown_instrument_invalid_transpose_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [
            _part(
                id="mystery",
                name="Mystery",
                instrument=None,
                clef={"initial": "treble", "policy": "preserve"},
                transpose={"from": "h", "to": "c'"},
            )
        ],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid LilyPond transpose pitch: h" in str(error)


def test_written_transpose_is_not_applied(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c''''1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(pitch_basis="written", transpose={"from": "c'", "to": "c''"})],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert not any(rule.startswith("range.") for rule in _rules(result))


def test_missing_variable_cannot_suppress_invalid_range(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(variable="missingMusic", range_override={"practical": {"low": "H4", "high": "C5"}})],
        suppressions=[{"rule_id": "parts.variable-not-found", "part": "violin", "reason": "hide it"}],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid scientific pitch: H4" in str(error)


def test_broken_source_cannot_hide_invalid_config(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1\n")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "H4", "high": "C5"}})],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid scientific pitch: H4" in str(error)


def test_non_schema_index_error_is_aggregated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(tmp_path, [_part()])

    def fail(*args: object, **kwargs: object) -> None:
        raise WorkbenchError("variable is not music", "VARIABLE_NOT_MUSIC")

    monkeypatch.setattr("lilypond_workbench.linting.build_semantic_index", fail)

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "semantic.index-failed")
    assert finding["severity"] == "error"
    assert "variable is not music" in finding["message"]
    assert finding["details"]["part"] == "violin"


def test_schema_error_from_index_is_reraised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(tmp_path, [_part()])

    def fail(*args: object, **kwargs: object) -> None:
        raise WorkbenchError("invalid at index time", "MANIFEST_SCHEMA", exit_code=2)

    monkeypatch.setattr("lilypond_workbench.linting.build_semantic_index", fail)

    error = _assert_schema_error(source, manifest)

    assert "invalid at index time" in str(error)


def test_suppression_cannot_hide_manifest_schema_error(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "H4", "high": "C5"}})],
        suppressions=[{"rule_id": "semantic.index-failed", "part": "violin", "reason": "hide it"}],
    )

    error = _assert_schema_error(source, manifest)

    assert "Invalid scientific pitch: H4" in str(error)


def test_below_absolute_range(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c1 }""")
    manifest = _manifest(tmp_path, [_part()])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "range.below-absolute")
    assert finding["severity"] == "error"
    assert finding["details"]["pitch"] == "C3"


def test_below_practical_range_skips_rests(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { \time 4/4 r4 g4 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "C4", "high": "C5"}})],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "range.below-practical")
    assert finding["severity"] == "warning"
    assert finding["details"]["pitch"] == "G3"


def test_above_practical_range(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { \time 4/4 g''1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "C4", "high": "C5"}})],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "range.above-practical")
    assert finding["severity"] == "warning"
    assert finding["details"]["pitch"] == "G5"


def test_source_without_music_variables_warns(tmp_path: Path) -> None:
    source = _source(tmp_path, '\\version "2.24.4"\n')

    result = lint_score(source, static_only=True)

    assert result.ok
    assert "structure.no-music-variable" in _rules(result)


def test_duplicate_music_variable_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\nmusic = { d'1 }\n")

    result = lint_score(source, static_only=True)

    finding = _finding(result, "structure.duplicate-variable")
    assert finding["severity"] == "error"
    assert finding["location"]["line"] == 2


def test_missing_include_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, 'music = { c\'1 }\n\\include "missing.ly"\n')

    result = lint_score(source, static_only=True)

    finding = _finding(result, "structure.include-not-found")
    assert finding["location"]["line"] == 2
    assert "missing.ly" in finding["message"]


def test_manifest_with_broken_source_still_reports_structure_error(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1\n")
    manifest = _manifest(tmp_path, [_part()])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert not result.ok
    assert "structure.unmatched-delimiter" in _rules(result)


def test_duplicate_output_name_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\nother = { d'1 }\n")
    manifest = _manifest(
        tmp_path,
        [
            _part(id="first", variable="music", output_name="same"),
            _part(id="second", variable="other", output_name="same"),
        ],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "parts.duplicate-output")
    assert finding["details"]["part"] == "second"


def test_duplicate_part_id_is_reported_directly(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = {
        "parts": [
            _part(id="same", output_name="first"),
            _part(id="same", output_name="second"),
        ]
    }

    diagnostics = _manifest_diagnostics(source, manifest)

    assert [item.code for item in diagnostics if item.code == "PARTS_DUPLICATE_ID"] == ["PARTS_DUPLICATE_ID"]


def test_undeclared_tag_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = _manifest(tmp_path, [_part(tags=["tutti"])])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "parts.tag-not-found")
    assert finding["details"] == {"part": "violin", "tag": "tutti"}


def test_missing_variable_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = _manifest(tmp_path, [_part(variable="missingMusic")])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "parts.variable-not-found")
    assert finding["details"]["part"] == "violin"
    assert "missingMusic" in finding["message"]


def test_semantic_diagnostic_is_carried_into_lint(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = { \tempo 4 = 96 \repeat volta 2 { c'4 d' e' f' } }""")
    manifest = _manifest(tmp_path, [_part()])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "semantic.semantic-repeat-dropped")
    assert finding["severity"] == "warning"
    assert finding["details"]["part"] == "violin"


def test_clef_diagnostic_is_carried_into_lint(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { \time 4/4 \clef alto c'4 d' e' f' }""")
    manifest = _manifest(tmp_path, [_part()])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "clef.clef-nonstandard")
    assert finding["severity"] == "warning"
    assert finding["details"]["part"] == "violin"


def test_suppression_rule_and_part_mismatch_become_unused(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'''''1 }""")
    manifest = _manifest(
        tmp_path,
        [_part()],
        suppressions=[
            {"rule_id": "range.below-practical", "part": "violin", "reason": "wrong rule"},
            {"rule_id": "range.above-absolute", "part": "cello", "reason": "wrong part"},
        ],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    report = result.metadata["report"]
    assert report["summary"]["suppressed"] == 0
    assert [item["rule_id"] for item in report["findings"]].count("lint.unused-suppression") == 2


def test_string_practical_ranges_match_reference() -> None:
    assert INSTRUMENT_RANGES["violin"] == {"practical": (25, 50), "absolute": (24, 52)}
    assert INSTRUMENT_RANGES["viola"] == {"practical": (21, 44), "absolute": (21, 47)}


def test_violin_practical_boundary_pitches(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { \time 4/4 g4 d''''4 f4 e''''4 }""")
    manifest = _manifest(tmp_path, [_part()])

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert _finding(result, "range.below-practical")["details"]["pitch"] == "F3"
    assert _finding(result, "range.above-practical")["details"]["pitch"] == "E7"
    assert "range.below-absolute" not in _rules(result)
    assert "range.above-absolute" not in _rules(result)


def test_viola_practical_boundary_pitches(tmp_path: Path) -> None:
    source = _source(tmp_path, r"""music = \absolute { \time 4/4 c4 e'''4 f'''4 b,4 }""")
    manifest = _manifest(
        tmp_path,
        [_part(id="viola", name="Viola", instrument="viola", clef={"initial": "alto", "policy": "suggest"})],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert _finding(result, "range.above-practical")["details"]["pitch"] == "F6"
    assert _finding(result, "range.below-absolute")["details"]["pitch"] == "B2"
    assert "range.below-practical" not in _rules(result)
    assert "range.above-absolute" not in _rules(result)


def test_cli_lint_manifest_schema_error_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path, r"""music = \absolute { c'1 }""")
    manifest = _manifest(
        tmp_path,
        [_part(range_override={"practical": {"low": "H4", "high": "C5"}})],
    )
    # cli.main writes the runner into os.environ; register it so teardown restores the caller's value.
    monkeypatch.setenv("LILYPOND_WORKBENCH_RUNNER", "native")

    code = main(["lint", str(source), "--manifest", str(manifest), "--static-only", "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "MANIFEST_SCHEMA"
    assert "Invalid scientific pitch: H4" in payload["diagnostics"][0]["message"]


def test_invalid_fail_on_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")

    with pytest.raises(WorkbenchError) as excinfo:
        lint_score(source, fail_on="critical", static_only=True)

    assert excinfo.value.code == "INVALID_ARGUMENT"
    assert excinfo.value.exit_code == 2


def test_manifest_source_mismatch_is_reported(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = _manifest(tmp_path, [_part()], source="other.ly")

    result = lint_score(source, manifest_path=manifest, static_only=True)

    finding = _finding(result, "parts.source-mismatch")
    assert finding["severity"] == "error"
    assert finding["location"]["file"] == str(manifest)


@pytest.mark.parametrize(
    "overrides",
    [
        {"range_override": {"practical": {"low": "H4", "high": "C5"}}},
        {"transpose": {"from": "h", "to": "c'"}},
    ],
    ids=["invalid-range", "invalid-transpose"],
)
def test_source_mismatch_cannot_hide_invalid_config(tmp_path: Path, overrides: dict) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = _manifest(
        tmp_path,
        [_part(**overrides)],
        source="other.ly",
        suppressions=[{"rule_id": "parts.source-mismatch", "reason": "hide it"}],
    )

    _assert_schema_error(source, manifest)


def test_valid_config_still_allows_source_mismatch_suppression(tmp_path: Path) -> None:
    source = _source(tmp_path, "music = { c'1 }\n")
    manifest = _manifest(
        tmp_path,
        [_part()],
        source="other.ly",
        suppressions=[{"rule_id": "parts.source-mismatch", "reason": "intentional"}],
    )

    result = lint_score(source, manifest_path=manifest, static_only=True)

    assert result.ok
    report = result.metadata["report"]
    assert report["summary"]["suppressed"] == 1
    assert _finding(result, "parts.source-mismatch")["suppressed"] is True
