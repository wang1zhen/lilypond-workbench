# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Two things in one package:

1. An **agent skill** — `SKILL.md` (entry point, loaded by the agent), `references/*.md` (task-specific guidance the agent reads on demand), `agents/openai.yaml` (skill UI metadata), `assets/` (score/document templates). The repository directory *is* the skill package; it is consumed by symlinking it to `.agents/skills/lilypond-workbench` in another project.
2. A **deterministic CLI** under `scripts/` that the skill calls for anything that must be reproducible and verifiable.

The split is deliberate: musical judgment (composition, semantic edits) stays with the agent; validation, conversion, extraction, analysis, and rendering go through the CLI. Keep that boundary when adding features — new *musical* capability usually means a new `references/` document plus SKILL.md routing, not new Python.

## Commands

Every Python invocation goes through `uv`. Never call `python`, `pytest`, or the scripts directly, and never hand-edit dependency lists in `pyproject.toml` or `uv.lock` (`uv add` / `uv add --dev` / `uv remove`).

```sh
uv sync --group dev
uv run pytest -m "not integration"        # fast suite; no LilyPond needed
uv run pytest                             # full suite; needs LilyPond 2.24.4 + LaTeX
uv run pytest -m "integration and not latex"
uv run pytest tests/test_clefs.py::test_name   # single test
uv run python scripts/workbench.py doctor      # check local toolchain
uv run python scripts/validate_skill.py .      # lint the skill package metadata
uv run python scripts/run_evals.py             # run the executable skill evals
uv run python scripts/run_evals.py --id 3      # one eval
```

`pytest` markers: `integration` (needs system LilyPond) and `latex` (needs `lilypond-book` + LuaLaTeX + `latexmk`). CI (`.github/workflows/ci.yml`) runs the fast suite on Python 3.11/3.12/3.13 with **`--cov-fail-under=85` scoped to the semantic core** (`clefs`, `semantic`, `syntax`, `parts`, `linting`) — changes to those five modules must come with tests or CI fails.

Requires LilyPond 2.24.x (tested 2.24.4), installed at the OS level, not as a Python dependency. A monthly workflow re-runs the integration suite against a LilyPond development build (`continue-on-error`) as an early-warning signal.

## Architecture

`scripts/workbench.py` is a thin shim over `lilypond_workbench.cli`; `scripts/` is on `sys.path` (see `tests/conftest.py`), which is how the package resolves.

**`cli.py`** is pure argparse + a flat `dispatch()` if-chain: it parses, validates inputs via `ensure_input`, and delegates. Every subcommand handler returns a `Result`; `main()` prints it and maps to an exit code. Adding a command means: a subparser in `build_parser()`, a branch in `dispatch()`, a `Result`-returning function in a feature module, a SKILL.md CLI-map entry, a README table row (and `README_CN.md`), and tests.

**`common.py`** is the contract layer everything else depends on:
- `Result` / `Diagnostic` — the single output shape. `Result.to_dict()` emits the versioned JSON envelope (`schema_version`, `ok`, `command`, `inputs`, `artifacts`, `diagnostics`, `metadata`). Feature modules never print.
- `WorkbenchError(message, code, exit_code)` — the only error channel. Exit codes are a public interface: **0** success, **1** completed with failing findings or tool failure, **2** invalid input/config or missing required tool, **130** interrupt. Use `exit_code=2` for input/config problems.
- `run_process()` — the single gateway to every external executable, dispatching on the `LILYPOND_WORKBENCH_RUNNER` env var that `cli.main()` sets from the global `--runner` flag. The `container` backend hard-sandboxes (`--network=none`, `--read-only`, `--cap-drop=ALL`, source mounted read-only, host paths rewritten into declared mounts) and currently accepts only `lilypond`, so `--runner container` is restricted to the render/validate/lint/harmony commands. Never call `subprocess` directly from a feature module.
- `prepare_output` / `atomic_write` — refuse to clobber unless `force=True`, which is what backs every `--force` flag.

**Analysis layering** (bottom-up; respect it, don't shortcut around it):

- `syntax.py` — text-level LilyPond structure. `masked_source()` blanks comments and strings *while preserving byte offsets*, so every regex scan in the codebase runs against the mask and then indexes back into the original text. Also block/variable discovery, definition sanitizing, include rewriting, `python-ly` reformatting.
- `semantic.py` — builds a `SemanticIndex` from a music variable: resolves includes, relative→absolute pitch, transposition, tuplets, repeats, simultaneous voices, and emits `IndexedEvent`s carrying a `SourceLocation` plus measure/meter reconstruction and a content fingerprint. This is why diagnostics can point at real source lines. Diatonic pitch integers use **C4 == 28** — the same convention in `clefs.py` and `linting.py`.
- `clefs.py` — consumes a `SemanticIndex` and recommends stable violin/viola/cello clef changes (hysteresis over staff ranges), optionally rendering a separate clef *track*. It never edits score source.
- `linting.py`, `parts.py`, `harmony.py`, `rendering.py`, `diagnostics.py`, `importers.py`, `documents.py` — command implementations. `linting.py` composes the semantic index, the clef analyzer, manifest normalization, and a LilyPond validation compile into one report; `parts.py` builds/normalizes the manifest and generates part wrappers.

**Versioned schemas.** Several independent version numbers, all part of the public surface: `RESULT_SCHEMA_VERSION` (JSON envelope), the parts-manifest schema (`parts.py` writes **v3** with `pitch_basis: concert|written` and still reads v1/v2, normalizing upward while preserving old behavior), the lint report schema, the semantic-index schema, the clef-analysis schema, and `evals/evals.json`. Keep JSON fields backward compatible within a major release; a manifest change needs migration notes and a normalization path for older versions.

**Evals.** `evals/evals.json` maps each eval id to `pytest_nodes`, so evals are executable: `run_evals.py` shells out to pytest per eval and emits its own versioned JSON report. `tests/test_evals.py` validates the config.

## Conventions

- Behavior that refuses rather than guesses is intentional throughout: part extraction stops when a shared source can't be isolated safely, low-confidence harmony events are omitted from the generated `.ily` but kept in JSON, clef analysis only reports unless policy is `auto`. Preserve that posture — prefer a `needs_review` diagnostic over a silent assumption.
- Treat LilyPond input as executable code (embedded Guile/Scheme runs at compile time). Untrusted sources go through `--runner container`.
- User-facing changes must update **both** `README.md` and `README_CN.md`, plus `CHANGELOG.md`.
- Per `CONTRIBUTING.md`: deterministic semantic modules need focused unit tests; rendering, conversion, part extraction, harmony, and document changes need an integration test.
