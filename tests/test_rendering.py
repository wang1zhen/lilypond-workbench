from lilypond_workbench import rendering
from lilypond_workbench.common import ProcessResult


def test_doctor_treats_optional_tools_as_warnings_unless_strict(monkeypatch) -> None:
    core = {"uv", "lilypond", "convert-ly"}
    monkeypatch.setattr(rendering.shutil, "which", lambda name: f"/bin/{name}" if name in core else None)
    monkeypatch.setattr(
        rendering,
        "run_process",
        lambda argv, **_kwargs: ProcessResult(list(argv), 0, "GNU LilyPond 2.24.4\n" if argv[0] == "lilypond" else "1.0\n", ""),
    )

    normal = rendering.doctor()
    strict = rendering.doctor(strict=True)

    assert normal.ok
    assert all(item.severity == "warning" for item in normal.diagnostics)
    assert not strict.ok
    assert all(item.severity == "error" for item in strict.diagnostics)
