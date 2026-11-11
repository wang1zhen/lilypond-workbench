import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from lilypond_workbench import parts
from lilypond_workbench.common import Diagnostic, Result, WorkbenchError
from lilypond_workbench.parts import build_manifest, extract_parts, normalize_manifest, write_manifest


SCORE = r'''\version "2.24.4"
violinMusic = \relative c'' { c4 d e f | }
\score {
  \new Staff \with { instrumentName = "Violin" } \violinMusic
}
'''

ENSEMBLE = r'''\version "2.24.4"
fluteMusic = \relative c'' { c4 d e f | }
violaMusic = \relative c' { c4 d e f | }
drumMusic = \drummode { bd4 sn bd sn | }
extraMusic = { c1 }
\score {
  \new Staff \with { instrumentName = "Flute" } \fluteMusic
  \new Staff \with { instrumentName = "Viola" } \violaMusic
  \new Staff \with { instrumentName = "Drum" } \drumMusic
  \new Staff { c1 }
}
'''


def _write_manifest(
    tmp_path: Path,
    parts: list[dict[str, Any]],
    *,
    version: int = 2,
    source: str = "score.ly",
) -> Path:
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        yaml.safe_dump({"schema_version": version, "source": source, "parts": parts}),
        encoding="utf-8",
    )
    return manifest


def test_build_manifest_guesses_unknown_viola_and_percussion(tmp_path: Path) -> None:
    source = tmp_path / "ensemble.ly"
    source.write_text(ENSEMBLE, encoding="utf-8")

    manifest, diagnostics = build_manifest(source)

    by_id = {part["id"]: part for part in manifest["parts"]}
    assert by_id["flute"]["instrument"] is None
    assert by_id["flute"]["clef"] == {"initial": "treble", "policy": "preserve"}
    assert by_id["viola"]["instrument"] == "viola"
    assert by_id["viola"]["clef"] == {"initial": "alto", "policy": "suggest"}
    assert by_id["drum"]["instrument"] is None
    assert by_id["drum"]["clef"] == {"initial": "percussion", "policy": "preserve"}
    assert by_id["extra"]["needs_review"] is True
    assert [item.code for item in diagnostics] == ["PART_MAPPING_REVIEW"]
    assert "extraMusic" in diagnostics[0].message


def test_extract_parts_warns_about_needs_review_parts(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(
        r'''\version "2.24.4"
orphanMusic = \relative c' { c1 }
violinMusic = \relative c'' { c1 }
\score { \new Staff \with { instrumentName = "Violin" } \violinMusic }
''',
        encoding="utf-8",
    )
    manifest = tmp_path / "parts.yaml"
    assert write_manifest(source, manifest).ok

    result = extract_parts(manifest, output_dir=tmp_path / "parts")

    assert result.ok
    assert any(
        item.code == "PART_MAPPING_REVIEW" and "orphan" in item.message for item in result.diagnostics
    )


def test_wrapper_applies_transposition_and_tag_filter(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "id": "violin",
                "name": "Violin",
                "variable": "violinMusic",
                "transpose": {"from": "c", "to": "d"},
                "tags": ["solo", "tutti"],
            }
        ],
    )

    result = extract_parts(manifest, output_dir=tmp_path / "parts")

    assert result.ok
    wrapper = (tmp_path / "parts" / "violin.ly").read_text(encoding="utf-8")
    assert "\\transpose c d { \\violinMusic }" in wrapper
    assert "\\keepWithTag #'(solo tutti) { \\transpose c d { \\violinMusic } }" in wrapper
    assert result.metadata == {"parts": 1, "manifest_schema": 2}


def test_normalize_reads_string_clef_and_guesses_missing_clef() -> None:
    normalized = normalize_manifest(
        {
            "schema_version": 2,
            "parts": [
                {"id": "alto", "name": "Alto", "variable": "altoMusic", "clef": "alto"},
                {"id": "cello", "name": "Cello", "variable": "celloMusic", "clef": 42},
            ],
        }
    )

    assert normalized["schema_version"] == 3
    assert normalized["parts"][0]["clef"] == {"initial": "alto", "policy": "preserve"}
    assert normalized["parts"][1]["clef"] == {"initial": "bass", "policy": "preserve"}


def _part(**overrides: Any) -> dict[str, Any]:
    part: dict[str, Any] = {"id": "violin", "name": "Violin", "variable": "violinMusic"}
    part.update(overrides)
    return part


@pytest.mark.parametrize(
    ("manifest", "match"),
    [
        pytest.param([], "schema_version: 1, 2, or 3", id="not-a-mapping"),
        pytest.param({"schema_version": 4, "parts": []}, "schema_version: 1, 2, or 3", id="unknown-version"),
        pytest.param({"schema_version": 3, "parts": {}}, "contain a parts list", id="parts-not-list"),
        pytest.param({"schema_version": 3, "parts": ["violin"]}, "requires id, name, and variable", id="part-not-mapping"),
        pytest.param(
            {"schema_version": 3, "parts": [{"id": "violin", "name": "Violin"}]},
            "requires id, name, and variable",
            id="part-missing-variable",
        ),
        pytest.param(
            {"schema_version": 2, "parts": [_part(clef={"initial": "treble", "policy": "bogus"})]},
            "invalid clef policy",
            id="invalid-clef-policy",
        ),
        pytest.param(
            {
                "schema_version": 2,
                "parts": [_part(clef={"initial": "treble", "policy": "suggest"}, instrument="flute")],
            },
            "requires instrument violin, viola, or cello",
            id="clef-policy-without-string-instrument",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part()]},
            "requires pitch_basis in schema v3",
            id="v3-missing-pitch-basis",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="transposed")]},
            "invalid pitch_basis",
            id="invalid-pitch-basis",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="concert", transpose={"from": "c"})]},
            "transpose requires string from and to pitches",
            id="transpose-missing-to",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="concert", transpose=["c", "d"])]},
            "transpose requires string from and to pitches",
            id="transpose-not-mapping",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="concert", tags="solo")]},
            "tags must be a list of strings",
            id="tags-not-list",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="concert", tags=["solo", ""])]},
            "tags must be a list of strings",
            id="tags-empty-string",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [_part(pitch_basis="concert", range_override="low")]},
            "range_override must be a mapping",
            id="range-override-not-mapping",
        ),
        pytest.param({"schema_version": 3, "parts": [], "suppressions": {}}, "suppressions must be a list", id="suppressions-not-list"),
        pytest.param({"schema_version": 3, "parts": [], "suppressions": ["x"]}, "Each suppression", id="suppression-not-mapping"),
        pytest.param(
            {"schema_version": 3, "parts": [], "suppressions": [{"rule_id": "parts.tag-not-found"}]},
            "Each suppression",
            id="suppression-missing-reason",
        ),
        pytest.param(
            {"schema_version": 3, "parts": [], "suppressions": [{"rule_id": "x", "reason": "   "}]},
            "Each suppression",
            id="suppression-blank-reason",
        ),
    ],
)
def test_normalize_manifest_rejects_schema_violations(manifest: Any, match: str) -> None:
    with pytest.raises(WorkbenchError, match=match) as excinfo:
        normalize_manifest(manifest)

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert excinfo.value.exit_code == 2


def test_extract_parts_reports_missing_source(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [_part()], source="missing.ly")

    with pytest.raises(WorkbenchError, match="Manifest source not found") as excinfo:
        extract_parts(manifest, output_dir=tmp_path / "parts")

    assert excinfo.value.code == "INPUT_NOT_FOUND"
    assert excinfo.value.exit_code == 2


def test_extract_parts_rejects_variables_not_available_outside_blocks(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = _write_manifest(tmp_path, [_part(variable="ghostMusic")])

    with pytest.raises(WorkbenchError, match="ghostMusic") as excinfo:
        extract_parts(manifest, output_dir=tmp_path / "parts")

    assert excinfo.value.code == "PARTS_UNSUPPORTED_STRUCTURE"
    assert not (tmp_path / "parts" / "_shared.ily").exists()


def test_compile_parts_renders_each_wrapper_and_aggregates_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = _write_manifest(tmp_path, [_part()])
    destination = tmp_path / "parts"
    calls: list[tuple[Path, Path, int]] = []

    def fake_render(input_path: Path, *, output_dir: Path, timeout: int) -> Result:
        calls.append((input_path, output_dir, timeout))
        return Result(
            True,
            "render",
            [str(input_path)],
            [str(output_dir / "violin.pdf")],
            [Diagnostic("warning", "RENDER_NOTE", "rendered")],
        )

    monkeypatch.setattr(parts, "render_file", fake_render)

    result = extract_parts(manifest, output_dir=destination, compile_parts=True, timeout=17)

    assert result.ok
    assert calls == [(destination.resolve() / "violin.ly", destination.resolve(), 17)]
    assert str(destination.resolve() / "violin.pdf") in result.artifacts
    assert any(item.code == "RENDER_NOTE" for item in result.diagnostics)


def test_compile_parts_failure_makes_the_result_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = _write_manifest(tmp_path, [_part()])

    def fake_render(input_path: Path, *, output_dir: Path, timeout: int) -> Result:
        return Result(False, "render", [], [], [Diagnostic("error", "LILYPOND_FAILED", "boom")])

    monkeypatch.setattr(parts, "render_file", fake_render)

    result = extract_parts(manifest, output_dir=tmp_path / "parts", compile_parts=True)

    assert not result.ok
    assert [item.code for item in result.diagnostics] == ["LILYPOND_FAILED"]


def test_write_manifest_as_json_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    output = tmp_path / "parts.json"

    result = write_manifest(source, output, as_json=True)

    assert result.ok
    assert result.metadata == {"parts": 1}
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["parts"][0]["variable"] == "violinMusic"
