from __future__ import annotations

import os
from pathlib import Path

from .common import Diagnostic, Result, WorkbenchError, run_process


_LATEX_PROBE_PATTERNS = ("tmp*.out", "tmp*.pdf", "tmp*.bcf", "tmp*.run.xml")


def _probe_files(directory: Path) -> set[Path]:
    return {
        path.resolve()
        for pattern in _LATEX_PROBE_PATTERNS
        for path in directory.glob(pattern)
        if path.is_file()
    }


def build_document(source: Path, *, output_dir: Path, timeout: int = 180) -> Result:
    source = source.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_files_before = _probe_files(source.parent)
    try:
        first = run_process(
            [
                "lilypond-book",
                "--pdf",
                "--latex-program=lualatex",
                "--output",
                str(output_dir),
                str(source),
            ],
            cwd=source.parent,
            timeout=timeout,
        )
    finally:
        for path in _probe_files(source.parent) - probe_files_before:
            path.unlink(missing_ok=True)
    diagnostics: list[Diagnostic] = []
    if first.returncode != 0:
        diagnostics.append(
            Diagnostic(
                "error",
                "LILYPOND_BOOK_FAILED",
                f"lilypond-book exited with status {first.returncode}",
                file=str(source),
                suggestion="Inspect LilyPond snippets and LaTeX syntax in the generated log.",
            )
        )
        return Result(False, "build-document", [str(source)], diagnostics=diagnostics, metadata={"stderr": first.stderr})
    generated = output_dir / f"{source.stem}.tex"
    if not generated.is_file():
        raise WorkbenchError(f"lilypond-book did not create {generated.name}", "DOCUMENT_TEX_MISSING")
    second = run_process(
        ["latexmk", "-lualatex", "-interaction=nonstopmode", "-halt-on-error", generated.name],
        cwd=output_dir,
        timeout=timeout,
        env_overrides={
            "TEXINPUTS": f"{source.parent}//{os.pathsep}{os.environ.get('TEXINPUTS', '')}",
        },
    )
    if second.returncode != 0:
        diagnostics.append(
            Diagnostic(
                "error",
                "LATEX_FAILED",
                f"latexmk exited with status {second.returncode}",
                file=str(generated),
                suggestion="Inspect the .log file for a missing package, font, or malformed command.",
            )
        )
    pdf = output_dir / f"{source.stem}.pdf"
    artifacts = [str(generated)]
    if pdf.is_file():
        artifacts.append(str(pdf))
    log = output_dir / f"{source.stem}.log"
    if log.is_file():
        artifacts.append(str(log))
    return Result(
        second.returncode == 0 and pdf.is_file(),
        "build-document",
        [str(source)],
        artifacts,
        diagnostics,
        {"lilypond_book_exit": first.returncode, "latexmk_exit": second.returncode, "stderr": first.stderr + second.stderr},
    )
