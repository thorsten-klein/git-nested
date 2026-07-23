"""Tests extraction of a nested repository"""

import textwrap

import pytest
import yaml

from conftest import assert_commit_count, clone_repo, cmd_git_nested, create_upstream_repo, tree
from git_nested import GitNestedError


def test_consumer_with_filter(foo_bar_cloned):
    """Test basic nested push functionality"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/otherfile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # count commits
    assert_commit_count(env.workspace / 'foo', 1)
    assert_commit_count(env.workspace / 'leg', 6)

    # add nested repository leg
    cmd_git_nested(f'clone {env.upstream}/leg leg --filter=subdirA --filter=subdirC', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()

    # add nested repository leg
    env.add_new_files('leg/subdirA/somefile', cwd=env.workspace / 'foo')
    cmd_git_nested('push leg --branch master', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()

    # add nested repository leg
    env.run(['git', 'pull'], cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/file3', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()


def test_pull_conflicts_on_change_to_filtered_out_file(foo_bar_cloned):
    """Reproduces bug: pulling upstream changes to a file excluded by --filter
    causes a merge conflict, even though the file was never present locally.
    """
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/somefile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # clone leg with a filter that excludes subdirB entirely
    cmd_git_nested(f'clone {env.upstream}/leg leg --filter=subdirA', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()

    # upstream modifies a file inside the *excluded* subdirB - the local clone
    # never had this file, so this change should not conflict with anything
    env.modify_files('subdirB/somefile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # pulling should succeed cleanly since subdirB is filtered out locally
    result = cmd_git_nested('pull leg', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 0, (
        f"Expected pull of a change to a filtered-out file to succeed without conflicts, "
        f"but it failed:\n{result.stdout}\n{result.stderr}"
    )
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()


def test_filter_pull(foo_bar_cloned):
    """Test that a filter added to .gitnested is applied on the next pull"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/otherfile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # count commits
    assert_commit_count(env.workspace / 'foo', 1)
    assert_commit_count(env.workspace / 'leg', 6)

    # clone leg without filters — all subdirs should be present
    cmd_git_nested(f'clone {env.upstream}/leg leg', cwd=env.workspace / 'foo')
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── subdirA
        │   ├── otherfile
        │   └── somefile
        ├── subdirB
        │   ├── otherfile
        │   └── somefile
        ├── subdirC
        │   ├── otherfile
        │   └── somefile
        └── .gitnested""")

    # add filters to .gitnested so that only subdirA and subdirC are included on pull
    gitnested_path = env.workspace / 'foo' / 'leg' / '.gitnested'
    data = yaml.safe_load(gitnested_path.read_text())
    data['nested']['filter'] = ['subdirA', 'subdirC', 'rootfile']
    with gitnested_path.open('w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    env.run(['git', 'add', 'leg/.gitnested'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'add filter to leg/.gitnested'], cwd=env.workspace / 'foo')

    # add a new upstream commit so that pull is triggered
    env.add_new_files('subdirA/file3', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── subdirA
        │   ├── file3
        │   ├── otherfile
        │   └── somefile
        ├── subdirC
        │   ├── otherfile
        │   └── somefile
        └── .gitnested""")

    # add a new upstream commit so that pull is triggered
    env.add_new_files('rootfile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── subdirA
        │   ├── file3
        │   ├── otherfile
        │   └── somefile
        ├── subdirC
        │   ├── otherfile
        │   └── somefile
        ├── .gitnested
        └── rootfile""")

    data['nested']['filter'] = ['subdirA', 'rootfile']
    with gitnested_path.open('w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    env.run(['git', 'add', 'leg/.gitnested'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'modify filter in leg/.gitnested'], cwd=env.workspace / 'foo')

    # pull removes files when filters have changed
    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── subdirA
        │   ├── file3
        │   ├── otherfile
        │   └── somefile
        ├── .gitnested
        └── rootfile""")


def test_filter_regex(foo_bar_cloned):
    """Test that filter patterns are interpreted as regex when they don't match a literal path"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/file2', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file2', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/file2', cwd=env.workspace / 'leg')
    env.add_new_files('docs/readme.md', cwd=env.workspace / 'leg')
    env.add_new_files('docs/notes.txt', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # clone with regex filters:
    #   - subdir[AC]/.* selects everything under subdirA and subdirC
    #   - docs/.*\.md selects only markdown files under docs
    cmd_git_nested(
        ['clone', f'{env.upstream}/leg', 'leg', '--filter=subdir[AC]/.*', '--filter=docs/.*\\.md'],
        cwd=env.workspace / 'foo',
    )
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── docs
        │   └── readme.md
        ├── subdirA
        │   ├── file1
        │   └── file2
        ├── subdirC
        │   ├── file1
        │   └── file2
        └── .gitnested""")

    # change the regex filter in .gitnested so that only docs/*\.md and the
    # subdirA contents are kept, and verify the next pull applies it
    gitnested_path = env.workspace / 'foo' / 'leg' / '.gitnested'
    data = yaml.safe_load(gitnested_path.read_text())
    data['nested']['filter'] = ['docs/.*\\.md', 'subdirA/.*']
    with gitnested_path.open('w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    env.run(['git', 'add', 'leg/.gitnested'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'narrow regex filter in leg/.gitnested'], cwd=env.workspace / 'foo')

    # add a new upstream commit so that pull is triggered
    env.add_new_files('subdirA/file3', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── docs
        │   └── readme.md
        ├── subdirA
        │   ├── file1
        │   ├── file2
        │   └── file3
        └── .gitnested""")


def test_filter_invalid_regex(foo_bar_cloned):
    """Invalid regex in --filter must raise GitNestedError with a clear message"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # '[unclosed' is neither a tree, a blob, nor a valid regex
    with pytest.raises(GitNestedError, match=r"Invalid filter pattern '\[unclosed'"):
        cmd_git_nested(
            ['clone', f'{env.upstream}/leg', 'leg', '--filter=[unclosed'],
            cwd=env.workspace / 'foo',
        )


def test_filter_regex_overlaps_literal(foo_bar_cloned):
    """A regex filter that also matches files already added by a literal filter must skip them"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/file2', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file2', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/file2', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # Literal 'subdirA' pulls in subdirA/file1 and subdirA/file2 via read-tree.
    # The regex 'subdir.*/file1' also matches subdirA/file1 (already present →
    # exercises the file_path.exists() skip branch) and adds subdirB/file1 and
    # subdirC/file1.
    cmd_git_nested(
        ['clone', f'{env.upstream}/leg', 'leg', '--filter=subdirA', '--filter=subdir.*/file1'],
        cwd=env.workspace / 'foo',
    )
    assert tree(env.workspace / 'foo' / 'leg') == textwrap.dedent("""\
        ├── subdirA
        │   ├── file1
        │   └── file2
        ├── subdirB
        │   └── file1
        ├── subdirC
        │   └── file1
        └── .gitnested""")
