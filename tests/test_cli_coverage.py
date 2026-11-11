"""Routing and entry-point tests filling the remaining CLI contract paths.

Each subcommand is exercised through ``main()`` with its feature handler
mocked, so these tests assert the wiring (argument normalization, environment
selection, dispatch table) without running LilyPond or any external tool.
"""

from __future__ import annotations

import json
import runpy
import sys
import warnings
from pathlib import Path
from unittest.mock import Mock

import pytest

from lilypond_workbench import cli
from lilypond_workbench.common import Result


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def isolate_runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LILYPOND_WORKBENCH_RUNNER", "LILYPOND_WORKBENCH_CONTAINER_IMAGE"):
        # setenv registers the undo for both were-set and were-absent states;
        # delenv then gives the tests their documented clean environment.
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)


def envelope(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


def test_dispatch_routes_doctor(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    doctor = Mock(return_value=Result(True, "doctor"))

    monkeypatch.setattr(cli, "doctor", doctor)
    assert cli.main(["doctor", "--strict", "--json"]) == 0
    doctor.assert_called_once_with(strict=True)
    assert envelope(capsys)["command"] == "doctor"


def test_dispatch_routes_render_with_normalized_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "progression.ly"
    render = Mock(return_value=Result(True, "render"))

    monkeypatch.setattr(cli, "render_file", render)
    assert cli.main(
        [
            "render",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--format",
            "svg",
            "--resolution",
            "150",
            "--backend",
            "cairo",
            "--no-point-and-click",
            "--preview",
            "--timeout",
            "9",
            "--json",
        ]
    ) == 0
    render.assert_called_once_with(
        source.resolve(),
        output_dir=tmp_path / "out",
        fmt="svg",
        resolution=150,
        backend="cairo",
        no_point_and_click=True,
        preview=True,
        timeout=9,
    )
    assert envelope(capsys)["command"] == "render"


def test_dispatch_routes_batch_render_and_clamps_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "progression.ly"
    batch = Mock(return_value=Result(True, "batch-render"))

    monkeypatch.setattr(cli, "batch_render", batch)
    assert cli.main(
        [
            "batch-render",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--pattern",
            "*.ly",
            "--recursive",
            "--jobs",
            "0",
            "--continue-on-error",
            "--format",
            "png",
            "--resolution",
            "72",
            "--backend",
            "svg",
            "--no-point-and-click",
            "--preview",
            "--timeout",
            "5",
            "--json",
        ]
    ) == 0
    batch.assert_called_once_with(
        [source],
        output_dir=tmp_path / "out",
        pattern="*.ly",
        recursive=True,
        jobs=1,
        continue_on_error=True,
        fmt="png",
        resolution=72,
        backend="svg",
        no_point_and_click=True,
        preview=True,
        timeout=5,
    )
    assert envelope(capsys)["command"] == "batch-render"


def test_parse_log_reads_a_log_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "build.log"
    log.write_text("score.ly:3:5: error: syntax error\n", encoding="utf-8")
    assert cli.main(["parse-log", str(log), "--json"]) == 1
    payload = envelope(capsys)
    assert payload["inputs"] == [str(log.resolve())]
    assert payload["diagnostics"][0]["code"] == "SYNTAX_ERROR"


def test_dispatch_routes_import_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "sample.abc"
    output = tmp_path / "score.ly"
    importer = Mock(return_value=Result(True, "import-score"))

    monkeypatch.setattr(cli, "import_score", importer)
    assert cli.main(
        [
            "import-score",
            str(source),
            "--output",
            str(output),
            "--preserve-layout",
            "--preserve-beams",
            "--force",
            "--timeout",
            "7",
            "--json",
        ]
    ) == 0
    importer.assert_called_once_with(
        source.resolve(),
        output_path=output,
        force=True,
        preserve_layout=True,
        preserve_beams=True,
        timeout=7,
    )
    assert envelope(capsys)["command"] == "import-score"


def test_dispatch_routes_parts_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "progression.ly"
    output = tmp_path / "parts.yaml"
    manifest = Mock(return_value=Result(True, "parts-manifest"))

    monkeypatch.setattr(cli, "write_manifest", manifest)
    assert cli.main(
        ["parts-manifest", str(source), "--output", str(output), "--format", "json", "--force", "--json"]
    ) == 0
    manifest.assert_called_once_with(source.resolve(), output, force=True, as_json=True)
    assert envelope(capsys)["command"] == "parts-manifest"


def test_dispatch_routes_extract_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "parts.yaml"
    manifest.write_text("schema_version: 3\nparts: []\n", encoding="utf-8")
    extract = Mock(return_value=Result(True, "extract-parts"))

    monkeypatch.setattr(cli, "extract_parts", extract)
    assert cli.main(
        [
            "extract-parts",
            str(manifest),
            "--output-dir",
            str(tmp_path / "parts"),
            "--compile",
            "--force",
            "--timeout",
            "8",
            "--json",
        ]
    ) == 0
    extract.assert_called_once_with(
        manifest.resolve(),
        output_dir=tmp_path / "parts",
        compile_parts=True,
        force=True,
        timeout=8,
    )
    assert envelope(capsys)["command"] == "extract-parts"


def test_dispatch_routes_analyze_harmony(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "progression.ly"
    harmony = Mock(return_value=Result(True, "analyze-harmony"))

    monkeypatch.setattr(cli, "analyze_harmony", harmony)
    assert cli.main(
        [
            "analyze-harmony",
            str(source),
            "--output",
            str(tmp_path / "harmony.ily"),
            "--report",
            str(tmp_path / "report.json"),
            "--score-index",
            "1",
            "--key",
            "C",
            "--window",
            "2",
            "--max-chords",
            "4",
            "--trim-below",
            "0.5",
            "--confidence-threshold",
            "0.9",
            "--force",
            "--timeout",
            "11",
            "--json",
        ]
    ) == 0
    harmony.assert_called_once_with(
        source.resolve(),
        output_path=tmp_path / "harmony.ily",
        report_path=tmp_path / "report.json",
        score_index=1,
        key_override="C",
        window=2,
        max_chords=4,
        trim_below=0.5,
        confidence_threshold=0.9,
        force=True,
        timeout=11,
    )
    assert envelope(capsys)["command"] == "analyze-harmony"


def test_dispatch_routes_analyze_clefs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FIXTURES / "progression.ly"
    clefs = Mock(return_value=Result(True, "analyze-clefs"))

    monkeypatch.setattr(cli, "analyze_clefs", clefs)
    assert cli.main(
        [
            "analyze-clefs",
            str(source),
            "--instrument",
            "viola",
            "--variable",
            "music",
            "--initial-clef",
            "alto",
            "--output",
            str(tmp_path / "clefs.json"),
            "--force",
            "--json",
        ]
    ) == 0
    clefs.assert_called_once_with(
        source.resolve(),
        variable="music",
        instrument="viola",
        output_path=tmp_path / "clefs.json",
        initial_clef="alto",
        force=True,
    )
    assert envelope(capsys)["command"] == "analyze-clefs"


def test_dispatch_routes_build_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.lytex"
    source.write_text("\\begin{document}\\end{document}\n", encoding="utf-8")
    document = Mock(return_value=Result(True, "build-document"))

    monkeypatch.setattr(cli, "build_document", document)
    assert cli.main(
        ["build-document", str(source), "--output-dir", str(tmp_path / "build"), "--timeout", "30", "--json"]
    ) == 0
    document.assert_called_once_with(source.resolve(), output_dir=tmp_path / "build", timeout=30)
    assert envelope(capsys)["command"] == "build-document"


@pytest.mark.parametrize(
    ("text", "exit_code", "code", "ok"),
    [
        ("score.ly:9:1: warning: bar check failed", 0, "BAR_DURATION", True),
        ("score.ly:9:1: error: bar check failed", 1, "BAR_DURATION", False),
    ],
)
def test_python_module_entry_point_returns_its_exit_code(
    text: str,
    exit_code: int,
    code: str,
    ok: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``python -m lilypond_workbench.cli`` must surface main()'s exit code."""
    monkeypatch.setattr(sys, "argv", ["lilypond-workbench", "parse-log", "--json", "--text", text])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("lilypond_workbench.cli", run_name="__main__")
    assert exit_info.value.code == exit_code
    payload = envelope(capsys)
    assert payload["command"] == "parse-log"
    assert payload["ok"] is ok
    assert payload["diagnostics"][0]["code"] == code
