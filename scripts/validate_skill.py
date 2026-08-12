#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    skill = root / "SKILL.md"
    if not skill.is_file():
        return ["SKILL.md is missing"]
    text = skill.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return ["SKILL.md must start with YAML frontmatter"]
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        return ["SKILL.md frontmatter must be a mapping"]
    if set(metadata) != {"name", "description"}:
        errors.append("SKILL.md frontmatter must contain only name and description")
    name = metadata.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > 64:
        errors.append("Skill name must be lowercase hyphen-case and at most 64 characters")
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        errors.append("Skill description is required")
    agent_file = root / "agents" / "openai.yaml"
    if not agent_file.is_file():
        errors.append("agents/openai.yaml is missing")
    else:
        agent = yaml.safe_load(agent_file.read_text(encoding="utf-8"))
        interface = agent.get("interface", {}) if isinstance(agent, dict) else {}
        for key in ("display_name", "short_description", "default_prompt"):
            if not isinstance(interface.get(key), str) or not interface[key].strip():
                errors.append(f"agents/openai.yaml interface.{key} is required")
        if isinstance(name, str) and f"${name}" not in str(interface.get("default_prompt", "")):
            errors.append("interface.default_prompt must mention the skill by $name")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the LilyPond Workbench skill package")
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print("Skill package is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
