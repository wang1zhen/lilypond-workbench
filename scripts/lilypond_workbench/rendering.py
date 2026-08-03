from __future__ import annotations

import fnmatch
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import Diagnostic, Result, WorkbenchError, run_process
from .diagnostics import parse_lilypond_log
from .syntax import check_measure_durations


FORMATS = {"pdf", "png", "svg", "ps"}


def _snapshot(output_base: Path) -> dict[Path, tuple[int, int]]:
    return {
        path: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in output_base.parent.glob(f"{output_base.name}*")
        if path.is_file()
    }


def _artifact_paths(output_base: Path, previous: dict[Path, tuple[int, int]]) -> list[str]:
    candidates: list[Path] = []
    for path in sorted(output_base.parent.glob(f"{output_base.name}*")):
        state = (path.stat().st_mtime_ns, path.stat().st_size) if path.is_file() else None
        if (
            path.is_file()
            and path.suffix.lower() in {".pdf", ".png", ".svg", ".ps", ".midi", ".mid"}
            and previous.get(path) != state
        ):
            candidates.append(path.resolve())
    return [str(path) for path in candidates]


def render_file(
    input_path: Path,
    *,
    output_dir: Path | None = None,
    fmt: str = "pdf",
    resolution: int | None = None,
    backend: str | None = None,
    no_point_and_click: bool = False,
    preview: bool = False,
    timeout: int = 60,
    output_stem: str | None = None,
) -> Result:
    if fmt not in FORMATS:
        raise WorkbenchError(f"Unsupported render format: {fmt}", "INVALID_FORMAT", exit_code=2)
    source = input_path.resolve()
    destination = (output_dir or source.parent).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output_base = destination / (output_stem or source.stem)
    previous = _snapshot(output_base)
    argv = ["lilypond", f"-f{fmt}", "-o", str(output_base)]
    if no_point_and_click:
        argv.append("-dno-point-and-click")
    if resolution is not None:
        argv.append(f"-dresolution={resolution}")
    if backend:
        argv.append(f"-dbackend={backend}")
    if preview:
        argv.append("-dpreview")
    argv.append(str(source))
    process = run_process(argv, cwd=source.parent, timeout=timeout)
    diagnostics = parse_lilypond_log(process.stderr + "\n" + process.stdout)
    if process.timed_out:
        diagnostics.append(Diagnostic("error", "TIMEOUT", f"LilyPond exceeded {timeout} seconds", file=str(source)))
    if process.returncode != 0 and not any(item.severity == "error" for item in diagnostics):
        diagnostics.append(
            Diagnostic(
                "error",
                "LILYPOND_FAILED",
                f"LilyPond exited with status {process.returncode}",
                file=str(source),
                suggestion="Run parse-log on the captured stderr and inspect the source around the first failure.",
            )
        )
    return Result(
        ok=process.returncode == 0,
        command="render",
        inputs=[str(source)],
        artifacts=_artifact_paths(output_base, previous),
        diagnostics=diagnostics,
        metadata={"argv": process.argv, "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr},
    )


def validate_file(input_path: Path, *, timeout: int = 60, static_only: bool = False) -> Result:
    source = input_path.resolve()
    try:
        diagnostics = check_measure_durations(source.read_text(encoding="utf-8"), file_name=str(source))
    except WorkbenchError as exc:
        diagnostics = [
            Diagnostic(
                "error",
                exc.code,
                str(exc),
                file=str(source),
                suggestion="Balance the LilyPond delimiters before checking measure durations.",
            )
        ]
    metadata: dict[str, Any] = {"static_only": static_only}
    if not static_only:
        with tempfile.TemporaryDirectory(prefix="lilypond-workbench-validate-") as temp_dir:
            output_base = Path(temp_dir) / "validate"
            process = run_process(
                ["lilypond", "-dno-print-pages", "-o", str(output_base), str(source)],
                cwd=source.parent,
                timeout=timeout,
            )
            diagnostics.extend(parse_lilypond_log(process.stderr + "\n" + process.stdout))
            if process.returncode != 0 and not any(item.severity == "error" for item in diagnostics):
                diagnostics.append(Diagnostic("error", "LILYPOND_FAILED", f"LilyPond exited with status {process.returncode}", file=str(source)))
            metadata.update({"argv": process.argv, "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr})
    ok = not any(item.severity == "error" for item in diagnostics)
    return Result(ok, "validate", [str(source)], diagnostics=diagnostics, metadata=metadata)


def discover_scores(paths: list[Path], *, pattern: str, recursive: bool) -> list[Path]:
    files: set[Path] = set()
    for item in paths:
        resolved = item.expanduser().resolve()
        if resolved.is_file():
            files.add(resolved)
        elif resolved.is_dir():
            iterator = resolved.rglob("*") if recursive else resolved.iterdir()
            for candidate in iterator:
                if candidate.is_file() and fnmatch.fnmatch(candidate.name, pattern):
                    files.add(candidate.resolve())
        else:
            raise WorkbenchError(f"Input path not found: {resolved}", "INPUT_NOT_FOUND", exit_code=2)
    return sorted(files)


def batch_render(
    paths: list[Path],
    *,
    output_dir: Path,
    pattern: str = "*.ly",
    recursive: bool = False,
    jobs: int = 1,
    continue_on_error: bool = False,
    **render_options: Any,
) -> Result:
    sources = discover_scores(paths, pattern=pattern, recursive=recursive)
    if not sources:
        raise WorkbenchError("No LilyPond files matched the supplied paths", "NO_INPUTS", exit_code=2)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    common_parent = Path(os.path.commonpath([str(item.parent) for item in sources]))

    def one(source: Path) -> Result:
        try:
            relative = source.relative_to(common_parent)
            destination = output_dir / relative.parent
        except ValueError:
            destination = output_dir
        return render_file(source, output_dir=destination, **render_options)

    results: list[Result] = []
    if jobs <= 1:
        for source in sources:
            result = one(source)
            results.append(result)
            if not result.ok and not continue_on_error:
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(one, source): source for source in sources}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        results.sort(key=lambda item: item.inputs[0])
    diagnostics = [item for result in results for item in result.diagnostics]
    return Result(
        ok=all(result.ok for result in results) and len(results) == len(sources),
        command="batch-render",
        inputs=[str(path) for path in sources],
        artifacts=[path for result in results for path in result.artifacts],
        diagnostics=diagnostics,
        metadata={"completed": len(results), "total": len(sources), "failed": sum(not item.ok for item in results)},
    )


def doctor() -> Result:
    tools = [
        "uv",
        "lilypond",
        "musicxml2ly",
        "midi2ly",
        "abc2ly",
        "convert-ly",
        "lilypond-book",
        "latexmk",
        "lualatex",
    ]
    diagnostics: list[Diagnostic] = []
    versions: dict[str, str] = {}
    for tool in tools:
        resolved = shutil.which(tool)
        if not resolved:
            diagnostics.append(Diagnostic("error", "MISSING_TOOL", f"Required executable not found: {tool}"))
            continue
        process = run_process([tool, "--version"], timeout=15)
        first_line = (process.stdout or process.stderr).splitlines()
        versions[tool] = first_line[0] if first_line else resolved
    lilypond_version = versions.get("lilypond", "")
    if lilypond_version and "2.24." not in lilypond_version:
        diagnostics.append(
            Diagnostic(
                "error",
                "LILYPOND_VERSION",
                f"Expected LilyPond 2.24.x, found {lilypond_version}",
                suggestion="Use the system LilyPond 2.24 installation for this skill.",
            )
        )
    return Result(not any(item.severity == "error" for item in diagnostics), "doctor", diagnostics=diagnostics, metadata={"versions": versions})
