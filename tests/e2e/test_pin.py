"""Tests for --pin: nest a commit or tag of the tracked branch"""

import pytest
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


def _upstream_commit(env, text):
    """Upstream adds a commit that changes bard/Bard."""
    bar = env.workspace / 'bar'
    env.modify_files('bard/Bard', text=text, cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    return git_rev_parse(['HEAD'], cwd=bar)


@pytest.mark.parametrize('method', ['merge', 'rebase'])
def test_pull_pin_goes_back_and_forth_with_local_changes(foo_bar_cloned_and_nested, method):
    """A pin to an older commit goes back to it. The local changes stay, also on the way forward again."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    first = git_rev_parse(['master'], cwd=env.upstream / 'bar')
    env.modify_files('bar/Bar', text='local', cwd=foo)
    second = _upstream_commit(env, 'second')
    cmd_git_nested(['pull', f'--{method}', 'bar'], foo)

    cmd_git_nested(['pull', f'--{method}', '--pin', first, 'bar'], foo)

    assert 'second' not in (foo / 'bar' / 'bard' / 'Bard').read_text()
    assert 'local' in (foo / 'bar' / 'Bar').read_text()
    assert _nested(foo, 'commit') == first

    env.modify_files('bar/Bar', text='more', cwd=foo)
    third = _upstream_commit(env, 'third')
    cmd_git_nested(['pull', f'--{method}', '--pin', third, 'bar'], foo)

    bard = (foo / 'bar' / 'bard' / 'Bard').read_text()
    assert 'second' in bard
    assert 'third' in bard
    assert 'local' in (foo / 'bar' / 'Bar').read_text()
    assert 'more' in (foo / 'bar' / 'Bar').read_text()
    assert _nested(foo, 'commit') == third != second


@pytest.mark.parametrize('method', ['merge', 'rebase'])
def test_pull_pin_goes_back_to_before_a_file_existed(foo_bar_cloned_and_nested, method):
    """Tag A has no bard yet, so going back removes it."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.modify_files('bar/Bar', text='local', cwd=foo)

    cmd_git_nested(['pull', f'--{method}', '--pin', 'A', 'bar'], foo)

    assert not (foo / 'bar' / 'bard').exists()
    assert 'local' in (foo / 'bar' / 'Bar').read_text()


def test_pull_without_a_pin_does_not_go_back(foo_bar_cloned_and_nested):
    """An upstream branch reset to an older commit is still refused with merge."""
    env = foo_bar_cloned_and_nested
    foo, bar = env.workspace / 'foo', env.workspace / 'bar'
    _upstream_commit(env, 'second')
    cmd_git_nested('pull bar', cwd=foo)
    env.run(['git', 'reset', '-q', '--hard', 'HEAD~1'], cwd=bar)
    env.run(['git', 'push', '-q', '--force'], cwd=bar)

    result = cmd_git_nested('pull bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert "upstream history was rewritten" in result.output
