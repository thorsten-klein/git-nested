"""Tests extraction of a nested repository"""

import textwrap
import yaml

from conftest import assert_commit_count, clone_repo, cmd_git_nested, create_upstream_repo, tree


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

    cmd_git_nested('pull leg --force', cwd=env.workspace / 'foo')
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
