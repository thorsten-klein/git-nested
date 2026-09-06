"""Tests for shell completion.

There are no completion scripts in the repository any more: git-nested
prints them itself, from the same tables its parser is built from. So these
tests cover three things -- that what it prints is valid in each shell, that
the documented wiring registers it, and that the candidates it computes for
a `<TAB>` are the ones the parser would accept.
"""

import shutil

import pytest

SHELLS = ['bash', 'zsh', 'fish']

# `-n` is a syntax-check-only flag; fish spells it differently.
SYNTAX_CHECK = {
    'bash': ['bash', '-n'],
    'zsh': ['zsh', '-n'],
    'fish': ['fish', '--no-execute'],
}


def requires(shell):
    """Skip the test unless `shell` is installed."""
    if not shutil.which(shell):
        pytest.skip(f"{shell} is not installed")


def completion_script(env, shell):
    """What `git-nested completion <shell>` prints."""
    return env.run(['git-nested', 'completion', shell]).stdout


# ============================================================================
# The printed script
# ============================================================================


@pytest.mark.parametrize('shell', SHELLS)
def test_the_printed_script_is_valid_in_its_shell(env, shell):
    requires(shell)
    script = env.tmp / f"completion.{shell}"
    script.write_text(completion_script(env, shell))

    result = env.run([*SYNTAX_CHECK[shell], script], check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('shell', SHELLS)
def test_the_printed_script_binds_the_git_nested_command(env, shell):
    requires(shell)
    assert 'git-nested' in completion_script(env, shell)


def test_the_shell_is_detected_when_it_is_not_given(env):
    requires('bash')
    result = env.run(['bash', '-c', 'git-nested completion'])
    assert 'bash completion' in result.stdout


def test_an_unsupported_shell_is_rejected(env):
    result = env.run(['git-nested', 'completion', 'tcsh'], check=False)
    assert result.returncode != 0
    assert 'tcsh' in result.stderr


# ============================================================================
# Wiring the script up, the way the README and .rc document it
# ============================================================================


def test_bash_registers_completion_for_git_nested(env):
    requires('bash')
    result = env.run(['bash', '-c', 'eval "$(git-nested completion bash)"; complete -p git-nested'])
    assert '_git_nested_complete' in result.stdout


def test_bash_registers_the_function_git_dispatches_to(env):
    requires('bash')
    result = env.run(['bash', '-c', 'eval "$(git-nested completion bash)"; type -t _git_nested'])
    assert result.stdout.strip() == 'function'


def test_sourcing_the_rc_registers_bash_completion(env):
    requires('bash')
    result = env.run(['bash', '-c', f'source {env.test_dir}/.rc; complete -p git-nested'])
    assert '_git_nested_complete' in result.stdout


def test_zsh_registers_completion_for_git_nested(env):
    requires('zsh')
    script = f'autoload -Uz compinit; compinit -u; source {env.test_dir}/.rc; echo ${{_comps[git-nested]}}'
    result = env.run(['zsh', '-c', script])
    assert result.stdout.strip() == '_git_nested_complete'


def test_zsh_registers_the_function_git_dispatches_to(env):
    requires('zsh')
    script = f'source {env.test_dir}/.rc; (( $+functions[_git-nested] )) && echo DEFINED'
    result = env.run(['zsh', '-c', script])
    assert 'DEFINED' in result.stdout


def test_zsh_wiring_survives_a_shell_without_the_completion_system(env):
    """compdef only exists after compinit; without it, no error and no completion."""
    requires('zsh')
    result = env.run(['zsh', '-c', 'eval "$(git-nested completion zsh)"; echo OK'], check=False)
    assert result.returncode == 0
    assert 'OK' in result.stdout


def test_sourcing_the_fish_rc_offers_the_commands(env):
    requires('fish')
    result = env.run(['fish', '-c', f"source {env.test_dir}/.fish.rc; complete -C 'git-nested '"])
    offered = {line.split('\t')[0] for line in result.stdout.splitlines()}
    assert {'clone', 'push', 'pull', 'status'} <= offered


# ============================================================================
# The candidates themselves, through the shells
# ============================================================================


def complete_in_bash(env, line, cwd=None):
    """The words bash would offer for `line`, whose last word is being completed."""
    words = line.split(' ')
    array = ' '.join(f"'{word}'" for word in words)
    script = (
        'eval "$(git-nested completion bash)";'
        f' COMP_WORDS=({array});'
        f' COMP_CWORD={len(words) - 1};'
        ' _git_nested_complete;'
        ' printf "%s\\n" "${COMPREPLY[@]}"'
    )
    return [word for word in env.run(['bash', '-c', script], cwd=cwd).stdout.splitlines() if word]


def test_bash_completes_a_command_prefix(env):
    requires('bash')
    assert complete_in_bash(env, 'git-nested c') == ['clean', 'clone', 'commit', 'completion']


def test_bash_completes_through_the_git_subcommand(env):
    requires('bash')
    assert complete_in_bash(env, 'git nested stat') == ['status']


def test_bash_completes_a_flag_of_the_command(env):
    requires('bash')
    assert '--squash' in complete_in_bash(env, 'git nested push -')


def test_bash_does_not_offer_a_flag_another_command_owns(env):
    requires('bash')
    assert '--squash' not in complete_in_bash(env, 'git nested pull -')


def test_bash_completes_the_value_of_a_flag(env):
    requires('bash')
    assert complete_in_bash(env, 'git nested pull --method ') == ['merge', 'rebase']


def test_bash_completes_a_nested_subdir(env, foo_bar_cloned_and_nested):
    requires('bash')
    # The subdir comes before the flags: it is what is actually being asked for.
    assert complete_in_bash(env, 'git nested pull ', cwd=env.workspace / 'foo')[0] == 'bar'


# ============================================================================
# The hidden __complete subcommand
# ============================================================================


def test_dunder_complete_offers_every_command(env):
    result = env.run(['git-nested', '__complete', 'git-nested', ''])
    offered = set(result.stdout.split())
    assert {'clone', 'pull', 'push', 'status', 'completion', 'version'} <= offered


def test_dunder_complete_offers_the_shells(env):
    result = env.run(['git-nested', '__complete', 'git-nested', 'completion', ''])
    assert result.stdout.split()[: len(SHELLS)] == SHELLS


def test_dunder_complete_describes_when_asked(env):
    result = env.run(['git-nested', '__complete', '--describe', 'git-nested', 'status'])
    assert result.stdout.rstrip('\n') == 'status\treport on the nested repositories of this repository'


def test_dunder_complete_stays_quiet_about_an_unknown_command(env):
    result = env.run(['git-nested', '__complete', 'git-nested', 'bogus', ''])
    assert result.returncode == 0
    assert result.stdout == ''


def test_dunder_complete_never_fails_the_shell(env):
    """A <TAB> must never put a traceback on the user's prompt."""
    result = env.run(['git-nested', '__complete'], check=False)
    assert result.returncode == 0
    assert 'Traceback' not in result.stderr
