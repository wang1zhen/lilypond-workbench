from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from lilypond_workbench.parts import extract_parts, write_manifest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_cross_directory_part_extraction_compiles(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source_dir = project / "source"
    source_dir.mkdir(parents=True)
    source = source_dir / "parts-project.ly"
    shutil.copyfile(ROOT / "assets" / "templates" / "parts-project.ly", source)
    manifest = project / "config" / "parts.yaml"

    assert write_manifest(source, manifest).ok
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["source"] == "../source/parts-project.ly"

    output = project / "build" / "parts"
    extracted = extract_parts(manifest, output_dir=output, compile_parts=True)

    assert extracted.ok
    for part_id in ("violin-i", "viola", "cello"):
        assert (output / f"{part_id}.pdf").is_file()
