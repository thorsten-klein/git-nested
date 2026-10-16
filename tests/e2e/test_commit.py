"""Tests for git nested commit command"""

from conftest import cmd_git_nested, git_rev_parse


def test_commit_missing_fetch_ref_error(env):
    """Test that commit fails with a helpful message when the nested repo was never fetched"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    # init (not clone) never populates refs/nested/<subref>/fetch
    cmd_git_nested('init doc', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    result = cmd_git_nested('commit doc', cwd=init_dir, check=False)
    assert result.returncode == 1
    assert (
        result.output.strip()
        == "git-nested: no ref refs/nested/doc/fetch; run 'git nested fetch doc' first, or pass -F"
    )


def test_commit_fetch_flag_fetches_before_committing(env):
    """Test that `commit --fetch` refreshes the upstream ref before committing"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    cmd_git_nested(f'init doc -r {env.upstream.as_posix()}/bar -b master', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    # --force: the local branch was built from unrelated local history, so it doesn't
    # (and isn't expected to) contain the freshly fetched upstream HEAD as an ancestor.
    result = cmd_git_nested('commit doc --fetch --force', cwd=init_dir)
    assert result.returncode == 0
    assert "doc: committed" in result.output


def test_commit_with_message_file(env):
    """Test that `commit --file` uses the given commit message file"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    cmd_git_nested(f'init doc -r {env.upstream.as_posix()}/bar -b master', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    msg_file = init_dir / 'commit_msg.txt'
    msg_file.write_text('Custom commit message\n')

    result = cmd_git_nested(f'commit doc --fetch --force --file={msg_file}', cwd=init_dir)
    assert result.returncode == 0

    last_msg = env.run(['git', 'log', '-1', '--format=%B'], cwd=init_dir).stdout
    assert last_msg.strip() == 'Custom commit message'


def test_commit_without_changes_makes_no_commit(foo_bar_cloned_and_nested):
    """A nested branch with nothing new on it leaves the history as it is.

    With a local change on the branch it is not upstream as it is, so the
    sync point stays, and so does every other field of .gitnested.
    """
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/local', cwd=foo)
    head = git_rev_parse(['HEAD'], cwd=foo)

    cmd_git_nested('branch bar', cwd=foo)
    result = cmd_git_nested('-v commit bar', cwd=foo)

    assert "nothing to commit for the .gitnested update" in result.output
    assert git_rev_parse(['HEAD'], cwd=foo) == head
