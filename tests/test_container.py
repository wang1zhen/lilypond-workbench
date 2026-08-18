"""Unit tests for the container process runner.

The container backend is a security boundary: it mounts the source read-only,
rewrites host paths into the guest mount layout, and refuses anything it cannot
isolate.  None of that is observable from a passing render, so it is asserted
here on the constructed argv instead of by running a real container.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lilypond_workbench import common
from lilypond_workbench.common import ProcessResult, WorkbenchError


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch):
    """Pretend a container runtime exists and capture the argv it would run."""

    def install(name: str = "docker") -> list[list[str]]:
        calls: list[list[str]] = []
        monkeypatch.setattr(
            common.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == name else None
        )

        def fake_native(args, *, cwd=None, timeout=60, env_overrides=None):
            calls.append(args)
            install.cwd = cwd
            install.env_overrides = env_overrides
            return ProcessResult(args, 0, "", "")

        monkeypatch.setattr(common, "_run_native", fake_native)
        return calls

    return install


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "score.ly"
    source.write_text("{ c'1 }\n", encoding="utf-8")
    return source_dir, source, tmp_path / "output"


def run(source_dir: Path, argv: list[str], **kwargs) -> ProcessResult:
    return common._run_container(argv, cwd=source_dir, timeout=10, env_overrides=None, **kwargs)


def test_hardening_flags_and_mounts(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    result = run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    argv = calls[0]

    assert result.returncode == 0
    assert argv[:3] == ["/usr/bin/docker", "run", "--rm"]
    for flag in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=256m",
        "--env=XDG_CACHE_HOME=/tmp/cache",
        "--env=HOME=/tmp",
    ):
        assert flag in argv
    assert f"{source_dir}:/work:ro" in argv
    assert f"{output_dir}:/output0:rw" in argv
    # The command itself is rewritten into guest paths, source last.
    assert argv[-3:] == ["-o", "/output0/score", "/work/score.ly"]


def test_source_mount_is_always_read_only(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("podman")
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    mounts = [value for index, value in enumerate(calls[0]) if calls[0][index - 1] == "--volume"]
    assert [mount for mount in mounts if mount.endswith(":ro")] == [f"{source_dir}:/work:ro"]


def test_podman_keeps_the_user_namespace(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("podman")
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    assert "--userns=keep-id" in calls[0]
    assert not any(item.startswith("--user=") for item in calls[0])


def test_docker_maps_the_invoking_user(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    assert f"--user={os.getuid()}:{os.getgid()}" in calls[0]
    assert "--userns=keep-id" not in calls[0]


def test_podman_is_preferred_when_both_runtimes_exist(
    monkeypatch: pytest.MonkeyPatch, tree
) -> None:
    source_dir, source, output_dir = tree
    calls: list[list[str]] = []
    monkeypatch.setattr(common.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        common,
        "_run_native",
        lambda args, **_kwargs: (calls.append(args), ProcessResult(args, 0, "", ""))[1],
    )
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    assert calls[0][0] == "/usr/bin/podman"


def test_missing_runtime_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch, tree) -> None:
    source_dir, source, output_dir = tree
    monkeypatch.setattr(common.shutil, "which", lambda _tool: None)
    with pytest.raises(WorkbenchError) as error:
        run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    assert error.value.code == "MISSING_CONTAINER_RUNTIME"
    assert error.value.exit_code == 2


@pytest.mark.parametrize("argv", [[], ["convert-ly", "score.ly"], ["/usr/bin/musicxml2ly", "in.xml"]])
def test_only_lilypond_may_run_in_the_container(runtime, tree, argv: list[str]) -> None:
    source_dir, _source, _output = tree
    runtime("docker")
    with pytest.raises(WorkbenchError) as error:
        run(source_dir, argv)
    assert error.value.code == "CONTAINER_UNSUPPORTED_TOOL"
    assert error.value.exit_code == 2


def test_a_host_path_to_lilypond_becomes_the_image_executable(runtime, tree) -> None:
    """The image provides LilyPond; a host path for it is not mapped into the guest."""
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    result = run(source_dir, ["/opt/lilypond-2.24.4/bin/lilypond", "-o", str(output_dir / "s"), str(source)])
    assert result.returncode == 0
    assert "/opt/lilypond-2.24.4/bin/lilypond" not in calls[0]
    assert calls[0][-3:] == ["-o", "/output0/s", "/work/score.ly"]


@pytest.mark.parametrize("relative", ["", "nested"])
def test_output_inside_the_read_only_source_tree_is_refused(runtime, tree, relative: str) -> None:
    source_dir, source, _output = tree
    runtime("docker")
    target = source_dir / relative / "build" if relative else source_dir
    with pytest.raises(WorkbenchError) as error:
        run(source_dir, ["lilypond", "-o", str(target / "score"), str(source)])
    assert error.value.code == "CONTAINER_OUTPUT_CONFLICT"
    assert error.value.exit_code == 2


def test_paths_outside_every_mount_are_refused(runtime, tree, tmp_path: Path) -> None:
    source_dir, _source, output_dir = tree
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    stray = elsewhere / "score.ly"
    stray.write_text("{ c'1 }\n", encoding="utf-8")
    runtime("docker")
    with pytest.raises(WorkbenchError) as error:
        run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(stray)])
    assert error.value.code == "CONTAINER_PATH_UNMAPPED"
    assert error.value.exit_code == 2


def test_several_outputs_get_separate_writable_mounts(runtime, tree, tmp_path: Path) -> None:
    source_dir, source, output_dir = tree
    second = tmp_path / "other-output"
    calls = runtime("docker")
    run(
        source_dir,
        ["lilypond", "-o", str(output_dir / "a"), "-o", str(second / "b"), str(source)],
    )
    argv = calls[0]
    assert f"{output_dir}:/output0:rw" in argv
    assert f"{second}:/output1:rw" in argv
    assert "/output0/a" in argv and "/output1/b" in argv


def test_outputs_sharing_a_directory_reuse_one_mount(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-o", str(output_dir / "a"), "-o", str(output_dir / "b"), str(source)])
    mounts = [value for index, value in enumerate(calls[0]) if calls[0][index - 1] == "--volume"]
    assert mounts == [f"{source_dir}:/work:ro", f"{output_dir}:/output0:rw"]
    assert calls[0].count("/output0/a") == 1
    assert "/output0/b" in calls[0]


def test_the_output_directory_is_created_before_mounting(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    runtime("docker")
    assert not output_dir.exists()
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    assert output_dir.is_dir()


def test_the_deepest_matching_mount_wins(runtime, tree, tmp_path: Path) -> None:
    """A nested output under a parent mount must not be rewritten to the parent."""
    source_dir, source, _output = tree
    outer = tmp_path / "build"
    inner = outer / "parts"
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-o", str(outer / "score"), "-o", str(inner / "violin"), str(source)])
    argv = calls[0]
    assert "/output0/score" in argv
    assert "/output1/violin" in argv


def test_relative_arguments_pass_through_unchanged(runtime, tree) -> None:
    source_dir, _source, output_dir = tree
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-dno-print-pages", "-o", str(output_dir / "score"), "score.ly"])
    assert "score.ly" in calls[0]
    assert "-dno-print-pages" in calls[0]


def test_environment_overrides_travel_as_container_env_not_host_env(runtime, tree) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    common._run_container(
        ["lilypond", "-o", str(output_dir / "score"), str(source)],
        cwd=source_dir,
        timeout=10,
        env_overrides={"TEXINPUTS": "/fonts"},
    )
    argv = calls[0]
    assert argv[argv.index("--env") + 1] == "TEXINPUTS=/fonts"
    # The host process must not inherit them; only the guest gets them.
    assert runtime.env_overrides is None
    assert runtime.cwd == source_dir.resolve()


def test_image_defaults_to_the_pinned_local_build(runtime, tree, monkeypatch: pytest.MonkeyPatch) -> None:
    source_dir, source, output_dir = tree
    monkeypatch.delenv("LILYPOND_WORKBENCH_CONTAINER_IMAGE", raising=False)
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    argv = calls[0]
    assert argv[argv.index("lilypond") - 1] == "localhost/lilypond-workbench:2.24.4"


def test_image_is_overridable_by_environment(runtime, tree, monkeypatch: pytest.MonkeyPatch) -> None:
    source_dir, source, output_dir = tree
    monkeypatch.setenv("LILYPOND_WORKBENCH_CONTAINER_IMAGE", "example.invalid/lilypond:pinned")
    calls = runtime("docker")
    run(source_dir, ["lilypond", "-o", str(output_dir / "score"), str(source)])
    argv = calls[0]
    assert argv[argv.index("lilypond") - 1] == "example.invalid/lilypond:pinned"


def test_run_process_routes_by_runner_selection(runtime, tree, monkeypatch: pytest.MonkeyPatch) -> None:
    source_dir, source, output_dir = tree
    calls = runtime("docker")
    monkeypatch.setenv("LILYPOND_WORKBENCH_RUNNER", "container")
    common.run_process(["lilypond", "-o", str(output_dir / "score"), str(source)], cwd=source_dir, timeout=10)
    assert calls[0][0] == "/usr/bin/docker"

    monkeypatch.setenv("LILYPOND_WORKBENCH_RUNNER", "native")
    common.run_process(["lilypond", "--version"], timeout=10)
    assert calls[1] == ["lilypond", "--version"]


def test_run_process_rejects_an_unknown_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LILYPOND_WORKBENCH_RUNNER", "chroot")
    with pytest.raises(WorkbenchError) as error:
        common.run_process(["lilypond", "--version"])
    assert error.value.code == "INVALID_RUNNER"
    assert error.value.exit_code == 2
