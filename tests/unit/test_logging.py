import contextlib
import io

import pytest

from git_nested import Flags, GitNested, GitNestedError, output


def test_log_disabled():
    """Test verbose() doesn't print when verbose=False"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.verbose("this is my text", Flags(verbose=False))
    assert stdout.getvalue() == ""


def test_log_verbose():
    """Test verbose() prints with verbose=True"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.verbose("this is my text", Flags(verbose=True))
    assert stdout.getvalue().strip() == "* this is my text"


def test_say_normal():
    """Test say() prints when quiet=False"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.say("normal message", Flags(quiet=False))
    assert stdout.getvalue().strip() == "normal message"


def test_say_quiet():
    """Test say() doesn't print when quiet=True"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.say("should not appear", Flags(quiet=True))
    assert stdout.getvalue() == ""


def test_say_multiple_messages():
    """Test say() with multiple messages"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.say("first message", Flags(quiet=False))
        output.say("second message", Flags(quiet=False))
    printed = stdout.getvalue()
    assert "first message" in printed
    assert "second message" in printed


def test_error_prints_to_stderr():
    """Test error() prints to stderr"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr), pytest.raises(GitNestedError):
        runner.error("error message")
    assert stderr.getvalue().strip() == "git-nested: error message"


def test_error_raises_exception():
    """Test error() raises GitNestedError"""
    runner = GitNested()
    with pytest.raises(GitNestedError) as exc_info:
        runner.error("test error")
    assert str(exc_info.value) == "test error"


def test_error_exception_message():
    """Test error() exception contains the message"""
    runner = GitNested()
    error_msg = "Something went wrong"
    with pytest.raises(GitNestedError) as exc_info:
        runner.error(error_msg)
    assert exc_info.value.message == error_msg


def test_error_format():
    """Test error() output format includes 'git-nested:' prefix"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr), pytest.raises(GitNestedError):
        runner.error("test")
    printed = stderr.getvalue()
    assert printed.startswith("git-nested:")
    assert "test" in printed


def test_usage_error_prints_to_stderr():
    """Test usage_error() prints to stderr"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr), pytest.raises(SystemExit):
        runner.usage_error("usage error message")
    assert stderr.getvalue().strip() == "git-nested: usage error message"


def test_usage_error_exits_with_code_1():
    """Test usage_error() calls sys.exit(1)"""
    runner = GitNested()
    with pytest.raises(SystemExit) as exc_info:
        runner.usage_error("usage error")
    assert exc_info.value.code == 1


def test_usage_error_format():
    """Test usage_error() output format includes 'git-nested:' prefix"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr), pytest.raises(SystemExit):
        runner.usage_error("invalid option")
    printed = stderr.getvalue()
    assert printed.startswith("git-nested:")
    assert "invalid option" in printed


def test_error_vs_usage_error_difference():
    """Test that error() raises GitNestedError while usage_error() calls sys.exit"""
    runner = GitNested()

    # error() should raise GitNestedError
    with pytest.raises(GitNestedError):
        runner.error("regular error")

    # usage_error() should raise SystemExit
    with pytest.raises(SystemExit):
        runner.usage_error("usage error")


def test_log_message_with_special_characters():
    """Test verbose() with special characters"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.verbose("message with #, &, @, and 日本語", Flags(verbose=True))
    assert "message with #, &, @, and 日本語" in stdout.getvalue()


def test_say_message_with_newlines():
    """Test say() preserves newlines in message"""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        output.say("line1\nline2\nline3", Flags(quiet=False))
    printed = stdout.getvalue().splitlines()
    assert "line1" in printed
    assert "line2" in printed
    assert "line3" in printed
