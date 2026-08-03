# Validation and repair

Run `validate score.ly --json`. It combines a conservative source-level measure check with LilyPond's authoritative parser and bar checks.

Repair in this order:

1. Missing includes and fatal Scheme errors.
2. Syntax errors and unmatched `{}`, `<< >>`, parentheses, or strings. The reported location can follow the actual mistake.
3. Invalid commands or note names, including pitch-language mismatches.
4. Bar-duration failures: count notes, rests, skips, dots, multipliers, tuplets, pickups, and inherited durations.
5. Lyric alignment and engraving warnings.

The static checker intentionally reports partial analysis for simultaneous music, custom functions, and Scheme. Do not interpret absence of a static warning as proof; rely on the validation compile.

Make one focused repair, validate again, and regenerate outputs. Do not rewrite a large file to fix one local diagnostic.
