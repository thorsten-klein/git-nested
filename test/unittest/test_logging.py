import contextlib
import io
import pytest
from git_nested import GitNested, GitNestedError


def test_log_disabled():
    """Test verbose() doesn't print when verbose=False"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.verbose = False
    with contextlib.redirect_stdout(stdout):
        runner.verbose("this is my text")
    assert stdout.getvalue() == ""


def test_log_verbose():
    """Test verbose() prints with verbose=True"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.verbose = True
    with contextlib.redirect_stdout(stdout):
        runner.verbose("this is my text")
    assert stdout.getvalue().strip() == "* this is my text"


def test_say_normal():
    """Test say() prints when quiet=False"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.quiet = False
    with contextlib.redirect_stdout(stdout):
        runner.say("normal message")
    assert stdout.getvalue().strip() == "normal message"


def test_say_quiet():
    """Test say() doesn't print when quiet=True"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.quiet = True
    with contextlib.redirect_stdout(stdout):
        runner.say("should not appear")
    assert stdout.getvalue() == ""


def test_say_multiple_messages():
    """Test say() with multiple messages"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.quiet = False
    with contextlib.redirect_stdout(stdout):
        runner.say("first message")
        runner.say("second message")
    output = stdout.getvalue()
    assert "first message" in output
    assert "second message" in output


def test_error_prints_to_stderr():
    """Test error() prints to stderr"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr):
        with pytest.raises(GitNestedError):
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
    with contextlib.redirect_stderr(stderr):
        with pytest.raises(GitNestedError):
            runner.error("test")
    output = stderr.getvalue()
    assert output.startswith("git-nested:")
    assert "test" in output


def test_usage_error_prints_to_stderr():
    """Test usage_error() prints to stderr"""
    stderr = io.StringIO()
    runner = GitNested()
    with contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit):
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
    with contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit):
            runner.usage_error("invalid option")
    output = stderr.getvalue()
    assert output.startswith("git-nested:")
    assert "invalid option" in output


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
    runner = GitNested()
    runner.flags.verbose = True
    with contextlib.redirect_stdout(stdout):
        runner.verbose("message with #, &, @, and 日本語")
    assert "message with #, &, @, and 日本語" in stdout.getvalue()


def test_say_message_with_newlines():
    """Test say() preserves newlines in message"""
    stdout = io.StringIO()
    runner = GitNested()
    runner.flags.quiet = False
    with contextlib.redirect_stdout(stdout):
        runner.say("line1\nline2\nline3")
    output = stdout.getvalue().splitlines()
    assert "line1" in output
    assert "line2" in output
    assert "line3" in output
