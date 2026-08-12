# Semantic quality linting

Run `lint score.ly --output score.lint.json`. Add `--manifest parts.yaml` to
check part variables, tags, output names, written/concert pitch basis,
transposition metadata, practical ranges, absolute ranges, and string clefs.

The default exit status fails on unsuppressed errors. Use `--fail-on warning`
in strict CI. Findings that require musical judgment remain warnings or info.
Grace notes and cue music do not determine the main part range or clef.

Manifest schema v3 adds `pitch_basis: concert|written`, optional
`range_override`, and justified suppressions:

```yaml
suppressions:
  - rule_id: range.above-practical
    part: violin-i
    reason: Intentional solo harmonic reviewed by the editor
```

Use suppressions narrowly. Never suppress compiler errors or absolute-range
findings merely to make CI pass. Keep schema v1/v2 files unchanged when only
reading or extracting legacy projects; generate schema v3 for new projects.
