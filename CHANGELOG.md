# Changelog

All notable changes follow Keep a Changelog. Versions use Semantic Versioning.

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
