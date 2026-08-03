from pathlib import Path
import shutil

import pytest

from lilypond_workbench.documents import build_document
from lilypond_workbench.harmony import analyze_harmony
from lilypond_workbench.importers import import_score
from lilypond_workbench.parts import extract_parts, write_manifest
from lilypond_workbench.rendering import batch_render, render_file, validate_file


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.parametrize(
    "template",
    sorted((ROOT / "assets" / "templates").glob("*.ly")),
    ids=lambda path: path.stem,
)
def test_template_compiles(template: Path, tmp_path: Path) -> None:
    result = render_file(template, output_dir=tmp_path, timeout=90)
    assert result.ok, result.metadata.get("stderr")
    assert any(Path(path).suffix == ".pdf" for path in result.artifacts)


@pytest.mark.integration
def test_import_musicxml_and_abc(tmp_path: Path) -> None:
    for fixture in (ROOT / "tests" / "fixtures" / "sample.musicxml", ROOT / "tests" / "fixtures" / "sample.abc"):
        output = tmp_path / f"{fixture.stem}-{fixture.suffix.lstrip('.')}.ly"
        imported = import_score(fixture, output_path=output)
        assert imported.ok
        rendered = render_file(output, output_dir=tmp_path / fixture.stem)
        assert rendered.ok, rendered.metadata.get("stderr")


@pytest.mark.integration
def test_import_generated_midi(tmp_path: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "progression.ly"
    rendered = render_file(source, output_dir=tmp_path / "midi-source")
    midi = next(Path(path) for path in rendered.artifacts if Path(path).suffix in {".mid", ".midi"})
    imported = import_score(midi, output_path=tmp_path / "from-midi.ly")
    assert imported.ok
    assert (tmp_path / "from-midi.ly").is_file()


@pytest.mark.integration
def test_batch_render_and_failed_validation(tmp_path: Path) -> None:
    batch = batch_render(
        [ROOT / "assets" / "templates" / "single-staff.ly", ROOT / "assets" / "templates" / "piano.ly"],
        output_dir=tmp_path / "batch",
    )
    assert batch.ok
    assert len([path for path in batch.artifacts if Path(path).suffix == ".pdf"]) == 2
    invalid = validate_file(ROOT / "tests" / "fixtures" / "broken.ly")
    assert not invalid.ok
    assert any(item.severity == "error" for item in invalid.diagnostics)


@pytest.mark.integration
def test_part_extraction_compiles(tmp_path: Path) -> None:
    source = tmp_path / "parts-project.ly"
    shutil.copyfile(ROOT / "assets" / "templates" / "parts-project.ly", source)
    manifest = tmp_path / "parts.yaml"
    assert write_manifest(source, manifest).ok
    extracted = extract_parts(manifest, output_dir=tmp_path / "parts", compile_parts=True)
    assert extracted.ok
    assert len([path for path in extracted.artifacts if Path(path).suffix == ".pdf"]) == 3


@pytest.mark.integration
def test_harmony_analysis_from_lilypond(tmp_path: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "progression.ly"
    output = tmp_path / "harmony.ily"
    result = analyze_harmony(source, output_path=output, key_override="C")
    assert result.ok
    assert output.is_file()
    assert "workbenchChordNames" in output.read_text(encoding="utf-8")
    assert output.with_suffix(".analysis.json").is_file()
    combined = tmp_path / "analyzed-score.ly"
    combined.write_text(
        '\\version "2.24.4"\n'
        f'\\include "{output.as_posix()}"\n'
        'melody = \\relative c\' { c1 | f | g | c | }\n'
        '\\score { <<\n'
        '  \\new ChordNames \\workbenchChordNames\n'
        '  \\new Staff <<\n'
        '    \\new Voice = "music" \\melody\n'
        '    \\new NullVoice = "analysis" \\workbenchRomanRhythm\n'
        '    \\new Lyrics \\lyricsto "analysis" \\workbenchRomanNumerals\n'
        '  >>\n'
        '>> \\layout { } }\n',
        encoding="utf-8",
    )
    rendered = render_file(combined, output_dir=tmp_path / "analyzed")
    assert rendered.ok, rendered.metadata.get("stderr")


@pytest.mark.integration
def test_latex_document_build(tmp_path: Path) -> None:
    source = ROOT / "assets" / "documents" / "article.lytex"
    result = build_document(source, output_dir=tmp_path, timeout=180)
    assert result.ok, result.metadata.get("stderr")
    assert (tmp_path / "article.pdf").is_file()
