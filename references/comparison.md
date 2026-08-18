# Semantic comparison and indexing

`validate` and `lint` answer whether a score is correct. `diff` answers whether
an edit did only what was asked. Use it whenever you modify an existing score:
copy the original first, edit, then compare.

```sh
cp score.ly /tmp/score.before.ly
# make the edit
diff /tmp/score.before.ly score.ly --variable violinMusic --expect-measures 37-40
```

A text diff cannot answer this question. Inside `\relative`, editing one pitch
silently transposes everything after it while the text shows a single-character
change; reindenting or converting to absolute pitch rewrites every line while
changing no music. `diff` walks both semantic indexes instead, so it reports
pitch, accidental, duration, key, meter, clef, dynamic, articulation, tempo,
repeat, and barline differences with their measure, beat, and source location,
and reports nothing for edits that only touch text.

Two ways to make the intended scope enforceable:

- `--expect-measures 12,37-40` fails when anything outside those measures
  changed. Use it when the request named specific bars.
- `--fail-on-change` fails on any musical difference at all. Use it to prove
  that a reformat, a rename, a comment pass, or an include refactor was
  editorially neutral.

Both exit 1 on violation with one located error per unexpected change, so the
report is actionable without reading the JSON. Without either flag the command
only reports and exits 0.

Use `--new-variable` when the variable was renamed between the two files.

## Reading the index directly

`index score.ly --variable violinMusic` reports the same picture the clef and
lint analysers consume: every event with its offset, duration, written pitch
(`C4`, `Ab4`, `F#5`), diatonic position, and source location; every marker; and
the reconstructed measures with their meters. Prefer it over rereading the
source when you need to know what a variable actually contains after includes,
`\relative`, `\transpose`, tuplets, and repeats have been resolved.

## Limits worth knowing before you trust a result

- One music variable per invocation. Compare each part separately.
- Pitches are written, not concert. A `\transpose` shifts diatonic steps, so a
  transposed accidental is reported as written rather than respelled.
- Grace notes and cue music appear in the index and in comparisons; they are
  flagged so they can be filtered.
- Simultaneous voices are indexed in traversal order. Reordering two
  independent voices inside `<< >>` therefore reads as a difference.
- python-ly cannot parse a `\repeat` that directly follows a `\tempo` mark and
  drops its music. `index` and `diff` emit `SEMANTIC_REPEAT_DROPPED` rather than
  reporting a short score as complete. Separate the two commands to fix it.
- Equal fingerprints mean identical dependency paths and bytes; two different
  files never share one, so compare the reported `changes`, not fingerprints.
