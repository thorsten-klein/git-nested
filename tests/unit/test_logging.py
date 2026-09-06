import contextlib
import io
import logging

import pytest

from git_nested import Flags, GitNested, GitNestedError, GitRunner, output


def test_a_library_import_prints_nothing():
    """Nothing reaches stderr until configure() has run."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        output.say("unheard")
    assert stderr.getvalue() == ""


def test_say_is_printed(printing, no_colour, capsys):
    """say() reports at the default level."""
    output.say("normal message")
    assert capsys.readouterr().err == "normal message\n"


def test_say_is_silent_when_quiet(printing, no_colour, capsys):
    """-q lifts the level above say()."""
    output.set_level(Flags(quiet=True))
    output.say("should not appear")
    assert capsys.readouterr().err == ""


def test_verbose_is_silent_by_default(printing, no_colour, capsys):
    """verbose() says nothing until -v asks for it."""
    output.verbose("this is my text")
    assert capsys.readouterr().err == ""


def test_verbose_is_printed_with_one_v(printing, no_colour, capsys):
    """-v turns the narration on, marked with '*'."""
    output.set_level(Flags(verbose=1))
    output.verbose("this is my text")
    assert capsys.readouterr().err == "* this is my text\n"


def test_trace_needs_two_vs(printing, no_colour, capsys):
    """-v narrates the steps; only -vv lists the git commands behind them."""
    output.set_level(Flags(verbose=1))
    output.trace('git rev-parse HEAD')
    assert capsys.readouterr().err == ""

    output.set_level(Flags(verbose=2))
    output.trace('git rev-parse HEAD')
    assert capsys.readouterr().err == "$ git rev-parse HEAD\n"


def test_a_git_command_is_traced(printing, no_colour, capsys):
    """GitRunner announces every invocation it makes, for -vv to pick up."""
    git = GitRunner()  # constructed first: its own probing would be traced too
    output.set_level(Flags(verbose=2))
    git.check_output(['--version'])
    assert capsys.readouterr().err == "$ git --version\n"


def test_warn_survives_quiet(printing, no_colour, capsys):
    """A warning is worth hearing even when the user asked for -q."""
    output.set_level(Flags(quiet=True))
    output.warn("no remote")
    assert capsys.readouterr().err == "git-nested: no remote\n"


def test_several_messages_all_arrive(printing, no_colour, capsys):
    """Consecutive say() calls each get their own line."""
    output.say("first message")
    output.say("second message")
    assert capsys.readouterr().err == "first message\nsecond message\n"


def test_a_multiline_message_keeps_its_newlines(printing, no_colour, capsys):
    """say() does not reflow what it is given."""
    output.say("line1\nline2\nline3")
    assert capsys.readouterr().err == "line1\nline2\nline3\n"


def test_non_ascii_survives(printing, no_colour, capsys):
    """The layer is transparent to whatever the message contains."""
    output.set_level(Flags(verbose=1))
    output.verbose("message with #, &, @, and 日本語")
    assert capsys.readouterr().err == "* message with #, &, @, and 日本語\n"


def test_payload_goes_to_stdout(no_colour):
    """A command's actual result is not a diagnostic and is never gated."""
    output.set_level(Flags(quiet=True))
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.payload("subdir/one")
    assert stdout.getvalue() == "subdir/one\n"


def test_configure_is_idempotent(printing, no_colour, capsys):
    """A second configure() must not double every line."""
    detach = output.configure()
    try:
        output.say("once")
    finally:
        detach()
    assert capsys.readouterr().err == "once\n"


def test_detaching_stops_the_printing(no_colour, capsys):
    """What configure() returns is what puts the layer back to silent."""
    output.configure()()
    output.say("unheard")
    assert capsys.readouterr().err == ""


def test_a_tty_gets_colour(printing, monkeypatch, capsys):
    """FORCE_COLOR stands in for the tty the test suite does not have."""
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('FORCE_COLOR', '1')
    output.say("plain")
    output.warn("marked")
    assert capsys.readouterr().err == "plain\n\033[33mgit-nested: marked\033[0m\n"


def test_no_color_beats_force_color(printing, monkeypatch, capsys):
    """NO_COLOR is checked first, so setting both means no colour."""
    monkeypatch.setenv('NO_COLOR', '1')
    monkeypatch.setenv('FORCE_COLOR', '1')
    output.warn("marked")
    assert capsys.readouterr().err == "git-nested: marked\n"


def test_colour_follows_the_stream_when_nothing_is_forced(printing, monkeypatch, capsys):
    """With neither variable set, it comes down to whether stderr is a tty."""
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    output.warn("marked")
    assert capsys.readouterr().err == "git-nested: marked\n"


def test_the_error_level_is_red(printing, monkeypatch, capsys):
    """error() is the loudest thing the layer prints, and looks it."""
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('FORCE_COLOR', '1')
    with pytest.raises(GitNestedError):
        output.error("boom")
    assert capsys.readouterr().err == "\033[31mgit-nested: boom\033[0m\n"


def test_error_prints_to_stderr(printing, no_colour, capsys):
    """error() reports before it raises."""
    with pytest.raises(GitNestedError):
        GitNested().error("error message")
    assert capsys.readouterr().err == "git-nested: error message\n"


def test_error_raises_exception():
    """error() raises GitNestedError carrying the bare message."""
    with pytest.raises(GitNestedError) as exc_info:
        GitNested().error("test error")
    assert str(exc_info.value) == "test error"


def test_error_exception_message():
    """The exception keeps the message on .message too."""
    with pytest.raises(GitNestedError) as exc_info:
        GitNested().error("Something went wrong")
    assert exc_info.value.message == "Something went wrong"


def test_usage_error_prints_to_stderr(printing, no_colour, capsys):
    """usage_error() reports before it exits."""
    with pytest.raises(SystemExit):
        GitNested().usage_error("usage error message")
    assert capsys.readouterr().err == "git-nested: usage error message\n"


def test_usage_error_exits_with_code_1():
    """usage_error() leaves the process with status 1."""
    with pytest.raises(SystemExit) as exc_info:
        GitNested().usage_error("usage error")
    assert exc_info.value.code == 1


def test_error_vs_usage_error_difference():
    """error() raises for main() to map; usage_error() exits on the spot."""
    runner = GitNested()
    with pytest.raises(GitNestedError):
        runner.error("regular error")
    with pytest.raises(SystemExit):
        runner.usage_error("usage error")


def test_the_default_level_is_info():
    """configure() alone is enough to hear say(), before any flag is parsed."""
    output.configure()()
    assert output.LOGGER.level == logging.INFO
