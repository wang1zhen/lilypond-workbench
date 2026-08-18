from lilypond_workbench.common import Result


def test_result_json_has_versioned_envelope() -> None:
    assert Result(True, "test").to_dict()["schema_version"] == 1
