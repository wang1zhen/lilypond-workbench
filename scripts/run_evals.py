#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "evals" / "evals.json"


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("evals"), list):
        raise ValueError("Eval config must use schema_version 1 and contain an evals list")
    ids: set[int] = set()
    for item in data["evals"]:
        if not isinstance(item.get("id"), int) or item["id"] in ids:
            raise ValueError("Every eval requires a unique integer id")
        ids.add(item["id"])
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            raise ValueError(f"Eval {item['id']} requires a prompt")
        nodes = item.get("pytest_nodes")
        if not isinstance(nodes, list) or not nodes or not all(isinstance(node, str) for node in nodes):
            raise ValueError(f"Eval {item['id']} requires pytest_nodes")
    return data


def run(config: dict[str, Any], selected: set[int] | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in config["evals"]:
        if selected is not None and item["id"] not in selected:
            continue
        started = time.monotonic()
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *item["pytest_nodes"]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        records.append(
            {
                "id": item["id"],
                "passed": process.returncode == 0,
                "duration_seconds": round(time.monotonic() - started, 3),
                "pytest_nodes": item["pytest_nodes"],
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        )
    return {
        "schema_version": 1,
        "skill_name": config["skill_name"],
        "passed": sum(item["passed"] for item in records),
        "total": len(records),
        "ok": all(item["passed"] for item in records),
        "results": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic LilyPond Workbench skill evaluations")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--id", type=int, action="append", dest="ids")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config.resolve())
        if args.validate_only:
            report = {"schema_version": 1, "ok": True, "evals": len(config["evals"])}
        else:
            selected = set(args.ids) if args.ids else None
            known = {item["id"] for item in config["evals"]}
            if selected and not selected <= known:
                raise ValueError(f"Unknown eval ids: {sorted(selected - known)}")
            report = run(config, selected)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema_version": 1, "ok": False, "error": str(exc)}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
