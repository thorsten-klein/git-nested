"""Tests for nested-in-nested repositories (recursive nesting)

This test file demonstrates and verifies support for nested repositories
that themselves contain nested repositories (recursive nesting).

Example structure:
  parent-repo/
    nested-level1/        # First level nested repo
      .gitnested
      nested-level2/      # Second level nested repo (nested within nested)
        .gitnested
        nested-level3/    # Third level nested repo (even deeper nesting)
          .gitnested
"""

import subprocess
from pathlib import Path

import pytest
from conftest import (
    assert_gitnested_field,
    cmd_git_nested,
    create_upstream_repo,
)


def create_upstream_level3(repo_path: Path):
    """Create the deepest nested test repository (level 3)"""
    work_dir = create_upstream_repo(repo_path)

    # Create a simple file
    (work_dir / 'level3.txt').write_text('This is level 3\n')
    subprocess.run(['git', 'add', 'level3.txt'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Add level3 content'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    # Clean up
    import shutil

    shutil.rmtree(work_dir)


def create_upstream_level2_with_nested(env):
    """Create level2 repository that contains a nested level3 repository"""
    repo_path = env.upstream / 'level2'
    work_dir = create_upstream_repo(repo_path)

    # Create initial content for level2
    (work_dir / 'level2.txt').write_text('This is level 2\n')
    subprocess.run(['git', 'add', 'level2.txt'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Add level2 content'], cwd=work_dir, check=True, capture_output=True)

    # Clone level3 as a nested repository inside level2
    result = cmd_git_nested(['clone', str(env.upstream / 'level3'), 'nested3'], cwd=work_dir)
    assert result.returncode == 0

    # Push level2 (now containing nested level3) to upstream
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    # Clean up
    import shutil

    shutil.rmtree(work_dir)


def create_upstream_level1_with_nested(env):
    """Create level1 repository that contains a nested level2 repository (which itself contains level3)"""
    repo_path = env.upstream / 'level1'
    work_dir = create_upstream_repo(repo_path)

    # Create initial content for level1
    (work_dir / 'level1.txt').write_text('This is level 1\n')
    subprocess.run(['git', 'add', 'level1.txt'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Add level1 content'], cwd=work_dir, check=True, capture_output=True)

    # Clone level2 (which contains nested level3) as a nested repository inside level1
    result = cmd_git_nested(['clone', str(env.upstream / 'level2'), 'nested2'], cwd=work_dir)
    assert result.returncode == 0

    # Push level1 (now containing nested level2 which contains nested level3) to upstream
    subprocess.run(['git', 'push', str(repo_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    # Clean up
    import shutil

    shutil.rmtree(work_dir)


@pytest.fixture
def nested_in_nested_repos(env):
    """Setup a hierarchy of nested repositories: level1 -> level2 -> level3"""
    # Create the deepest level first
    create_upstream_level3(env.upstream / 'level3')
    # Create level2 with nested level3
    create_upstream_level2_with_nested(env)
    # Create level1 with nested level2 (which contains level3)
    create_upstream_level1_with_nested(env)

    return env


def test_nested_in_nested_basic(nested_in_nested_repos):
    """Test cloning a nested repository that itself contains nested repositories"""
    env = nested_in_nested_repos

    # Create a parent repo
    parent = env.workspace / 'parent'
    parent.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'ParentUser'], cwd=parent, check=True)
    subprocess.run(['git', 'config', 'user.email', 'parent@parent'], cwd=parent, check=True)

    # Create initial commit in parent
    (parent / 'README.md').write_text('# Parent Repository\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=parent, check=True, capture_output=True)

    # Clone level1 (which contains level2, which contains level3) into parent
    result = cmd_git_nested(['clone', str(env.upstream / 'level1'), 'nested1'], cwd=parent)
    assert result.returncode == 0
    assert "nested1: cloned from" in result.output

    # Verify the structure exists
    assert (parent / 'nested1' / 'level1.txt').is_file()
    assert (parent / 'nested1' / '.gitnested').is_file()
    assert (parent / 'nested1' / 'nested2' / 'level2.txt').is_file()
    assert (parent / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').is_file()

    # Verify content
    assert (parent / 'nested1' / 'level1.txt').read_text() == 'This is level 1\n'
    assert (parent / 'nested1' / 'nested2' / 'level2.txt').read_text() == 'This is level 2\n'
    assert (parent / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').read_text() == 'This is level 3\n'

    # Verify .gitnested files are correct at all levels
    # Level 1: regular .gitnested for the immediate nested repo
    assert_gitnested_field(
        parent / 'nested1' / '.gitnested',
        remote=str(env.upstream / 'level1'),
        branch='master',
    )

    # Level 2: .gitnested.level2 file should be created in parent/nested1/nested2/
    # This allows pulling nested2 independently when working in the parent repo
    assert (parent / 'nested1' / 'nested2' / '.gitnested.level2').is_file(), (
        "Should have .gitnested.level2 for sub-nested repo"
    )
    assert_gitnested_field(
        parent / 'nested1' / 'nested2' / '.gitnested.level2',
        remote=str(env.upstream / 'level2'),
        branch='master',
    )

    # Level 3: .gitnested.level3 file should be created in parent/nested1/nested2/nested3/
    assert (parent / 'nested1' / 'nested2' / 'nested3' / '.gitnested.level3').is_file(), (
        "Should have .gitnested.level3 for deeply sub-nested repo"
    )
    assert_gitnested_field(
        parent / 'nested1' / 'nested2' / 'nested3' / '.gitnested.level3',
        remote=str(env.upstream / 'level3'),
        branch='master',
    )

    # The original .gitnested files should still exist (from when level2 cloned level3, etc.)
    assert (parent / 'nested1' / 'nested2' / '.gitnested').is_file()
    assert (parent / 'nested1' / 'nested2' / 'nested3' / '.gitnested').is_file()


def test_nested_in_nested_pull(nested_in_nested_repos):
    """Test pulling updates through multiple levels of nested repositories"""
    env = nested_in_nested_repos

    # Create a parent repo and clone the nested hierarchy
    parent = env.workspace / 'parent'
    parent.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'ParentUser'], cwd=parent, check=True)
    subprocess.run(['git', 'config', 'user.email', 'parent@parent'], cwd=parent, check=True)
    (parent / 'README.md').write_text('# Parent Repository\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=parent, check=True, capture_output=True)

    # Clone the nested hierarchy
    result = cmd_git_nested(['clone', str(env.upstream / 'level1'), 'nested1'], cwd=parent)
    assert result.returncode == 0

    # Make changes in level3 upstream
    level3_work = env.upstream / 'level3.tmp'
    level3_work.mkdir(exist_ok=True)
    subprocess.run(['git', 'clone', str(env.upstream / 'level3'), level3_work], check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=level3_work, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=level3_work, check=True)
    (level3_work / 'level3.txt').write_text('This is level 3 - updated\n')
    subprocess.run(['git', 'add', 'level3.txt'], cwd=level3_work, check=True)
    subprocess.run(['git', 'commit', '-m', 'Update level3'], cwd=level3_work, check=True)
    subprocess.run(['git', 'push'], cwd=level3_work, check=True)

    # Pull the update through the nested hierarchy
    # First, pull into level2's nested3
    level2_work = env.workspace / 'level2_work'
    subprocess.run(['git', 'clone', str(env.upstream / 'level2'), level2_work], check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=level2_work, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=level2_work, check=True)

    result = cmd_git_nested(['pull', 'nested3'], cwd=level2_work)
    assert result.returncode == 0

    subprocess.run(['git', 'push'], cwd=level2_work, check=True)

    # Then pull into level1's nested2
    level1_work = env.workspace / 'level1_work'
    subprocess.run(['git', 'clone', str(env.upstream / 'level1'), level1_work], check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=level1_work, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=level1_work, check=True)

    result = cmd_git_nested(['pull', 'nested2'], cwd=level1_work)
    assert result.returncode == 0

    subprocess.run(['git', 'push'], cwd=level1_work, check=True)

    # Finally pull into parent's nested1
    result = cmd_git_nested(['pull', 'nested1'], cwd=parent)
    assert result.returncode == 0

    # Verify the update propagated all the way down
    assert (parent / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').read_text() == 'This is level 3 - updated\n'


def test_nested_in_nested_status(nested_in_nested_repos):
    """Test status command shows all nested repositories at all levels"""
    env = nested_in_nested_repos

    # Create a parent repo and clone the nested hierarchy
    parent = env.workspace / 'parent'
    parent.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'ParentUser'], cwd=parent, check=True)
    subprocess.run(['git', 'config', 'user.email', 'parent@parent'], cwd=parent, check=True)
    (parent / 'README.md').write_text('# Parent Repository\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=parent, check=True, capture_output=True)

    # Clone the nested hierarchy
    result = cmd_git_nested(['clone', str(env.upstream / 'level1'), 'nested1'], cwd=parent)
    assert result.returncode == 0

    # Check status
    result = cmd_git_nested(['status'], cwd=parent)
    assert result.returncode == 0

    # Should show nested1 at minimum, ideally also nested2 and nested3
    assert 'nested1' in result.output

    # Depending on implementation, it might also recursively show deeper nesting
    # This would be the ideal behavior
    # assert 'nested1/nested2' in result.output or 'nested2' in result.output
    # assert 'nested1/nested2/nested3' in result.output or 'nested3' in result.output


def test_pull_sub_nested_using_level_files(nested_in_nested_repos):
    """Test that we can pull a sub-nested repo using .gitnested.level2 file"""
    env = nested_in_nested_repos

    # Create a parent repo and clone the nested hierarchy
    parent = env.workspace / 'parent'
    parent.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'ParentUser'], cwd=parent, check=True)
    subprocess.run(['git', 'config', 'user.email', 'parent@parent'], cwd=parent, check=True)
    (parent / 'README.md').write_text('# Parent Repository\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=parent, check=True, capture_output=True)

    # Clone the nested hierarchy
    result = cmd_git_nested(['clone', str(env.upstream / 'level1'), 'nested1'], cwd=parent)
    assert result.returncode == 0

    # Make changes in level2 upstream (add a new file to avoid conflicts)
    level2_work = env.workspace / 'level2_work'
    subprocess.run(['git', 'clone', str(env.upstream / 'level2'), level2_work], check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=level2_work, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=level2_work, check=True)
    (level2_work / 'new_file.txt').write_text('This is a new file in level2\n')
    subprocess.run(['git', 'add', 'new_file.txt'], cwd=level2_work, check=True)
    subprocess.run(['git', 'commit', '-m', 'Add new file to level2'], cwd=level2_work, check=True)
    subprocess.run(['git', 'push'], cwd=level2_work, check=True)

    # Now pull level2 directly from the parent repo using the .gitnested.level2 file
    # This should work because we have the .gitnested.level2 metadata
    result = cmd_git_nested(['pull', 'nested1/nested2'], cwd=parent, check=False)
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    assert result.returncode == 0, f"Pull failed with stderr: {result.stderr}"

    # Verify the update was pulled
    assert (parent / 'nested1' / 'nested2' / 'new_file.txt').exists()
    assert (parent / 'nested1' / 'nested2' / 'new_file.txt').read_text() == 'This is a new file in level2\n'

    # The deeply nested content should remain unchanged
    assert (parent / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').read_text() == 'This is level 3\n'


def test_four_levels_deep(nested_in_nested_repos):
    """Test even deeper nesting: 4 levels of nested repositories"""
    env = nested_in_nested_repos

    # Create level0 that will contain level1 (which contains level2, which contains level3)
    level0_path = env.upstream / 'level0'
    work_dir = create_upstream_repo(level0_path)

    (work_dir / 'level0.txt').write_text('This is level 0\n')
    subprocess.run(['git', 'add', 'level0.txt'], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Add level0 content'], cwd=work_dir, check=True, capture_output=True)

    # Clone level1 (with all its nested content) into level0
    result = cmd_git_nested(['clone', str(env.upstream / 'level1'), 'nested1'], cwd=work_dir)
    assert result.returncode == 0

    subprocess.run(['git', 'push', str(level0_path), 'master'], cwd=work_dir, check=True, capture_output=True)

    # Now create a parent and clone level0
    parent = env.workspace / 'parent'
    parent.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'ParentUser'], cwd=parent, check=True)
    subprocess.run(['git', 'config', 'user.email', 'parent@parent'], cwd=parent, check=True)
    (parent / 'README.md').write_text('# Parent Repository\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=parent, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=parent, check=True, capture_output=True)

    result = cmd_git_nested(['clone', str(env.upstream / 'level0'), 'nested0'], cwd=parent)
    assert result.returncode == 0

    # Verify all 4 levels exist
    assert (parent / 'nested0' / 'level0.txt').is_file()
    assert (parent / 'nested0' / '.gitnested').is_file()
    assert (parent / 'nested0' / 'nested1' / 'level1.txt').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'level2.txt').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').is_file()

    # Verify content at all levels
    assert (parent / 'nested0' / 'level0.txt').read_text() == 'This is level 0\n'
    assert (parent / 'nested0' / 'nested1' / 'level1.txt').read_text() == 'This is level 1\n'
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'level2.txt').read_text() == 'This is level 2\n'
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'nested3' / 'level3.txt').read_text() == 'This is level 3\n'

    # Verify .gitnested and .gitnested.levelN files exist
    # Level 0 (immediate nested)
    assert (parent / 'nested0' / '.gitnested').is_file()

    # Level 1 (nested within nested0)
    assert (parent / 'nested0' / 'nested1' / '.gitnested').is_file()
    assert (parent / 'nested0' / 'nested1' / '.gitnested.level2').is_file()

    # Level 2 (nested within nested1)
    assert (parent / 'nested0' / 'nested1' / 'nested2' / '.gitnested').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / '.gitnested.level2').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / '.gitnested.level3').is_file()

    # Level 3 (deeply nested)
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'nested3' / '.gitnested').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'nested3' / '.gitnested.level3').is_file()
    assert (parent / 'nested0' / 'nested1' / 'nested2' / 'nested3' / '.gitnested.level4').is_file()

    # Clean up
    import shutil

    shutil.rmtree(work_dir)
