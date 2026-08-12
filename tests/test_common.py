from pathlib import Path

from lilypond_workbench import common
from lilypond_workbench.common import ProcessResult, Result


def test_result_json_has_versioned_envelope() -> None:
    assert Result(True, "test").to_dict()["schema_version"] == 1


def test_container_runner_uses_read_only_source_and_offline_runtime(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()
    source = source_dir / "score.ly"
    source.write_text("{ c'1 }\n", encoding="utf-8")
    captured: list[str] = []

    monkeypatch.setattr(common.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def fake_native(args, **_kwargs):
        captured.extend(args)
        return ProcessResult(args, 0, "", "")

    monkeypatch.setattr(common, "_run_native", fake_native)
    result = common._run_container(
        ["lilypond", "-o", str(output_dir / "score"), str(source)],
        cwd=source_dir,
        timeout=10,
        env_overrides=None,
    )

    assert result.returncode == 0
    assert "--network=none" in captured
    assert "--read-only" in captured
    assert f"{source_dir}:/work:ro" in captured
    assert f"{output_dir}:/output0:rw" in captured
    assert "/work/score.ly" in captured
