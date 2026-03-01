"""Pytest configuration and fixtures for git-nested tests"""

import git_nested

import contextlib
import io
import os
import re
import shlex
import shutil
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# ============================================================================
# Test Environment
# ============================================================================


class TestEnvironment:
    """Test environment with paths and helper methods for git operations"""

    def __init__(self, tmp_dir: Path, test_dir: Path):
        self.tmp = tmp_dir
        self.test_dir = test_dir
        self.upstream = tmp_dir / "upstream"
        self.workspace = tmp_dir / "workspace"
        self.test_home = tmp_dir / "home"
        self.defaultbranch = 'master'

    def run(self, cmd, cwd=None, check=True, capture_output=True, text=True, **kwargs):
        """Run a subprocess command"""
        if isinstance(cmd, str):
            return subprocess.run(
                cmd, shell=True, cwd=cwd, capture_output=capture_output, text=text, check=check, **kwargs
            )
        else:
            cmd = [str(a) for a in cmd]  # convert all arguments to str
            return subprocess.run(cmd, cwd=cwd, capture_output=capture_output, text=text, check=check, **kwargs)

    def clone_foo(self, path=None):
        path = path or self.workspace / 'foo'
        clone_repo(str(self.upstream / 'foo'), path)

    def clone_bar(self, path=None):
        path = path or self.workspace / 'bar'
        clone_repo(str(self.upstream / 'bar'), path)

    def clone_init(self, path=None):
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
            with open(file_path, 'a') as f:
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


@pytest.fixture(scope='function')
def env(tmp_path):
    """Setup isolated test environment with git repos"""
    root_dir = Path(__file__).parent.parent
    tmp_dir = Path(tmp_path)
    test_env = TestEnvironment(tmp_dir, root_dir)

    # Create home directory for git config
    test_env.test_home.mkdir()

    # Set up isolated environment variables
    env_vars = {
        'HOME': str(test_env.test_home),
        'GIT_CONFIG_GLOBAL': str(test_env.test_home / '.gitconfig'),
        'GIT_CONFIG_SYSTEM': '/dev/null',
        'PATH': f"{root_dir / 'lib'}:{os.getenv('PATH')}",
    }

    with update_env(env_vars):
        # Configure git
        subprocess.run(['git', 'config', '--global', 'user.name', 'Test User'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'test@example.com'], check=True)
        subprocess.run(['git', 'config', '--global', 'init.defaultBranch', 'master'], check=True)

        # Create test repositories
        create_upstream_foo(test_env.upstream / 'foo')
        create_upstream_bar(test_env.upstream / 'bar')
        create_upstream_init(test_env.upstream / 'init')

        yield test_env


@pytest.fixture
def foo_bar_cloned(env):
    """Setup foo and bar repos with bar nested into foo"""
    env.clone_foo()
    env.clone_bar()
    yield env


@pytest.fixture
def foo_bar_cloned_and_nested(foo_bar_cloned):
    env = foo_bar_cloned
    cmd_git_nested(['clone', str(env.upstream / 'bar')], env.workspace / 'foo')
    yield env


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

    with open(gitnested_path, 'r') as f:
        content = f.read()

    comment_lines = [line for line in content.split('\n') if line.startswith('#')]
    actual = '\n'.join(comment_lines)

    assert actual == expected, f"Comment block mismatch.\nExpected:\n{expected}\nActual:\n{actual}"


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
    with open(gitnested_path, 'r') as f:
        data = yaml.safe_load(f) or {}

    if version is None:
        version = git_nested.VERSION

    def assert_field(nested_data, field, value: str | None):
        if value is None:
            return  # skip
        actual_value = nested_data.get(field, None)
        expected_values = [value]
        if value == '':
            expected_values.append(None)  # can be empty or None
        assert actual_value in expected_values

    assert_gitnested_comment_block(gitnested_path)
    nested_data = data.get('nested', {})
    assert_field(nested_data, 'remote', remote)
    assert_field(nested_data, 'branch', branch)
    assert_field(nested_data, 'commit', commit)
    assert_field(nested_data, 'parent', parent)
    assert_field(nested_data, 'method', method)
    assert_field(nested_data, 'cmdver', version)


def assert_commit(
    cwd,
    ref: str = 'HEAD',
    commit_title: str = None,
    commit_msg: str = None,
    author_name: str = None,
    author_email: str = None,
    committer_name: str = None,
    committer_email: str = None,
    author_date: str = None,
    committer_date: str = None,
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

    def get_commit_info(format_str):
        """Helper to get commit info with a format string"""
        result = subprocess.run(
            ['git', 'log', '-1', f'--format={format_str}', ref], cwd=cwd, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    # Check commit title (subject)
    if commit_title is not None:
        actual_title = get_commit_info('%s')
        assert actual_title == commit_title

    # Check full commit message
    if commit_msg is not None:
        actual_msg = get_commit_info('%B').strip()
        assert actual_msg == commit_msg

    # Check author name
    if author_name is not None:
        actual_author_name = get_commit_info('%an')
        assert actual_author_name == author_name

    # Check author email
    if author_email is not None:
        actual_author_email = get_commit_info('%ae')
        assert actual_author_email == author_email

    # Check committer name
    if committer_name is not None:
        actual_committer_name = get_commit_info('%cn')
        assert actual_committer_name == committer_name

    # Check committer email
    if committer_email is not None:
        actual_committer_email = get_commit_info('%ce')
        assert actual_committer_email == committer_email

    # Check author date
    if author_date is not None:
        actual_author_date = get_commit_info('%ad')
        assert actual_author_date == author_date

    # Check committer date
    if committer_date is not None:
        actual_committer_date = get_commit_info('%cd')
        assert actual_committer_date == committer_date

    # Check changed files
    if changed_files is not None:
        # Get the list of changed files using diff-tree
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
            actual_files_set = set(actual_files)
            assert actual_files_set == changed_files
        else:
            # List comparison (order matters)
            assert actual_files == list(changed_files)


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


def git_get_commit_msg(cwd, args: list[str] = None):
    """Get the commit message for a git commit"""
    args = args or ['--format=%B', '-1']
    result = subprocess.run(['git', 'log'] + args, cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def git_read_head(cwd: Path):
    """Get the commit message for a git commit"""
    return (cwd / '.git' / 'HEAD').read_text().strip()


def git_rev_parse(args: list[str], cwd) -> str:
    """Get the commit SHA for a git ref"""
    result = subprocess.run(['git', 'rev-parse'] + args, cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def git_config(key: str, cwd, file=None):
    """Get a git config value"""
    cmd = ['git', 'config']
    if file:
        cmd.append(f'--file={file}')
    cmd.append(key)

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def cmd_git_nested_subprocess(args, cwd, check: bool = True):
    """Run a git nested command as subprocess and return the result"""
    if isinstance(args, str):
        cmd = f'git nested {args}'
        shell = True
    else:
        cmd = ['git', 'nested'] + args
        shell = False

    result = subprocess.run(cmd, shell=shell, cwd=cwd, capture_output=True, text=True, check=check)
    return result


def cmd_git_nested(args: list[str] | str, cwd, check: bool = True):
    """Run a git nested command and return the result"""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    args = shlex.split(args) if isinstance(args, str) else args

    retval = SimpleNamespace()
    retval.returncode = 0

    with git_nested.chdir(cwd), contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            app = git_nested.GitNestedCommand()
            app.main(args)
        except SystemExit as e:
            retval.returncode = e.code
            if check and e.code:
                raise Exception('Command failed with exit code {e.code}')
        except Exception as e:
            retval.returncode = 1
            if check:
                raise e

    retval.stdout = stdout_buf.getvalue()
    retval.stderr = stderr_buf.getvalue()
    return retval
