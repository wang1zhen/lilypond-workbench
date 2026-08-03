from __future__ import annotations

from pathlib import Path

from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output, run_process
from .diagnostics import parse_lilypond_log
from .syntax import reformat_lilypond


IMPORT_FORMATS = {
    ".xml": "musicxml",
    ".musicxml": "musicxml",
    ".mxl": "musicxml",
    ".mid": "midi",
    ".midi": "midi",
    ".abc": "abc",
}


def clean_text(text: str, *, source_path: Path | None = None, timeout: int = 30) -> tuple[str, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    if source_path is not None:
        process = run_process(["convert-ly", "--current-version", str(source_path)], cwd=source_path.parent, timeout=timeout)
        if process.returncode == 0 and process.stdout.strip():
            text = process.stdout
        elif process.returncode != 0:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "CONVERT_LY_FAILED",
                    "convert-ly could not normalize the source version; retaining the existing version",
                    file=str(source_path),
                )
            )
    text = reformat_lilypond(text)
    return text, diagnostics


def clean_file(
    input_path: Path,
    *,
    output_path: Path | None = None,
    in_place: bool = False,
    force: bool = False,
) -> Result:
    if in_place and output_path is not None:
        raise WorkbenchError("--in-place and --output are mutually exclusive", "INVALID_ARGUMENT", exit_code=2)
    source = input_path.resolve()
    destination = source if in_place else (output_path or source.with_name(f"{source.stem}.clean.ly")).resolve()
    if destination != source:
        prepare_output(destination, force=force)
    cleaned, diagnostics = clean_text(source.read_text(encoding="utf-8"), source_path=source)
    atomic_write(destination, cleaned, force=(force or in_place))
    return Result(True, "clean", [str(source)], [str(destination)], diagnostics)


def import_score(
    input_path: Path,
    *,
    output_path: Path | None = None,
    force: bool = False,
    preserve_layout: bool = False,
    preserve_beams: bool = False,
    timeout: int = 120,
) -> Result:
    source = input_path.resolve()
    kind = IMPORT_FORMATS.get(source.suffix.lower())
    if not kind:
        raise WorkbenchError(f"Unsupported import format: {source.suffix}", "UNSUPPORTED_IMPORT", exit_code=2)
    destination = prepare_output(output_path or source.with_suffix(".ly"), force=force)
    if kind == "musicxml":
        argv = ["musicxml2ly", "--relative", "--midi"]
        if source.suffix.lower() == ".mxl":
            argv.append("--compressed")
        if not preserve_layout:
            argv.extend(["--npl", "--nsd"])
        if not preserve_beams:
            argv.append("--nb")
        argv.extend(["--output", str(destination), str(source)])
    elif kind == "midi":
        argv = [
            "midi2ly",
            "--explicit-durations",
            "--duration-quant=32",
            "--start-quant=16",
            "--output",
            str(destination),
            str(source),
        ]
    else:
        argv = ["abc2ly", "--output", str(destination), str(source)]
    process = run_process(argv, cwd=source.parent, timeout=timeout)
    diagnostics = parse_lilypond_log(process.stderr + "\n" + process.stdout)
    if process.returncode != 0 or not destination.exists():
        diagnostics.append(Diagnostic("error", "IMPORT_FAILED", f"{argv[0]} exited with status {process.returncode}", file=str(source)))
        return Result(False, "import-score", [str(source)], diagnostics=diagnostics, metadata={"argv": argv, "stderr": process.stderr})
    cleaned, clean_diagnostics = clean_text(destination.read_text(encoding="utf-8"), source_path=destination)
    diagnostics.extend(clean_diagnostics)
    atomic_write(destination, cleaned, force=True)
    diagnostics.append(
        Diagnostic(
            "info",
            "SEMANTIC_REVIEW_REQUIRED",
            "Mechanical cleanup completed; review voices, enharmonics, ties, beams, repeats, and lyric alignment before publishing.",
            file=str(destination),
        )
    )
    return Result(True, "import-score", [str(source)], [str(destination)], diagnostics, {"format": kind, "argv": argv})
