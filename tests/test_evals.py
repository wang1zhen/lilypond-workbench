import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("run_evals", ROOT / "scripts" / "run_evals.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_config_has_seven_executable_scenarios() -> None:
    config = _module().load_config(ROOT / "evals" / "evals.json")

    assert [item["id"] for item in config["evals"]] == list(range(1, 8))
    assert all(item["pytest_nodes"] for item in config["evals"])
