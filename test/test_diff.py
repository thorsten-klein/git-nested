"""Tests for git nested diff command"""

from conftest import (
    assert_output_like,
    assert_output_unlike,
    clone_repo,
    cmd_git_nested,
    create_upstream_repo,
)


def test_diff_no_differences(foo_bar_cloned_and_nested):
    """Test that diff reports no differences right after a clone"""
    env = foo_bar_cloned_and_nested

    result = cmd_git_nested('diff bar', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == f"No differences between 'bar' and upstream '{env.upstream}/bar' (master)."


def test_diff_shows_upstream_changes(foo_bar_cloned_and_nested):
    """Test that diff shows changes that are upstream but not yet pulled locally"""
    env = foo_bar_cloned_and_nested

    # Add a new file upstream and push, without pulling into foo
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    result = cmd_git_nested('diff bar', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert_output_like(result.stdout, r'diff --git a/Bar2 b/Bar2')
    assert_output_like(result.stdout, r'new file mode')
    assert_output_like(result.stdout, r'\+new file Bar2')

    # The .gitnested file must never show up in the diff
    assert_output_unlike(result.stdout, r'\.gitnested')


def test_diff_shows_local_only_changes(foo_bar_cloned_and_nested):
    """Test that diff shows local changes that haven't been pushed upstream yet"""
    env = foo_bar_cloned_and_nested

    # Modify the nested file directly within the outer (foo) repository and commit it there,
    # without ever pushing this change back upstream.
    env.modify_files('bar/Bar', text='a local only line', cwd=env.workspace / 'foo')

    result = cmd_git_nested('diff bar', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert_output_like(result.stdout, r'diff --git a/Bar b/Bar')
    assert_output_like(result.stdout, r'-a local only line')


def test_diff_respects_filter(foo_bar_cloned):
    """Test that diff only considers the paths matched by the nested repo's filter"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file1', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested(f'clone {env.upstream}/leg leg --filter=subdirA', cwd=env.workspace / 'foo')

    # Modify a file in both the filtered-in (subdirA) and filtered-out (subdirB) directories
    env.modify_files('subdirA/file1', text='a1 modified', cwd=env.workspace / 'leg')
    env.modify_files('subdirB/file1', text='b1 modified', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    result = cmd_git_nested('diff leg', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert_output_like(result.stdout, r'diff --git a/subdirA/file1 b/subdirA/file1')
    assert_output_unlike(result.stdout, r'subdirB')


def test_diff_no_remote(env):
    """Test diff command when nested has no remote"""
    env.clone_init()

    cmd_git_nested('init doc', cwd=env.workspace / 'init')

    result = cmd_git_nested('diff doc', cwd=env.workspace / 'init')
    assert result.stdout.strip() == "Ignored 'doc', no remote."
    assert result.stderr.strip() == ''


def test_diff_requires_clean_worktree(foo_bar_cloned_and_nested):
    """Test that diff refuses to run while there are uncommitted changes in the outer repo"""
    env = foo_bar_cloned_and_nested

    (env.workspace / 'foo' / 'untracked_file').write_text('uncommitted\n')
    env.run(['git', 'add', 'untracked_file'], cwd=env.workspace / 'foo')

    result = cmd_git_nested('diff bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert (
        result.stderr.strip()
        == f"git-nested: Can't diff nested repository. Working tree has changes. ({env.workspace}/foo)"
    )


def test_diff_all(foo_bar_cloned):
    """Test that diff --all runs diff for every nested repo"""
    env = foo_bar_cloned

    env.run(['git', 'nested', 'clone', '../bar', 'bar1'], cwd=env.workspace / 'foo')
    env.run(['git', 'nested', 'clone', '../bar', 'bar2'], cwd=env.workspace / 'foo')

    # Push a new upstream commit, then only bring 'bar1' up to date so 'bar2' lags behind
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    cmd_git_nested('pull bar1', cwd=env.workspace / 'foo')

    result = cmd_git_nested('diff --all', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert_output_like(result.stdout, r"No differences between 'bar1' and upstream '.*' \(master\)\.")
    assert_output_like(result.stdout, r'diff --git a/Bar2 b/Bar2')


def test_diff_with_filter_removed_upstream_file(foo_bar_cloned):
    """Diffing must not choke when a filtered-in file is removed upstream"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/file2', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested(f'clone {env.upstream}/leg leg --filter=subdirA', cwd=env.workspace / 'foo')

    env.remove_files('subdirA/file2', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    result = cmd_git_nested('diff leg', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert_output_like(result.stdout, r'deleted file mode')
    assert_output_like(result.stdout, r'diff --git a/subdirA/file2 b/subdirA/file2')


def test_diff_ignores_gitnested_level_files(foo_bar_cloned):
    """A nested-in-nested repository's .gitnested.levelN file must not show up in the diff"""
    env = foo_bar_cloned

    # Nest 'foo' inside 'bar' upstream, before 'bar' is ever cloned locally. This means the
    # single clone of 'bar' below will already need to create a bar/foo/.gitnested.level2 file.
    cmd_git_nested(f'clone {env.upstream}/foo nestedfoo', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    cmd_git_nested(f'clone {env.upstream}/bar', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'bar' / 'nestedfoo' / '.gitnested.level2').is_file()

    result = cmd_git_nested('diff bar', cwd=env.workspace / 'foo')
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == f"No differences between 'bar' and upstream '{env.upstream}/bar' (master)."
