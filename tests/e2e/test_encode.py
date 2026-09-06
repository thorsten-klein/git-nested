"""Tests for git nested with special characters in directory names"""

import pytest
from conftest import cmd_git_nested


@pytest.mark.parametrize(
    'dirname, expected_dirname, sanitized_ref',
    [
        ('normal', 'normal', 'normal'),
        ('.dot', '.dot', '_dot'),
        ('.......dots', '.......dots', '___.dots'),
        ('spa ce', 'spa ce', 'spa%20ce'),
        ('per%cent', 'per%cent', 'per%cent'),
        ('back-sl\\as/h', 'back-sl\\as/h', 'back-sl%5Cas_h'),
        ('end-with.lock', 'end-with.lock', 'end-with_lock'),
        ('@{', '@{', '%40%7B'),
        ('[', '[', '%5B'),
        ('-begin-with-minus', '-begin-with-minus', '-begin-with-minus'),
        ('trailing-slash/', 'trailing-slash', 'trailing-slash'),
        ('trailing-dots...', 'trailing-dots...', 'trailing-dots_'),
        ('special-char:^[?*', 'special-char:^[?*', 'special-char%3A%5E%5B%3F%2A'),
        ('many////slashes', 'many/slashes', 'many/slashes'),
        ('_under_scores_', '_under_scores_', '_under_scores_'),
        ('.str%a\\nge...', '.str%a\\nge...', '_str%25a%5Cnge_'),
        (
            '~////......s:a^t?r a*n[g@{e.lock',
            '~/......s:a^t?r a*n[g@{e.lock',
            '_____s%3Aa%5Et%3Fr%20a%2An%5Bg%40%7Be_lock',
        ),
    ],
)
def test_encode(foo_bar_cloned, dirname, expected_dirname, sanitized_ref):
    """Test nested operations with special characters in directory names"""
    env = foo_bar_cloned

    # Clone with original dirname, expect it to be normalized
    assert not (env.workspace / 'foo' / dirname).exists()
    result = cmd_git_nested(['clone', str(env.upstream / 'bar'), '--', dirname], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository '{env.upstream}/bar' (master) cloned into '{expected_dirname}'."
    assert result.stderr.strip() == ""
    assert (env.workspace / 'foo' / dirname).exists()

    # Add new file to bar and push
    assert not (env.workspace / 'bar' / 'Bar2').exists()
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Pull using original name
    assert not (env.workspace / 'foo' / dirname / 'Bar2').exists()
    result = cmd_git_nested(['pull', '--', dirname], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository '{expected_dirname}' pulled from '{env.upstream}/bar' (master)."
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Create a branch
    result = cmd_git_nested(['branch', '--force', '--', dirname], cwd=env.workspace / 'foo')
    assert (
        result.stdout.strip()
        == f"Created branch 'nested/{sanitized_ref}' and worktree '.git/tmp/nested/{sanitized_ref}'."
    )
