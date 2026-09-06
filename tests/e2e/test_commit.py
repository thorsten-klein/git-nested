"""Tests for git nested commit command"""

from conftest import cmd_git_nested


def test_commit_missing_fetch_ref_error(env):
    """Test that commit fails with a helpful message when the nested repo was never fetched"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    # init (not clone) never populates refs/nested/<subref>/fetch
    cmd_git_nested('init doc', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    result = cmd_git_nested('commit doc', cwd=init_dir, check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: Can't find ref 'refs/nested/doc/fetch'. Try using -F."


def test_commit_fetch_flag_fetches_before_committing(env):
    """Test that `commit --fetch` refreshes the upstream ref before committing"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    cmd_git_nested(f'init doc -r {env.upstream}/bar -b master', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    # --force: the local branch was built from unrelated local history, so it doesn't
    # (and isn't expected to) contain the freshly fetched upstream HEAD as an ancestor.
    result = cmd_git_nested('commit doc --fetch --force', cwd=init_dir)
    assert result.returncode == 0
    assert "committed as subdir 'doc/'" in result.output


def test_commit_with_message_file(env):
    """Test that `commit --file` uses the given commit message file"""
    env.clone_init()
    init_dir = env.workspace / 'init'

    cmd_git_nested(f'init doc -r {env.upstream}/bar -b master', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)

    msg_file = init_dir / 'commit_msg.txt'
    msg_file.write_text('Custom commit message\n')

    result = cmd_git_nested(f'commit doc --fetch --force --file={msg_file}', cwd=init_dir)
    assert result.returncode == 0

    last_msg = env.run(['git', 'log', '-1', '--format=%B'], cwd=init_dir).stdout
    assert last_msg.strip() == 'Custom commit message'
