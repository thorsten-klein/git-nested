"""Pytest configuration and fixtures for git-nested tests"""

import contextlib
import io
import os
import re
import shlex
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

import git_nested

# Path to a standalone git-nested executable (see scripts/create-python-exe.sh)
# to run the whole suite against instead of the git_nested module in this
# checkout. Every test drives git-nested through cmd_git_nested(), so pointing
# this at the frozen binary tests the artifact that is actually released --
# including everything only the freeze can break: a module PyInstaller did not
# collect, missing package metadata, a data file that is not in the archive.
#
#   GIT_NESTED_EXE=dist/git-nested uv run pytest
#
# Unset (the normal case) nothing changes: the tests run in-process, which is
# faster and is what the coverage numbers come from.
GIT_NESTED_EXE = os.getenv('GIT_NESTED_EXE') or None
if GIT_NESTED_EXE:
    # .absolute(), not .resolve(): the released archive's 'git-nested' is a
    # symlink to a versioned binary (see create-python-exe.sh), and .resolve()
    # would follow it before the name check below ever saw 'git-nested'.
    GIT_NESTED_EXE = Path(GIT_NESTED_EXE).absolute()
    if not os.access(GIT_NESTED_EXE, os.X_OK):
        raise RuntimeError(f"GIT_NESTED_EXE={GIT_NESTED_EXE} is not an executable file")
    # `git nested ...` is git looking up a 'git-nested' on PATH, so the name of
    # the file decides whether the tests reach it at all.
    if GIT_NESTED_EXE.name != 'git-nested':
        raise RuntimeError(f"GIT_NESTED_EXE={GIT_NESTED_EXE} must be named 'git-nested'")


def _version_under_test() -> str:
    """The version the git-nested being tested reports

    Asked of the binary rather than read from this checkout's git_nested: the
    binary carries the version frozen into it at build time, and a mismatch
    with the installed module (a build from another commit, a dirty tree) must
    show up as a failing version test, not as every .gitnested assertion in
    the suite failing at once.
    """
    if not GIT_NESTED_EXE:
        return git_nested.VERSION

    out = subprocess.run([GIT_NESTED_EXE, '--version'], capture_output=True, text=True, check=True).stdout
    match = re.search(r'^git-nested Version:\s*(\S+)', out, re.MULTILINE)
    if not match:
        raise RuntimeError(f"cannot parse a version out of `{GIT_NESTED_EXE} --version`:\n{out}")
    return match.group(1)


VERSION = _version_under_test()

# ============================================================================
# Test Environment
# ============================================================================


@dataclass
class CommandResult:
    """What one git-nested run produced, from either the in-process or subprocess path.

    The two paths are otherwise indistinguishable to a test, so they return
    the same shape -- which is also what gives both of them `.output`.
    """

    returncode: int = 0
    stdout: str = ''
    stderr: str = ''

    @property
    def output(self) -> str:
        """Everything the command said, whichever stream it chose to say it on.

        Assertions about diagnostics go through here rather than through
        `.stdout`/`.stderr`, so that moving a message from one stream to the
        other is not a test change. Assertions about a machine-consumable
        payload -- what `status` and `diff` print for a script to read --
        deliberately keep `.stdout`: for those the stream is the contract.
        """
        return self.stdout + self.stderr


def _as_command_result(result) -> CommandResult:
    """Re-wrap a subprocess.CompletedProcess so that it too has `.output`."""
    return CommandResult(result.returncode, result.stdout, result.stderr)


class NestedTestEnvironment:
    """Test environment with paths and helper methods for git operations.

    Not named Test* on purpose: pytest's `python_classes = ["Test*"]` would
    collect it as a test class the moment a test module imported it (for a
    type hint, say). It is safe today only because conftest.py is never
    collected, which is a coincidence rather than a design.
    """

    def __init__(self, tmp_dir: Path, test_dir: Path):
        self.tmp = tmp_dir
        self.test_dir = test_dir
        self.upstream = tmp_dir / "upstream"
        self.workspace = tmp_dir / "workspace"
        self.test_home = tmp_dir / "home"
        self.defaultbranch = 'master'

    def run(self, cmd, cwd=None, check=True, capture_output=True, text=True, **kwargs):
        """Run a subprocess command

        A captured result is wrapped in CommandResult, so that a test which
        drives git-nested through `env.run` asserts on `.output` the same way
        one that goes through cmd_git_nested does.
        """
        if not isinstance(cmd, str):
            cmd = [str(a) for a in cmd]  # convert all arguments to str
        result = subprocess.run(
            cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=capture_output, text=text, check=check, **kwargs
        )
        return _as_command_result(result) if capture_output and text else result

    def clone_foo(self, path=None):
        path = path or self.workspace / 'foo'
        clone_repo(str(self.upstream / 'foo'), path)

    def clone_bar(self, path=None):
        path = path or self.workspace / 'bar'
        clone_repo(str(self.upstream / 'bar'), path)

    def clone_init(self, path=None):
        # Built on demand rather than by the env fixture: the 'init' upstream
        # is a 5-commit history that only a handful of tests ever clone, and
        # pre-building it charged every test in the suite for it.
        if not (self.upstream / 'init').exists():
            create_upstream_init(self.upstream / 'init')
        path = path or self.workspace / 'init'
        clone_repo(str(self.upstream / 'init'), path)

    def clone_foo_and_bar(self):
        self.clone_foo()
        self.clone_bar()

    def add_new_files(self, *files, cwd=None):
        """Create new files, add to git, and commit"""
        for file in files:
            file_path = Path(cwd) / file if cwd else Path(file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"new file {file}\n")
            subprocess.run(['git', 'add', '--force', str(file)], cwd=cwd, check=True)

        subprocess.run(['git', 'commit', '--quiet', '-m', f'add new file: {files[-1]}'], cwd=cwd, check=True)

    def remove_files(self, *files, cwd=None):
        """Remove files and commit"""
        for file in files:
            subprocess.run(['git', 'rm', file], cwd=cwd, check=True)

        subprocess.run(['git', 'commit', '--quiet', '-m', f'Removed file: {files[-1]}'], cwd=cwd, check=True)

    def modify_files(self, *files, text=None, cwd=None):
        """Modify files (append text) and commit"""
        text = text or 'a new line\n'
        for file in files:
            file_path = Path(cwd) / file if cwd else Path(file)
            with file_path.open('a') as f:
                f.write(f'{text}\n')
            subprocess.run(['git', 'add', str(file)], cwd=cwd, check=True)

        subprocess.run(['git', 'commit', '-m', f'modified file: {files[-1]}'], cwd=cwd, check=True)


# ============================================================================
# Repository Creation
# ============================================================================


def clone_repo(upstream: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'clone', upstream, path], check=True, capture_output=True)
    name = path.name
    subprocess.run(['git', 'config', 'user.name', f'{name.capitalize()}User'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.email', f'{name}@{name}'], cwd=path, check=True)


def create_upstream_repo(repo_path: Path) -> Path:
    """Create a bare git repository and return a temporary working directory"""
    repo_path.mkdir(parents=True)
    subprocess.run(['git', 'init', '--bare'], cwd=repo_path, check=True, capture_output=True)

    # Create a temporary working directory
    work_dir = repo_path.parent / (repo_path.name + ".tmp")
    work_dir.mkdir(exist_ok=True)
    subprocess.run(['git', 'init'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=work_dir, check=True, capture_output=True)
    return work_dir


def create_upstream_foo(repo_path: Path):
    """Create the foo test repository with a single file"""
    work_dir = create_upstream_repo(repo_path)

    # Commit 1: Create empty Foo file and commit
    (work_dir / 'Foo').touch()
    subprocess.run(['git', 'add', 'Foo'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Foo'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    shutil.rmtree(work_dir)


def create_upstream_bar(repo_path: Path):
    """Create the bar test repository with files and tags"""
    work_dir = create_upstream_repo(repo_path)

    # Commit 1: Create empty Bar file
    (work_dir / 'Bar').touch()
    subprocess.run(['git', 'add', 'Bar'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Bar'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'tag', 'A'], cwd=work_dir, check=True, capture_output=True)

    # Commit 2: Create bard/Bard file
    (work_dir / 'bard').mkdir()
    (work_dir / 'bard' / 'Bard').touch()
    subprocess.run(['git', 'add', 'bard/Bard'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'bard/Bard'], cwd=work_dir, check=True, capture_output=True)

    # Push to bare repo (including tags)
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'push', str(repo_path), 'A'], cwd=work_dir, check=True, capture_output=True)

    shutil.rmtree(work_dir)


def create_upstream_init(repo_path: Path):
    """Create the init test repository with a subdir to be converted to nested repo"""
    work_dir = create_upstream_repo(repo_path)

    # Commit 1: Initial ReadMe
    readme_content = textwrap.dedent(
        """\
        This is a repo to test `git subrepo init`.

        We will make a short history with a subdir, then we can turn that subdir into a
        subrepo.
        """
    )
    (work_dir / 'ReadMe').write_text(readme_content)
    subprocess.run(['git', 'add', 'ReadMe'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=work_dir, check=True, capture_output=True)

    # Commit 2: Add doc/init.swim
    (work_dir / 'doc').mkdir()
    doc_content = textwrap.dedent(
        """\
        == Subrepo Init!

        This is a file to test the `git subrepo init` command.
        """
    )
    (work_dir / 'doc' / 'init.swim').write_text(doc_content)
    subprocess.run(['git', 'add', 'doc/init.swim'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Add a file in a subdir.'], cwd=work_dir, check=True, capture_output=True)

    # Commit 3: Modify ReadMe
    readme_content = textwrap.dedent(
        """\
        This is a repo to test `git subrepo init`.

        We will make a short history with a subdir, then we can turn that subdir into a
        subrepo.

        This repo will go in the git-subrepo test suite.
        """
    )
    (work_dir / 'ReadMe').write_text(readme_content)
    subprocess.run(['git', 'add', 'ReadMe'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Add a commit to the mainline.'],
        cwd=work_dir,
        check=True,
        capture_output=True,
    )

    # Commit 4: Modify doc/init.swim
    doc_content = textwrap.dedent(
        """\
        == Subrepo Init!

        This is a file to test the `git subrepo init` command.

        It lives under the doc directory which will become a subrepo.
        """
    )
    (work_dir / 'doc' / 'init.swim').write_text(doc_content)
    subprocess.run(['git', 'add', 'doc/init.swim'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Add a commit to the subdir.'],
        cwd=work_dir,
        check=True,
        capture_output=True,
    )

    # Commit 5: Modify both files
    readme_content = textwrap.dedent(
        """\
        This is a repo to test `git subrepo init`.

        We will make a short history with a subdir, then we can turn that subdir into a
        subrepo.

        This repo will go in the git-subrepo test suite.

        """
    )
    (work_dir / 'ReadMe').write_text(readme_content)
    doc_content = textwrap.dedent(
        """\
        == Subrepo Init!

        This is a file to test the `git subrepo init` command.

        It lives under the doc directory which will become a subrepo.

        """
    )
    (work_dir / 'doc' / 'init.swim').write_text(doc_content)
    subprocess.run(['git', 'add', 'ReadMe', 'doc/init.swim'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Add a commit that affects both…'],
        cwd=work_dir,
        check=True,
        capture_output=True,
    )

    # Push to bare repo
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    shutil.rmtree(work_dir)


# ============================================================================
# Fixtures
# ============================================================================


@contextlib.contextmanager
def update_env(env_vars: dict[str, str]):
    """Temporarily set environment variables for git isolation"""
    original_env = dict(os.environ)
    os.environ.update(env_vars)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
def env(tmp_path):
    """Setup isolated test environment with git repos"""
    root_dir = Path(__file__).parent.parent
    tmp_dir = Path(tmp_path)
    test_env = NestedTestEnvironment(tmp_dir, root_dir)

    # Create home directory for git config
    test_env.test_home.mkdir()

    # Set up isolated environment variables
    env_vars = {
        'HOME': str(test_env.test_home),
        'GIT_CONFIG_GLOBAL': str(test_env.test_home / '.gitconfig'),
        'GIT_CONFIG_SYSTEM': '/dev/null',
        # bin/ holds the 'git-nested' launcher `git nested` dispatches to --
        # replaced by the directory of the frozen binary when testing that.
        'PATH': f"{GIT_NESTED_EXE.parent if GIT_NESTED_EXE else root_dir / 'bin'}:{os.getenv('PATH')}",
    }

    with update_env(env_vars):
        # Configure git
        subprocess.run(['git', 'config', '--global', 'user.name', 'Test User'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'test@example.com'], check=True)
        subprocess.run(['git', 'config', '--global', 'init.defaultBranch', 'master'], check=True)

        # Create test repositories. 'init' is deliberately absent -- it is
        # built lazily by NestedTestEnvironment.clone_init, see there.
        create_upstream_foo(test_env.upstream / 'foo')
        create_upstream_bar(test_env.upstream / 'bar')

        yield test_env


@pytest.fixture
def foo_bar_cloned(env):
    """Setup foo and bar repos with bar nested into foo"""
    env.clone_foo()
    env.clone_bar()
    return env


@pytest.fixture
def foo_bar_cloned_and_nested(foo_bar_cloned):
    env = foo_bar_cloned
    cmd_git_nested(['clone', str(env.upstream / 'bar')], env.workspace / 'foo')
    return env


# ============================================================================
# Assertion Helpers
# ============================================================================


def assert_in_index(file_path: str, cwd, should_exist: bool = True):
    """Assert that a file exists (or doesn't exist) in the git index"""
    result = subprocess.run(
        ['git', 'ls-tree', '--full-tree', '--name-only', '-r', 'HEAD', file_path],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    exists = bool(result.stdout.strip())

    if should_exist:
        assert exists, f"File '{file_path}' should exist in index but doesn't"
    else:
        assert not exists, f"File '{file_path}' should not exist in index but does"


def assert_gitnested_comment_block(gitnested_path):
    """Assert that .gitnested YAML file has the correct comment header"""
    expected = textwrap.dedent(
        """\
        # This subdirectory is managed by "git nested".
        # Refer to: https://github.com/thorsten-klein/git-nested#readme
        #"""
    )

    with Path(gitnested_path).open() as f:
        content = f.read()

    comment_lines = [line for line in content.split('\n') if line.startswith('#')]
    actual = '\n'.join(comment_lines)

    assert actual == expected, f"Comment block mismatch.\nExpected:\n{expected}\nActual:\n{actual}"


def _assert_yaml_field(nested_data: dict, field: str, value: str | None):
    """Assert that nested_data[field] matches value ('' and None are interchangeable)"""
    if value is None:
        return  # skip
    actual_value = nested_data.get(field)
    expected_values = [value]
    if value == '':
        expected_values.append(None)  # can be empty or None
    assert actual_value in expected_values


def assert_gitnested_field(
    gitnested_path: Path | str,
    remote: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
    parent: str | None = None,
    method: str | None = None,
    version: str | None = None,
):
    """Assert that according fields in .gitnested YAML file have the expected value"""
    assert Path(gitnested_path).exists()
    with Path(gitnested_path).open() as f:
        data = yaml.safe_load(f) or {}

    if version is None:
        version = VERSION

    assert_gitnested_comment_block(gitnested_path)
    nested_data = data.get('nested', {})
    _assert_yaml_field(nested_data, 'remote', remote)
    _assert_yaml_field(nested_data, 'branch', branch)
    _assert_yaml_field(nested_data, 'commit', commit)
    _assert_yaml_field(nested_data, 'parent', parent)
    _assert_yaml_field(nested_data, 'method', method)
    _assert_yaml_field(nested_data, 'cmdver', version)


def _get_commit_info(cwd, ref: str, format_str: str) -> str:
    """Get one piece of commit info via `git log --format=...`"""
    result = subprocess.run(
        ['git', 'log', '-1', f'--format={format_str}', ref], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _assert_changed_files(cwd, ref: str, changed_files) -> None:
    """Assert that ref's changed files match changed_files (list=ordered, set=unordered)"""
    result = subprocess.run(
        ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    actual_files = result.stdout.strip().split('\n') if result.stdout.strip() else []

    # Support both list (ordered) and set (unordered) comparison
    if isinstance(changed_files, set):
        assert set(actual_files) == changed_files
    else:
        assert actual_files == list(changed_files)


def assert_commit(
    cwd,
    ref: str = 'HEAD',
    commit_title: str | None = None,
    commit_msg: str | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
    committer_name: str | None = None,
    committer_email: str | None = None,
    author_date: str | None = None,
    committer_date: str | None = None,
    changed_files=None,
):
    """Assert commit metadata matches expected values

    Args:
        cwd: Repository path
        ref: Git ref to check (default: 'HEAD')
        commit_title: Expected commit title/subject (first line of message)
        commit_msg: Expected full commit message
        author_name: Expected author name
        author_email: Expected author email
        committer_name: Expected committer name
        committer_email: Expected committer email
        author_date: Expected author date
        committer_date: Expected committer date
        changed_files: Expected list of changed files (paths). Can be exact list or set for unordered comparison.
    """
    # (expected value, git log format string) -- commit_msg's expected value is
    # compared as-is: _get_commit_info() already strips stdout, so re-stripping
    # it (as the old inline check did) never changed the comparison.
    checks = [
        (commit_title, '%s'),
        (commit_msg, '%B'),
        (author_name, '%an'),
        (author_email, '%ae'),
        (committer_name, '%cn'),
        (committer_email, '%ce'),
        (author_date, '%ad'),
        (committer_date, '%cd'),
    ]
    for expected, format_str in checks:
        if expected is not None:
            assert _get_commit_info(cwd, ref, format_str) == expected

    if changed_files is not None:
        _assert_changed_files(cwd, ref, changed_files)


def assert_commit_count(repo_path, expected_count: int, ref: str = 'HEAD'):
    """Assert the number of commits in a ref"""
    result = subprocess.run(
        ['git', 'rev-list', '--count', ref], cwd=repo_path, capture_output=True, text=True, check=True
    )
    actual_count = int(result.stdout.strip())
    assert actual_count == expected_count, f"Commit count should be {expected_count} but is {actual_count}"


def assert_output_like(output: str, pattern: str, description: str = ""):
    """Assert that output matches a regex pattern"""
    assert re.search(pattern, output), f"{description}\nPattern '{pattern}' not found in:\n{output}"


def assert_output_unlike(output: str, pattern: str, description: str = ""):
    """Assert that output doesn't match a regex pattern"""
    assert not re.search(pattern, output), f"{description}\nPattern '{pattern}' should not be found in:\n{output}"


# ============================================================================
# Git Utility Functions
# ============================================================================


def git_get_commit_msg(cwd, args: list[str] | None = None):
    """Get the commit message for a git commit"""
    args = args or ['--format=%B', '-1']
    result = subprocess.run(['git', 'log', *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def git_read_head(cwd: Path):
    """Get the commit message for a git commit"""
    return (cwd / '.git' / 'HEAD').read_text().strip()


def git_rev_parse(args: list[str], cwd) -> str:
    """Get the commit SHA for a git ref"""
    result = subprocess.run(['git', 'rev-parse', *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def git_config(key: str, cwd, file=None):
    """Get a git config value"""
    cmd = ['git', 'config']
    if file:
        cmd.append(f'--file={file}')
    cmd.append(key)

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _raise_if_failed(cmd_and_args: list[str], result, check: bool):
    """Raise GitNestedError if the subprocess failed and check is set"""
    if not (check and result.returncode):
        return
    # GitNestedError rather than a bare Exception: in-process the app's own
    # error type propagates out of app.main(), and tests match on it. The
    # message is the stderr the command produced, so `match=` keeps working;
    # print_to_stderr would duplicate it into the captured output.
    raise git_nested.GitNestedError(
        f"Command failed with exit code {result.returncode}: {shlex.join(cmd_and_args)}\n{result.stderr}",
        print_to_stderr=False,
    )


def cmd_git_nested_subprocess(args, cwd, check: bool = True):
    """Run a git nested command as subprocess and return the result

    Invoked as `git nested`, not as the executable directly: that is how users
    run it, and it only works if git finds a 'git-nested' on PATH -- which the
    env fixture points at either bin/ or the frozen binary.
    """
    args = shlex.split(args) if isinstance(args, str) else [str(a) for a in args]

    # `git nested --help` never reaches git-nested: git answers every
    # '--help'/'-h' itself by opening man git-nested, which is not installed
    # and exits 16. Only the help output is unreachable that way, so those
    # calls go straight to the executable -- which is also what git's own man
    # page tells users to do when there is no manual entry.
    cmd = ['git-nested'] if {'--help', '-h'} & set(args) else ['git', 'nested']

    result = subprocess.run(cmd + args, cwd=cwd, capture_output=True, text=True, check=False)
    _raise_if_failed(cmd + args, result, check)
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _handle_system_exit(e: SystemExit, retval, check: bool):
    """Record a SystemExit's code on retval, re-raising as Exception if check is set"""
    retval.returncode = e.code
    if check and e.code:
        raise Exception(f'Command failed with exit code {e.code}') from e


def _handle_run_exception(e: Exception, retval, check: bool):
    """Record a failure on retval, re-raising it if check is set"""
    retval.returncode = 1
    if check:
        raise e


def _run_inprocess(args: list[str], cwd, check: bool):
    """Run a git nested command in-process and return a result-like namespace"""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    retval = CommandResult()

    with git_nested.chdir(cwd), contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            app = git_nested.GitNestedCommand()
            app.main(args)
        except SystemExit as e:
            _handle_system_exit(e, retval, check)
        except Exception as e:
            _handle_run_exception(e, retval, check)

    retval.stdout = stdout_buf.getvalue()
    retval.stderr = stderr_buf.getvalue()
    return retval


def cmd_git_nested(args: list[str] | str, cwd, check: bool = True):
    """Run a git nested command and return the result"""
    # Against the frozen binary there is no in-process path to take: it is a
    # separate program, so the same command goes through a subprocess instead.
    if GIT_NESTED_EXE:
        return cmd_git_nested_subprocess(args, cwd, check=check)

    args = shlex.split(args) if isinstance(args, str) else args
    return _run_inprocess(args, cwd, check)


# ============================================================================
# General utilities
# ============================================================================


def _tree_entry_lines(entry: Path, prefix: str, is_last: bool) -> list[str]:
    """Build the tree-drawing lines for one entry, plus its recursive subtree if a dir"""
    connector = "└── " if is_last else "├── "
    lines = [prefix + connector + entry.name]
    if not entry.is_dir():
        return lines
    indent = "    " if is_last else "│   "
    sub = tree(entry, prefix + indent)
    if sub:
        lines.extend(sub.split("\n"))
    return lines


def tree(path: Path, prefix="") -> str:
    lines = []
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    for i, entry in enumerate(entries):
        lines.extend(_tree_entry_lines(entry, prefix, i == len(entries) - 1))
    return "\n".join(lines)


# ============================================================================
# Collection
# ============================================================================


def pytest_collection_modifyitems(items):
    """Mark every test by the directory it lives in.

    tests/unit is fast and uses FakeGit; tests/e2e shells out to real git. The
    split is already expressed by the layout, so deriving the marker from the
    path keeps it true by construction rather than asking ~190 tests to carry
    a decorator that could drift from where the file actually sits.
    """
    for item in items:
        parts = item.path.parts
        if 'unit' in parts:
            item.add_marker('unit')
        elif 'e2e' in parts:
            item.add_marker('e2e')
