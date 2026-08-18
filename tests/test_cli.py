"""Contract tests for the command-line surface.

The CLI is a public interface: exit codes, the JSON envelope, and the
container-runner guard are all promised in README.md and SKILL.md.  These tests
stay offline by using --static-only and --text so they run without LilyPond.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lilypond_workbench import cli
from lilypond_workbench.common import Diagnostic, Result, WorkbenchError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def isolate_runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() writes the runner selection into the environment; never leak it."""
    monkeypatch.delenv("LILYPOND_WORKBENCH_RUNNER", raising=False)
    monkeypatch.delenv("LILYPOND_WORKBENCH_CONTAINER_IMAGE", raising=False)


def envelope(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0


def test_missing_command_is_an_argparse_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert exit_info.value.code == 2


def test_unknown_command_is_an_argparse_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["not-a-command"])
    assert exit_info.value.code == 2


def test_success_exits_zero_and_emits_the_versioned_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["lint", str(FIXTURES / "progression.ly"), "--static-only", "--json"]) == 0
    payload = envelope(capsys)
    assert payload == {
        "schema_version": 1,
        "ok": True,
        "command": "lint",
        "inputs": payload["inputs"],
        "artifacts": payload["artifacts"],
        "diagnostics": payload["diagnostics"],
        "metadata": payload["metadata"],
    }
    assert payload["inputs"] == [str(FIXTURES / "progression.ly")]
    assert payload["metadata"]["report"]["schema_version"] == 1


def test_failing_findings_exit_one_not_two(capsys: pytest.CaptureFixture[str]) -> None:
    """Exit 1 means "ran fine, found problems"; it must not collapse into 2."""
    assert cli.main(["validate", str(FIXTURES / "broken.ly"), "--static-only", "--json"]) == 1
    payload = envelope(capsys)
    assert payload["ok"] is False
    assert [item["code"] for item in payload["diagnostics"]] == ["UNMATCHED_DELIMITER"]


def test_missing_input_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", str(tmp_path / "absent.ly"), "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "INPUT_NOT_FOUND"


def test_wrong_extension_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stray = tmp_path / "score.txt"
    stray.write_text("{ c'1 }\n", encoding="utf-8")
    assert cli.main(["validate", str(stray), "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "UNSUPPORTED_INPUT"


def test_unknown_template_exits_two_and_lists_alternatives(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["new", "harpsichord", str(tmp_path / "out.ly"), "--json"]) == 2
    diagnostic = envelope(capsys)["diagnostics"][0]
    assert diagnostic["code"] == "TEMPLATE_NOT_FOUND"
    assert "piano" in diagnostic["message"]


def test_new_writes_a_template_and_refuses_to_clobber_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "score.ly"
    assert cli.main(["new", "piano", str(destination), "--json"]) == 0
    assert envelope(capsys)["artifacts"] == [str(destination)]
    first = destination.read_text(encoding="utf-8")

    assert cli.main(["new", "piano", str(destination), "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "OUTPUT_EXISTS"
    assert destination.read_text(encoding="utf-8") == first

    assert cli.main(["new", "piano", str(destination), "--force", "--json"]) == 0
    capsys.readouterr()


def test_new_accepts_a_template_name_with_a_ly_suffix(tmp_path: Path) -> None:
    assert cli.main(["new", "piano.ly", str(tmp_path / "score.ly"), "--json"]) == 0


def test_parse_log_reads_text_and_classifies_severity(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["parse-log", "--json", "--text", "score.ly:3:5: error: syntax error"]) == 1
    diagnostic = envelope(capsys)["diagnostics"][0]
    assert (diagnostic["code"], diagnostic["line"], diagnostic["column"]) == ("SYNTAX_ERROR", 3, 5)

    assert cli.main(["parse-log", "--json", "--text", "score.ly:9:1: warning: bar check failed"]) == 0
    assert envelope(capsys)["diagnostics"][0]["severity"] == "warning"


def test_parse_log_reads_stdin_when_no_source_is_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", __import__("io").StringIO("score.ly:1:1: error: syntax error"))
    assert cli.main(["parse-log", "--json"]) == 1
    assert envelope(capsys)["inputs"] == ["stdin"]


def test_human_readable_output_reports_location_and_suggestion(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["parse-log", "--text", "score.ly:3:5: error: syntax error"]) == 1
    out = capsys.readouterr().out
    assert "[FAILED] parse-log" in out
    assert "score.ly:3:5: SYNTAX_ERROR" in out
    assert "suggestion:" in out


def test_human_readable_output_omits_the_structured_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["lint", str(FIXTURES / "progression.ly"), "--static-only"]) == 0
    out = capsys.readouterr().out
    assert "[OK] lint" in out
    assert "report:" not in out
    assert "schema_version" not in out


def test_index_and_diff_are_routed_and_write_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old_source = tmp_path / "old.ly"
    new_source = tmp_path / "new.ly"
    old_source.write_text('\\version "2.24.4"\nmusic = { c\'4 d\' e\' f\' }\n', encoding="utf-8")
    new_source.write_text('\\version "2.24.4"\nmusic = { c\'4 des\' e\' f\' }\n', encoding="utf-8")

    assert cli.main(["index", str(old_source), "--variable", "music", "--output", str(tmp_path / "i.json"), "--json"]) == 0
    payload = envelope(capsys)
    assert payload["metadata"]["report"]["schema_version"] == 2
    assert payload["artifacts"] == [str(tmp_path / "i.json")]

    assert cli.main(["diff", str(old_source), str(new_source), "--variable", "music", "--json"]) == 0
    report = envelope(capsys)["metadata"]["report"]
    assert report["summary"]["by_kind"] == {"pitch_changed": 1}


def test_diff_exits_one_when_a_change_falls_outside_the_expected_measures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old_source = tmp_path / "old.ly"
    new_source = tmp_path / "new.ly"
    old_source.write_text('\\version "2.24.4"\nmusic = { c\'4 d\' e\' f\' }\n', encoding="utf-8")
    new_source.write_text('\\version "2.24.4"\nmusic = { c\'4 des\' e\' f\' }\n', encoding="utf-8")
    argv = ["diff", str(old_source), str(new_source), "--variable", "music"]
    assert cli.main([*argv, "--expect-measures", "1", "--json"]) == 0
    capsys.readouterr()
    assert cli.main([*argv, "--expect-measures", "5", "--json"]) == 1
    assert envelope(capsys)["diagnostics"][-1]["code"] == "DIFF_OUTSIDE_EXPECTED"
    capsys.readouterr()
    assert cli.main([*argv, "--fail-on-change", "--json"]) == 1
    codes = {item["code"] for item in envelope(capsys)["diagnostics"]}
    assert "DIFF_UNEXPECTED_CHANGE" in codes


def test_diff_rejects_a_malformed_measure_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "score.ly"
    source.write_text('\\version "2.24.4"\nmusic = { c\'4 }\n', encoding="utf-8")
    assert cli.main(["diff", str(source), str(source), "--variable", "music", "--expect-measures", "4-2", "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "INVALID_ARGUMENT"


def test_clean_rejects_in_place_together_with_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "score.ly"
    source.write_text('\\version "2.24.4"\n{ c\'1 }\n', encoding="utf-8")
    assert cli.main(["clean", str(source), "--in-place", "--output", str(tmp_path / "o.ly"), "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("command", ["new", "clean", "import-score", "parts-manifest", "doctor"])
def test_container_runner_refuses_commands_it_cannot_isolate(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the LilyPond-driven commands may claim container isolation."""
    argv = {
        "new": ["new", "piano", str(tmp_path / "score.ly")],
        "clean": ["clean", str(FIXTURES / "progression.ly")],
        "import-score": ["import-score", str(FIXTURES / "sample.abc")],
        "parts-manifest": ["parts-manifest", str(FIXTURES / "progression.ly"), "--output", str(tmp_path / "p.yaml")],
        "doctor": ["doctor"],
    }[command]
    assert cli.main(["--runner", "container", *argv, "--json"]) == 2
    assert envelope(capsys)["diagnostics"][0]["code"] == "CONTAINER_UNSUPPORTED_TOOL"
    assert not (tmp_path / "score.ly").exists()


def test_container_runner_selection_reaches_the_process_layer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, str | None] = {}

    def fake_lint(*_args, **_kwargs) -> Result:
        seen["runner"] = cli.os.environ.get("LILYPOND_WORKBENCH_RUNNER")
        seen["image"] = cli.os.environ.get("LILYPOND_WORKBENCH_CONTAINER_IMAGE")
        return Result(True, "lint")

    monkeypatch.setattr(cli, "lint_score", fake_lint)
    assert cli.main(
        [
            "--runner",
            "container",
            "--container-image",
            "example.invalid/lilypond:2.24.4",
            "lint",
            str(FIXTURES / "progression.ly"),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert seen == {"runner": "container", "image": "example.invalid/lilypond:2.24.4"}


def test_native_runner_is_the_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, str | None] = {}

    def fake_lint(*_args, **_kwargs) -> Result:
        seen["runner"] = cli.os.environ.get("LILYPOND_WORKBENCH_RUNNER")
        return Result(True, "lint")

    monkeypatch.setattr(cli, "lint_score", fake_lint)
    assert cli.main(["lint", str(FIXTURES / "progression.ly"), "--json"]) == 0
    capsys.readouterr()
    assert seen == {"runner": "native"}


def test_workbench_error_exit_code_is_honoured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(_args) -> Result:
        raise WorkbenchError("tool missing", "MISSING_TOOL", exit_code=2)

    monkeypatch.setattr(cli, "dispatch", explode)
    assert cli.main(["doctor", "--json"]) == 2
    payload = envelope(capsys)
    assert payload["command"] == "doctor"
    assert payload["diagnostics"][0]["code"] == "MISSING_TOOL"


def test_interruption_exits_one_hundred_thirty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupt(_args) -> Result:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "dispatch", interrupt)
    assert cli.main(["doctor", "--json"]) == 130
    assert envelope(capsys)["diagnostics"][0]["code"] == "INTERRUPTED"


def test_dispatch_rejects_an_unroutable_command() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor"])
    args.command = "teleport"
    with pytest.raises(WorkbenchError) as error:
        cli.dispatch(args)
    assert error.value.code == "INVALID_ARGUMENT"


def test_every_subcommand_is_documented() -> None:
    """README tables and the SKILL.md CLI map must not drift from the parser."""
    actions = [
        action
        for action in cli.build_parser()._subparsers._group_actions  # type: ignore[union-attr]
        if hasattr(action, "choices")
    ]
    commands = set(actions[0].choices)
    assert commands, "no subcommands discovered"
    for document in ("README.md", "README_CN.md", "SKILL.md"):
        text = (ROOT / document).read_text(encoding="utf-8")
        missing = sorted(
            command for command in commands if not re.search(rf"`{re.escape(command)}\b", text)
        )
        assert not missing, f"{document} does not mention {missing}"


def test_json_flag_is_offered_by_every_subcommand() -> None:
    parser = cli.build_parser()
    actions = [
        action
        for action in parser._subparsers._group_actions  # type: ignore[union-attr]
        if hasattr(action, "choices")
    ]
    for name, subparser in actions[0].choices.items():
        options = {option for action in subparser._actions for option in action.option_strings}
        assert "--json" in options, f"{name} cannot emit JSON"


def test_diagnostic_serialisation_keeps_every_envelope_field() -> None:
    result = Result(
        False,
        "lint",
        ["in.ly"],
        ["out.ly"],
        [Diagnostic("warning", "CODE", "message", file="in.ly", line=2, column=3, suggestion="fix", details={"k": 1})],
        {"key": "value"},
    )
    payload = result.to_dict()
    assert set(payload) == {"schema_version", "ok", "command", "inputs", "artifacts", "diagnostics", "metadata"}
    assert set(payload["diagnostics"][0]) == {
        "severity",
        "code",
        "message",
        "file",
        "line",
        "column",
        "suggestion",
        "details",
    }
