# Contributing

Use Python 3.11 or newer and LilyPond 2.24.4. Manage every Python command and
dependency through `uv`; do not edit `uv.lock` by hand.

```sh
uv sync --group dev
uv run pytest -m "not integration"
uv run pytest
```

Changes to deterministic semantic modules must include focused unit tests.
Changes to rendering, conversion, part extraction, harmony, or documents must
include an integration test. Keep JSON fields backward compatible within a
major release, add migration notes for manifest changes, and update both
English and Chinese README files when user-facing behavior changes.
