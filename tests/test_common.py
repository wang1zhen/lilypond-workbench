import subprocess
from unittest.mock import patch

import pytest

from lilypond_workbench.common import Result, _run_native


def test_result_json_has_versioned_envelope() -> None:
    assert Result(True, "test").to_dict()["schema_version"] == 1


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected"),
    [(b"out", b"err", ("out", "err")), ("out", "err", ("out", "err")), (None, None, ("", ""))],
    ids=["bytes", "str", "none"],
)
def test_native_timeout_normalizes_captured_output(stdout, stderr, expected) -> None:
    timeout = subprocess.TimeoutExpired(["tool"], 1, output=stdout, stderr=stderr)
    with patch("lilypond_workbench.common.subprocess.run", side_effect=timeout):
        result = _run_native(["tool"], cwd=None, timeout=1, env_overrides=None)
    assert result.timed_out
    assert (result.stdout, result.stderr) == expected
