from pathlib import Path

import pytest

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
