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
