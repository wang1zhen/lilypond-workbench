# Changelog

All notable changes follow Keep a Changelog. Versions use Semantic Versioning.

## Unreleased

### Fixed

- Parts manifests reject unsafe part IDs and output names or conflicting IDs.
  Generated paths cannot escape the output directory, even with `--force`.
- Manifests written outside the source directory now retain a usable relative
  source path.
- Semantic comparisons report changes to event onsets and marker positions,
  including the old and new measures when checking an edit's allowed scope.
- External-tool timeouts normalize captured output to text instead of failing
  while constructing diagnostics.
- Harmony analysis selects the requested score's MIDI rather than the first
  filename returned by the compiler.
- The comparison guide uses the workbench CLI and preserves relative includes
  when taking a source backup.
- `masked_source` no longer blanks a newline that follows a backslash inside a
  string literal. The lost newline shifted every later line number, so
  diagnostics pointed at the wrong source line after an escaped line break or an
  unterminated quote.
- The container runner now passes the image's own `lilypond` to the guest instead
  of trying to map a host path for it into the container mounts.

### Added

- `index` reports the semantic index of a music variable: events with written
  pitch and accidental, markers, reconstructed measures, and source locations.
- `diff` compares two scores by musical content instead of by text, locating
  every difference by measure and beat. `--expect-measures` and
  `--fail-on-change` turn the intended scope of an edit into an enforceable
  check; `--new-variable` handles a renamed variable.
- The semantic index now records key signatures, tempo marks, dynamics,
  articulations, and repeats, and carries accidentals alongside diatonic
  positions. Index schema version 2.
- `SEMANTIC_REPEAT_DROPPED` warns when python-ly discards a `\repeat` that
  directly follows a `\tempo` mark, instead of returning a short index with no
  indication that notes are missing.
- [references/comparison.md](references/comparison.md) for the comparison
  workflow and its limits.
- Contract tests for the CLI surface: exit codes 0, 1, 2, and 130, the versioned
  JSON envelope, the container-runner command guard, and a check that every
  subcommand stays documented in both READMEs and `SKILL.md`.
- Unit tests for the container runner's mount layout, path rewriting, hardening
  flags, and its refusals (output inside the read-only source tree, paths outside
  every mount, unsupported tools, missing runtime).
- Offset and blanking invariants for `masked_source`, including a seeded fuzz
  corpus.

### Changed

- CI and container builds verify pinned LilyPond archive SHA256 hashes before
  extraction. The container explicitly requires amd64; version overrides also
  require the matching archive checksum.
- The development-release workflow names its pinned version and excludes LaTeX
  tests, which remain covered by the stable publishing job.
- Documentation distinguishes scenario-mapped regression checks from agent
  evaluations and updates the coverage and container-command descriptions.
- Human-readable output no longer dumps the structured report; it stays
  available through `--json` and `--output`.
- The CI coverage gate now also covers `cli`, `common`, and `comparison`.

## 1.0.0 - 2026-08-13

### Added

- Versioned JSON result envelopes and executable workflow evaluations.
- Semantic `lint` reports for score structure, ranges, transposition metadata,
  clefs, and part-manifest consistency.
- Parts manifest schema v3 with pitch basis, range overrides, and justified
  suppressions while retaining schema v1 and v2 compatibility.
- Native and container execution backends for LilyPond tool processes.
- CI for fast tests, LilyPond 2.24.4 integration tests, and skill validation.

### Changed

- `doctor` now treats import and document tools as optional unless `--strict`
  is used.
- Repository skill installation now follows the `.agents/skills` convention.

## 0.1.0

- Initial workbench with rendering, diagnostics, importing, part extraction,
  harmony analysis, and semantic clef analysis.
