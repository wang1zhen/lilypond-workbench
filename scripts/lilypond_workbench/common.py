from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    suggestion: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Result:
    ok: bool
    command: str
    inputs: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "inputs": self.inputs,
            "artifacts": self.artifacts,
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ProcessResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class WorkbenchError(Exception):
    def __init__(self, message: str, code: str = "WORKBENCH_ERROR", *, exit_code: int = 1):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def run_process(
    argv: Iterable[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    env_overrides: dict[str, str] | None = None,
) -> ProcessResult:
    args = [os.fspath(item) for item in argv]
    env = os.environ.copy()
    env.setdefault("LC_ALL", "C.UTF-8")
    cache_root = Path(tempfile.gettempdir()) / "lilypond-workbench-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    (cache_root / "texmf-var").mkdir(parents=True, exist_ok=True)
    env["XDG_CACHE_HOME"] = str(cache_root)
    env["TEXMFVAR"] = str(cache_root / "texmf-var")
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return ProcessResult(args, completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        raise WorkbenchError(f"Required executable not found: {args[0]}", "MISSING_TOOL", exit_code=2) from exc
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            args,
            -2,
            exc.stdout or "",
            exc.stderr or "",
            timed_out=True,
        )


def ensure_input(path: str | Path, suffixes: set[str] | None = None) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise WorkbenchError(f"Input file not found: {resolved}", "INPUT_NOT_FOUND", exit_code=2)
    if suffixes and resolved.suffix.lower() not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise WorkbenchError(f"Unsupported input extension {resolved.suffix}; expected {allowed}", "UNSUPPORTED_INPUT", exit_code=2)
    return resolved


def prepare_output(path: str | Path, *, force: bool = False) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved.exists() and not force:
        raise WorkbenchError(f"Output already exists: {resolved}; pass --force to replace it", "OUTPUT_EXISTS", exit_code=2)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def atomic_write(path: Path, text: str, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise WorkbenchError(f"Output already exists: {path}; pass --force to replace it", "OUTPUT_EXISTS", exit_code=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def print_result(result: Result, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    status = "OK" if result.ok else "FAILED"
    print(f"[{status}] {result.command}")
    for artifact in result.artifacts:
        print(f"  artifact: {artifact}")
    for diagnostic in result.diagnostics:
        location = ""
        if diagnostic.file:
            location = diagnostic.file
            if diagnostic.line is not None:
                location += f":{diagnostic.line}"
                if diagnostic.column is not None:
                    location += f":{diagnostic.column}"
            location += ": "
        print(f"  [{diagnostic.severity.upper()}] {location}{diagnostic.code}: {diagnostic.message}")
        if diagnostic.suggestion:
            print(f"    suggestion: {diagnostic.suggestion}")
    for key, value in result.metadata.items():
        if key not in {"stdout", "stderr"}:
            print(f"  {key}: {value}")
