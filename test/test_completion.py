"""Tests for shell completion functionality"""

import textwrap
import pytest


def skip_if_missing(env, cmd):
    result = env.run(['which', cmd], check=False)
    if result.returncode != 0:
        pytest.skip("bash is not installed")


def test_bash_rc_sources_without_error(env):
    """Test that .rc sources successfully in bash"""
    skip_if_missing(env, "bash")

    # Test that sourcing .rc doesn't produce errors
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.rc
        echo "SUCCESS"
        """)

    result = env.run(['bash', '-c', script], check=False)
    assert result.returncode == 0
    assert "SUCCESS" in result.stdout


def test_bash_completion_file_exists(env):
    """Test that bash completion file is readable"""
    skip_if_missing(env, "bash")

    # Test that the completion file is readable
    script = textwrap.dedent(f"""\
        if [[ -r {env.test_dir}/share/completion.bash ]]; then
            echo "COMPLETION_FILE_EXISTS"
        fi
        """)

    result = env.run(['bash', '-c', script], check=False)
    assert "COMPLETION_FILE_EXISTS" in result.stdout


def test_zsh_rc_sources_without_error(env):
    """Test that .rc sources successfully in zsh"""
    skip_if_missing(env, "zsh")

    # Test that sourcing .rc doesn't produce critical errors
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.rc
        echo "SUCCESS"
        """)

    result = env.run(['zsh', '-c', script], check=False)
    assert result.returncode == 0
    assert "SUCCESS" in result.stdout


def test_zsh_completion_function_loaded(env):
    """Test that zsh completion function is loaded after sourcing .rc"""
    skip_if_missing(env, "zsh")

    # Test that sourcing .rc loads the completion function
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.rc
        # Check if _git-nested function is loaded
        if (( $+functions[_git-nested] )); then
            echo "FUNCTION_LOADED"
        fi
        """)

    result = env.run(['zsh', '-c', script], check=False)
    assert result.returncode == 0
    assert "FUNCTION_LOADED" in result.stdout


def test_zsh_completion_with_compinit(env):
    """Test that zsh completion is registered when compinit is loaded"""
    skip_if_missing(env, "zsh")

    # Test with a full zsh completion environment
    script = textwrap.dedent(f"""\
        autoload -Uz compinit
        compinit
        source {env.test_dir}/.rc
        # Check if completion is registered for git-nested command
        if [[ -n ${{_comps[git-nested]}} ]]; then
            echo "COMPLETION_REGISTERED"
        fi
        """)

    result = env.run(['zsh', '-c', script], check=False)
    assert result.returncode == 0
    assert "COMPLETION_REGISTERED" in result.stdout


def test_fish_rc_sources_without_error(env):
    """Test that .fish.rc sources successfully in fish"""
    skip_if_missing(env, "fish")

    # Test that sourcing .fish.rc doesn't produce critical errors
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.fish.rc
        echo "SUCCESS"
        """)

    result = env.run(['fish', '-c', script], check=False)
    assert result.returncode == 0
    assert "SUCCESS" in result.stdout


def test_fish_completion_function_loaded(env):
    """Test that fish completion function is loaded after sourcing .fish.rc"""
    skip_if_missing(env, "fish")

    # Test that sourcing .fish.rc loads the completion function
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.fish.rc
        # Check if completion function is defined
        if functions -q __fish_git_nested_subdirs
            echo "FUNCTION_LOADED"
        end
        """)

    result = env.run(['fish', '-c', script], check=False)
    assert result.returncode == 0
    assert "FUNCTION_LOADED" in result.stdout


def test_fish_completion_commands(env):
    """Test that fish completion suggests commands"""
    skip_if_missing(env, "fish")

    # Test that completion suggests valid subcommands
    script = textwrap.dedent(f"""\
        source {env.test_dir}/.fish.rc
        # Use complete -C to test what completions would be offered
        complete -C 'git-nested '
        """)

    result = env.run(['fish', '-c', script], check=False)
    assert result.returncode == 0
    for cmd in ['clone', 'push', 'pull', 'status']:
        assert cmd in result.stdout
