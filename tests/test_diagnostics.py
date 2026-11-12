from lilypond_workbench.diagnostics import parse_lilypond_log


def test_parse_location_and_bar_warning() -> None:
    issues = parse_lilypond_log("score.ly:12:7: warning: bar check failed at: 3/4")
    assert len(issues) == 1
    assert issues[0].code == "BAR_DURATION"
    assert issues[0].line == 12
    assert issues[0].column == 7


def test_deduplicates_identical_messages() -> None:
    text = "score.ly:2:1: error: syntax error, unexpected }\nscore.ly:2:1: error: syntax error, unexpected }"
    issues = parse_lilypond_log(text)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].code == "SYNTAX_ERROR"


def test_fontconfig_cache_message_is_nonfatal() -> None:
    issues = parse_lilypond_log("Fontconfig error: No writable cache directories")
    assert issues[0].severity == "warning"
    assert issues[0].code == "FONT_CACHE_UNWRITABLE"


# Captured verbatim from LilyPond 2.24.4 compiling a 2.26.0 score whose includes all exist.
VERSION_MISMATCH_LOG = """Processing `haruhikage.ly'
Parsing...
error: program too old: 2.24.4 (file requires: 2.26.0)
Interpreting music...
Preprocessing graphical objects...
Finding the ideal number of pages...
Fitting music on 1 page...
Drawing systems...
Converting to `haruhikage.pdf'...
fatal error: failed files: "haruhikage.ly"
"""

# Captured verbatim from LilyPond 2.24.4 compiling a score with a genuinely missing include.
MISSING_INCLUDE_LOG = """Processing `missing.ly'
Parsing...
missing.ly:2:10: error: cannot find file: `parts/does-not-exist.ily'
(search path: `/usr/share/lilypond/2.24.4/ly:/usr/share/lilypond/2.24.4/ps:')
\\include
         "parts/does-not-exist.ily"
Interpreting music...
Preprocessing graphical objects...
Finding the ideal number of pages...
Fitting music on 1 page...
Drawing systems...
Converting to `missing.pdf'...
fatal error: failed files: "missing.ly"
"""


def test_version_error_is_not_misclassified_as_missing_include() -> None:
    issues = parse_lilypond_log(VERSION_MISMATCH_LOG)
    assert [issue.code for issue in issues] == ["VERSION_MISMATCH", "LILYPOND_ERROR"]
    version_issue, summary = issues
    assert version_issue.severity == "error"
    assert "program too old" in version_issue.message
    assert summary.severity == "error"
    assert "failed files" in summary.message
    assert all(issue.code != "INCLUDE_NOT_FOUND" for issue in issues)


def test_missing_include_is_reported_without_summary_false_positive() -> None:
    issues = parse_lilypond_log(MISSING_INCLUDE_LOG)
    include_issues = [issue for issue in issues if issue.code == "INCLUDE_NOT_FOUND"]
    assert len(include_issues) == 1
    assert include_issues[0].file == "missing.ly"
    assert include_issues[0].line == 2
    assert include_issues[0].column == 10
    assert "cannot find file" in include_issues[0].message
    assert any(issue.severity == "error" and "failed files" in issue.message for issue in issues)
