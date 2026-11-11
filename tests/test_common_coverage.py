"""Contract tests for the remaining common.py process/output paths."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lilypond_workbench.common import Result, WorkbenchError, _run_native, atomic_write, print_result


@pytest.mark.parametrize("host_lc_all", [None, "C"], ids=["unset", "preset"])
def test_native_success_returns_captured_output_and_applies_env_overrides(
    monkeypatch: pytest.MonkeyPatch, host_lc_all: str | None
) -> None:
    if host_lc_all is None:
        monkeypatch.delenv("LC_ALL", raising=False)
    else:
        monkeypatch.setenv("LC_ALL", host_lc_all)
    completed = subprocess.CompletedProcess(["tool"], 0, stdout="out", stderr="err")
    with patch("lilypond_workbench.common.subprocess.run", return_value=completed) as run:
        result = _run_native(["tool"], cwd=None, timeout=3, env_overrides={"TEXINPUTS": "/fonts"})

    assert (result.returncode, result.stdout, result.stderr, result.timed_out) == (0, "out", "err", False)
    env = run.call_args.kwargs["env"]
    assert env["TEXINPUTS"] == "/fonts"
    # setdefault: an existing host locale wins, otherwise the C.UTF-8 default applies.
    assert env["LC_ALL"] == (host_lc_all or "C.UTF-8")
    assert run.call_args.kwargs["timeout"] == 3


def test_missing_executable_is_a_configuration_error() -> None:
    with patch("lilypond_workbench.common.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(WorkbenchError) as error:
            _run_native(["absent-tool"], cwd=None, timeout=3, env_overrides=None)
    assert error.value.code == "MISSING_TOOL"
    assert error.value.exit_code == 2


def test_atomic_write_refuses_to_clobber_without_force(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(WorkbenchError) as error:
        atomic_write(target, "new")
    assert error.value.code == "OUTPUT_EXISTS"
    assert target.read_text(encoding="utf-8") == "old"

    atomic_write(target, "new", force=True)
    assert target.read_text(encoding="utf-8") == "new"


def test_human_output_prints_artifacts_and_plain_metadata_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = Result(
        True,
        "render",
        artifacts=["score.pdf"],
        metadata={"report": {"schema_version": 1}, "stdout": "noise", "notes": 2},
    )
    print_result(result)
    out = capsys.readouterr().out

    assert "[OK] render" in out
    assert "artifact: score.pdf" in out
    assert "notes: 2" in out
    assert "report" not in out
    assert "stdout" not in out
