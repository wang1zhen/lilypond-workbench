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
    assert [item["id"] for item in manifest["parts"]] == ["violin-i", "cello"]
    assert manifest["parts"][1]["clef"] == "bass"
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
    with pytest.raises(WorkbenchError, match="already exists"):
        extract_parts(manifest_path, output_dir=tmp_path / "parts")
