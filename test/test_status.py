"""Tests for git nested status command"""

from conftest import cmd_git_nested, git_rev_parse

import textwrap


def test_status(foo_bar_cloned):
    """Test nested status command with nested nesteds"""
    env = foo_bar_cloned

    # Clone multiple nesteds, including nested ones
    cmd_git_nested(f'clone {env.upstream}/bar', cwd=env.workspace / 'foo')
    cmd_git_nested(f'clone {env.upstream}/foo bar/foo', cwd=env.workspace / 'foo')
    (env.workspace / 'foo' / 'lib').mkdir()
    cmd_git_nested(f'clone {env.upstream}/bar lib/bar', cwd=env.workspace / 'foo')
    cmd_git_nested(f'clone {env.upstream}/foo lib/bar/foo', cwd=env.workspace / 'foo')

    bar_upstream = git_rev_parse(['--short', 'HEAD'], env.upstream / 'bar')
    foo_upstream = git_rev_parse(['--short', 'HEAD'], env.upstream / 'foo')
    pull_parent1 = git_rev_parse(['--short', 'HEAD~1'], env.workspace / 'foo')
    pull_parent2 = git_rev_parse(['--short', 'HEAD~2'], env.workspace / 'foo')
    pull_parent3 = git_rev_parse(['--short', 'HEAD~3'], env.workspace / 'foo')

    # Test status --all (non-recursive)
    result = cmd_git_nested('status --all', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == textwrap.dedent(f"""\
        2 nested repositories:
        Git nested repository 'bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {foo_upstream}

        Git nested repository 'lib/bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {pull_parent2}""")

    # Test status --ALL (recursive)
    result = cmd_git_nested('status --ALL', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == textwrap.dedent(f"""\
        4 nested repositories:
        Git nested repository 'bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {foo_upstream}

        Git nested repository 'bar/foo':
          Remote URL:      {env.upstream}/foo
          Upstream Ref:    {foo_upstream}
          Tracking Branch: master
          Pulled Commit:   {foo_upstream}
          Pull Parent:     {pull_parent3}

        Git nested repository 'lib/bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {pull_parent2}
          
        Git nested repository 'lib/bar/foo':
          Remote URL:      {env.upstream}/foo
          Upstream Ref:    {foo_upstream}
          Tracking Branch: master
          Pulled Commit:   {foo_upstream}
          Pull Parent:     {pull_parent1}""")

    # Test status --all again (should be same as first test)
    result = cmd_git_nested('status --all', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == textwrap.dedent(f"""\
        2 nested repositories:
        Git nested repository 'bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {foo_upstream}

        Git nested repository 'lib/bar':
          Remote URL:      {env.upstream}/bar
          Upstream Ref:    {bar_upstream}
          Tracking Branch: master
          Pulled Commit:   {bar_upstream}
          Pull Parent:     {pull_parent2}""")


def test_status_quiet(foo_bar_cloned):
    """Test nested status with --quiet flag"""
    env = foo_bar_cloned

    # Clone a nested
    cmd_git_nested(f'clone {env.upstream}/bar', cwd=env.workspace / 'foo')

    # Test status with --quiet flag (should still show output since status prints output)
    result = cmd_git_nested('--quiet status', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == ""
