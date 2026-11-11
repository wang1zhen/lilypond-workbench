from pathlib import Path

import pytest
import yaml

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.parts import build_manifest, extract_parts, write_manifest


SCORE = r'''\version "2.24.4"
global = { \time 4/4 }
violinIMusic = \relative c'' { \global c1 | }
celloMusic = \relative c { \global \clef bass c1 | }
\score {
  \new StaffGroup <<
    \new Staff \with { instrumentName = "Violin I" } \violinIMusic
    \new Staff \with { instrumentName = "Cello" } \celloMusic
  >>
  \layout { }
}
'''


def test_manifest_maps_staffs(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest, diagnostics = build_manifest(source)
    assert manifest["schema_version"] == 3
    assert [item["id"] for item in manifest["parts"]] == ["violin-i", "cello"]
    assert manifest["parts"][1]["instrument"] == "cello"
    assert manifest["parts"][1]["pitch_basis"] == "concert"
    assert manifest["parts"][1]["clef"] == {"initial": "bass", "policy": "suggest"}
    assert not diagnostics


def test_extracts_shared_source_and_wrappers(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest_path = tmp_path / "parts.yaml"
    result = write_manifest(source, manifest_path)
    assert result.ok
    result = extract_parts(manifest_path, output_dir=tmp_path / "parts")
    assert result.ok
    shared = (tmp_path / "parts" / "_shared.ily").read_text(encoding="utf-8")
    assert "violinIMusic" in shared
    assert "\\score" not in shared
    assert (tmp_path / "parts" / "violin-i.ly").is_file()
    assert (tmp_path / "parts" / "cello.clefs.json").is_file()
    with pytest.raises(WorkbenchError, match="already exists"):
        extract_parts(manifest_path, output_dir=tmp_path / "parts")


def test_schema_v1_keeps_preserve_behavior(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        """schema_version: 1
source: score.ly
parts:
  - id: cello
    name: Cello
    variable: celloMusic
    staff_type: Staff
    clef: bass
""",
        encoding="utf-8",
    )

    result = extract_parts(manifest, output_dir=tmp_path / "v1-parts")

    assert result.ok
    wrapper = (tmp_path / "v1-parts" / "cello.ly").read_text(encoding="utf-8")
    assert "\\clef bass" in wrapper
    assert "workbenchCelloClefs" not in wrapper
    assert not (tmp_path / "v1-parts" / "cello.clefs.json").exists()


def test_auto_policy_adds_a_generated_clef_track(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(
        r'''\version "2.24.4"
celloMusic = \absolute { \time 4/4 \clef bass c4 d e f | d'4 e' f' g' | a'4 b' c'' d'' | }
\score { \new Staff \with { instrumentName = "Cello" } \celloMusic }
''',
        encoding="utf-8",
    )
    manifest = tmp_path / "parts.yaml"
    manifest.write_text(
        """schema_version: 2
source: score.ly
parts:
  - id: cello
    name: Cello
    instrument: cello
    variable: celloMusic
    staff_type: Staff
    clef: {initial: bass, policy: auto}
""",
        encoding="utf-8",
    )

    result = extract_parts(manifest, output_dir=tmp_path / "auto-parts")

    assert result.ok
    wrapper = (tmp_path / "auto-parts" / "cello.ly").read_text(encoding="utf-8")
    assert "workbenchCelloClefs" in wrapper
    assert "\\clef tenor" in wrapper
    assert "\\clef treble" in wrapper
    assert (tmp_path / "auto-parts" / "cello.clefs.json").is_file()


def _write_v1_manifest(path: Path, parts: list[dict[str, str]]) -> None:
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "source": "score.ly", "parts": parts}),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "part_id",
    ["", " ", ".", "..", "../escape", "nested/id", r"nested\id", "/tmp/evil", "_shared", "_SHARED"],
)
def test_manifest_rejects_unsafe_part_ids(tmp_path: Path, part_id: str) -> None:
    manifest = tmp_path / "parts.yaml"
    _write_v1_manifest(manifest, [{"id": part_id, "name": "Violin", "variable": "violinIMusic"}])

    with pytest.raises(WorkbenchError) as excinfo:
        extract_parts(manifest, output_dir=tmp_path / "parts")

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert excinfo.value.exit_code == 2


def test_manifest_rejects_duplicate_part_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "parts.yaml"
    _write_v1_manifest(
        manifest,
        [
            {"id": "violin", "name": "Violin", "variable": "violinIMusic"},
            {"id": "violin", "name": "Cello", "variable": "celloMusic"},
        ],
    )

    with pytest.raises(WorkbenchError, match="Duplicate part id"):
        extract_parts(manifest, output_dir=tmp_path / "parts")


def test_force_does_not_write_outside_destination(tmp_path: Path) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    destination = tmp_path / "out" / "parts"
    destination.mkdir(parents=True)
    victim = tmp_path / "victim.ly"
    victim.write_text("ORIGINAL", encoding="utf-8")
    manifest = tmp_path / "parts.yaml"
    _write_v1_manifest(manifest, [{"id": "../../victim", "name": "Violin", "variable": "violinIMusic"}])

    with pytest.raises(WorkbenchError) as excinfo:
        extract_parts(manifest, output_dir=destination, force=True)

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert victim.read_text(encoding="utf-8") == "ORIGINAL"


def test_source_is_relative_to_manifest_directory_for_cross_dir_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "score"
    source_dir.mkdir()
    source = source_dir / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    manifest = tmp_path / "config" / "parts.yaml"

    assert write_manifest(source, manifest).ok
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["source"] == "../score/score.ly"

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    extracted = extract_parts(manifest)

    assert extracted.ok
    output = manifest.parent / "build" / "parts"
    wrapper = output / "violin-i.ly"
    assert wrapper.is_file()
    assert (output / "_shared.ily").is_file()
    assert "_shared.ily" in wrapper.read_text(encoding="utf-8")


@pytest.mark.parametrize("output_name", ["", ".", "..", "../escape", "nested/id", r"nested\id", "/tmp/evil", None])
def test_manifest_rejects_unsafe_output_names(tmp_path: Path, output_name: str | None) -> None:
    manifest = tmp_path / "parts.yaml"
    _write_v1_manifest(
        manifest,
        [{"id": "violin", "name": "Violin", "variable": "violinIMusic", "output_name": output_name}],
    )

    with pytest.raises(WorkbenchError) as excinfo:
        extract_parts(manifest, output_dir=tmp_path / "parts")

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert excinfo.value.exit_code == 2


@pytest.mark.parametrize("target", ["_shared.ily", "violin-i.ly"])
def test_existing_symlink_escaping_destination_is_rejected(tmp_path: Path, target: str) -> None:
    source = tmp_path / "score.ly"
    source.write_text(SCORE, encoding="utf-8")
    destination = tmp_path / "parts"
    destination.mkdir()
    victim = tmp_path / "outside-target"
    victim.write_text("ORIGINAL", encoding="utf-8")
    (destination / target).symlink_to(victim)
    manifest = tmp_path / "parts.yaml"
    _write_v1_manifest(manifest, [{"id": "violin-i", "name": "Violin", "variable": "violinIMusic"}])

    with pytest.raises(WorkbenchError, match="escapes output directory") as excinfo:
        extract_parts(manifest, output_dir=destination, force=True)

    assert excinfo.value.code == "MANIFEST_SCHEMA"
    assert victim.read_text(encoding="utf-8") == "ORIGINAL"
