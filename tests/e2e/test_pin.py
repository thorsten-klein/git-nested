"""Tests for --pin: nest a commit or tag of the tracked branch"""

import yaml
from conftest import cmd_git_nested, git_rev_parse


def _nested(foo, field):
    return yaml.safe_load((foo / 'bar' / '.gitnested').read_text())['nested'].get(field)


def test_clone_pin_nests_that_commit(foo_bar_cloned):
    """Tag A is the first commit of bar: Bar, but no bard yet."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'

    cmd_git_nested(['clone', '-b', 'master', '--pin', 'A', (env.upstream / 'bar').as_posix()], foo)

    assert (foo / 'bar' / 'Bar').is_file()
    assert not (foo / 'bar' / 'bard').exists()
    assert _nested(foo, 'pin') == 'A'
    assert _nested(foo, 'branch') == 'master'
    assert _nested(foo, 'commit') == git_rev_parse(['A^{commit}'], cwd=env.upstream / 'bar')


def test_pull_stays_at_the_pin_and_moves_it_on_request(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '-b', 'master', '--pin', 'A', (env.upstream / 'bar').as_posix()], foo)

    assert "already up to date" in cmd_git_nested('pull bar', cwd=foo).output

    tip = git_rev_parse(['master'], cwd=env.upstream / 'bar')
    cmd_git_nested(['pull', '--pin', tip, 'bar'], foo)

    assert (foo / 'bar' / 'bard' / 'Bard').is_file()
    assert _nested(foo, 'pin') == tip


def test_clone_pin_must_be_on_the_branch(foo_bar_cloned):
    env = foo_bar_cloned
    bar = env.workspace / 'bar'
    env.run(['git', 'switch', '-q', '-c', 'side'], cwd=bar)
    env.add_new_files('Side', cwd=bar)
    env.run(['git', 'push', '-q', 'origin', 'side'], cwd=bar)
    side = git_rev_parse(['HEAD'], cwd=bar)

    args = ['clone', '-b', 'master', '--pin', side, (env.upstream / 'bar').as_posix()]
    result = cmd_git_nested(args, env.workspace / 'foo', check=False)

    assert result.returncode == 1
    assert result.output.strip() == f"git-nested: {side} is not on master of {(env.upstream / 'bar').as_posix()}"


def test_pull_conflict_keeps_the_pin(foo_bar_cloned):
    """A pull with --pin that conflicts records the pin once it is finished as printed."""
    env = foo_bar_cloned
    foo, bar = env.workspace / 'foo', env.workspace / 'bar'
    cmd_git_nested(['clone', '-b', 'master', '--pin', 'A', (env.upstream / 'bar').as_posix()], foo)
    env.modify_files('bar/Bar', text='foo', cwd=foo)
    env.modify_files('Bar', text='bar', cwd=bar)
    pin = git_rev_parse(['HEAD'], cwd=bar)
    env.add_new_files('Newer', cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)

    result = cmd_git_nested(['pull', '--pin', pin, 'bar'], foo, check=False)
    assert result.returncode == 1
    worktree = foo / '.git' / 'tmp' / 'nested' / 'bar'
    (worktree / 'Bar').write_text('merged\n')
    env.run(['git', 'add', 'Bar'], cwd=worktree)
    env.run(['git', 'commit', '-q', '--no-edit'], cwd=worktree)
    # the last step the pull printed
    commit_step = result.output.split('7. ')[1].splitlines()[0]
    cmd_git_nested(commit_step.removeprefix('git nested '), foo)

    assert _nested(foo, 'pin') == pin
    assert _nested(foo, 'commit') == pin
    assert "already up to date" in cmd_git_nested('pull bar', cwd=foo).output
