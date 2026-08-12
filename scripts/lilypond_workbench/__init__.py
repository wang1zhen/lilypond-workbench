"""Deterministic helpers for the LilyPond Workbench skill."""

from pathlib import Path
import tomllib


_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
__version__ = str(tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])
