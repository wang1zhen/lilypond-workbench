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
