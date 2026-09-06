"""Unit tests for the completion candidate engine and the scripts it prints"""

from __future__ import annotations

import contextlib

import pytest
from fakes import FakeGit

from git_nested import completion
from git_nested.cli.spec import VALID_COMMAND_OPTIONS
from git_nested.completion import scripts
from git_nested.constants import COMPLETION_SHELLS


@pytest.fixture
def git():
    return FakeGit()


def words(git, line: str) -> list[str]:
    """The candidate words for `line`, whose last word is the one being completed."""
    return [word for word, _ in completion.candidates(git, line.split(' '))]


# ============================================================================
# Candidates: the command word
# ============================================================================


def test_every_command_is_offered(git):
    assert set(VALID_COMMAND_OPTIONS) <= set(words(git, 'git-nested '))


def test_the_commands_are_offered_through_git(git):
    assert set(VALID_COMMAND_OPTIONS) <= set(words(git, 'git nested '))


def test_the_commands_are_offered_through_a_launcher_path(git):
    assert 'status' in words(git, '/opt/checkout/lib/git-nested ')


def test_a_prefix_narrows_the_commands(git):
    assert words(git, 'git nested cl') == ['clean', 'clone']


def test_the_global_flags_are_offered_alongside_the_commands(git):
    assert {'-h', '--help', '--version', '-q', '--verbose'} <= set(words(git, 'git nested -'))


def test_an_unknown_command_offers_nothing(git):
    assert words(git, 'git nested bogus ') == []


# ============================================================================
# Candidates: flags and their values
# ============================================================================


def test_a_flag_is_completed_without_asking_git(git):
    """FakeGit raises on an unregistered call, so this fails if a provider runs."""
    assert words(git, 'git nested pull -f') == ['-f']


def test_a_command_offers_its_own_flags(git):
    assert {'-s', '--squash', '-c', '--commit'} <= set(words(git, 'git nested push -'))


def test_a_command_does_not_offer_another_commands_flags(git):
    assert '--squash' not in words(git, 'git nested pull -')


def test_every_offered_flag_carries_its_help(git):
    assert all(description for _, description in completion.candidates(git, ['git-nested', 'push', '-']))


def test_a_flag_that_takes_a_value_completes_that_value(git):
    assert words(git, 'git nested pull --method ') == ['merge', 'rebase']
    assert words(git, 'git nested pull -M r') == ['rebase']


def test_a_flag_whose_value_cannot_be_enumerated_offers_nothing(git):
    assert words(git, 'git nested pull --branch ') == []


def test_a_valueless_flag_does_not_swallow_the_next_word(git):
    """`--force` takes no value, so what follows it is still the subdir."""
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    assert words(git, 'git nested pull --force ')[0] == 'ext/lib'


def test_a_flags_value_is_not_counted_as_a_positional(git):
    """`-m msg` is two words but no positional, so the subdir is still open."""
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    assert words(git, 'git nested push -m msg ')[0] == 'ext/lib'


# ============================================================================
# Candidates: positionals
# ============================================================================


def test_the_subdir_offers_the_nested_repositories(git):
    git.respond('ls-files', stdout='ext/lib/.gitnested\next/lib/deep/.gitnested\nREADME.md\n')
    assert words(git, 'git nested pull ')[:2] == ['ext/lib', 'ext/lib/deep']


def test_a_command_without_positionals_offers_only_flags(git):
    assert words(git, 'git nested version ') == ['-h', '--help']


def test_a_positional_past_the_last_one_offers_only_flags(git):
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    assert words(git, 'git nested pull ext/lib ')[:2] == ['-h', '--help']


def test_the_second_positional_of_push_offers_the_nested_branches(git):
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    git.respond('for-each-ref', stdout='nested/ext/lib\nnested/other\n')
    assert words(git, 'git nested push ext/lib ')[:2] == ['nested/ext/lib', 'nested/other']


def test_commit_offers_the_nested_branches_too(git):
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    git.respond('for-each-ref', stdout='nested/ext/lib\n')
    assert words(git, 'git nested commit ext/lib ')[0] == 'nested/ext/lib'


def test_completion_offers_the_shells(git):
    assert words(git, 'git nested completion ')[: len(COMPLETION_SHELLS)] == list(COMPLETION_SHELLS)


def test_the_shells_are_described(git):
    assert ('bash', "print the bash completion script") in completion.candidates(git, ['git-nested', 'completion', ''])


# ============================================================================
# Candidates: the directories clone and init name
# ============================================================================


def test_a_new_subdir_offers_directories_not_nested_repositories(git, tmp_path, monkeypatch):
    (tmp_path / 'doc').mkdir()
    (tmp_path / '.hidden').mkdir()
    (tmp_path / 'file.txt').write_text('')
    monkeypatch.chdir(tmp_path)
    # No ls-files response is registered: asking git at all would fail the test.
    assert words(git, 'git nested init ')[0] == 'doc/'


def test_a_new_subdir_descends_into_the_typed_prefix(git, tmp_path, monkeypatch):
    (tmp_path / 'ext' / 'lib').mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert words(git, 'git nested clone url ext/')[0] == 'ext/lib/'


def test_an_unreadable_prefix_offers_no_directories(git, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert words(git, 'git nested init nosuchdir/') == []


# ============================================================================
# The __complete subcommand
# ============================================================================


def test_dunder_complete_prints_one_candidate_per_line(git, capsys):
    assert completion.handle_dunder_complete(git, ['__complete', 'git-nested', 'ver']) is True
    assert capsys.readouterr().out == 'version\n'


def test_dunder_complete_describes_when_asked(git, capsys):
    completion.handle_dunder_complete(git, ['__complete', '--describe', 'git-nested', 'ver'])
    assert capsys.readouterr().out == "version\tprint version information\n"


def test_dunder_complete_omits_an_empty_description(git, capsys):
    git.respond('ls-files', stdout='ext/lib/.gitnested\n')
    completion.handle_dunder_complete(git, ['__complete', '--describe', 'git-nested', 'pull', 'ext'])
    assert capsys.readouterr().out.splitlines()[0] == 'ext/lib'


def test_anything_that_is_not_a_completion_request_is_left_alone(git):
    assert completion.handle_dunder_complete(git, ['status']) is False
    assert completion.handle_dunder_complete(git, []) is False


def test_a_failure_while_completing_is_swallowed(git, monkeypatch):
    """A <TAB> must never put a traceback -- or an exit -- on the user's prompt."""

    def explode(*_args, **_kwargs):
        raise SystemExit(2)

    monkeypatch.setattr(completion, '_print_candidates', explode)
    assert completion.handle_dunder_complete(git, ['__complete', 'git-nested', '']) is True


# ============================================================================
# The printed scripts
# ============================================================================


@pytest.mark.parametrize('shell', COMPLETION_SHELLS)
def test_every_shell_gets_a_script_bound_to_the_command(shell):
    assert 'git-nested' in scripts.script(shell, ['git-nested'])


def test_the_bash_script_defines_the_function_git_dispatches_to():
    assert '_git_nested()' in scripts.script('bash', ['git-nested'])


def test_the_zsh_script_defines_the_function_git_dispatches_to():
    assert '_git-nested()' in scripts.script('zsh', ['git-nested'])


def test_the_zsh_script_tolerates_a_missing_completion_system():
    assert '$+functions[compdef]' in scripts.script('zsh', ['git-nested'])


def test_the_fish_script_binds_a_launcher_path_by_path():
    script = scripts.script('fish', ['git-nested', '/opt/checkout/lib/git-nested'])
    assert "complete -p /opt/checkout/lib/git-nested" in script
    assert "complete -c git-nested" in script


# ============================================================================
# Which command words the script binds
# ============================================================================


def test_the_command_is_always_bound(monkeypatch):
    monkeypatch.setattr(scripts.sys, 'argv', ['-c'])
    assert scripts.bind_names() == ['git-nested']


def test_the_launcher_that_was_invoked_is_bound_too(monkeypatch, tmp_path):
    launcher = tmp_path / 'lib' / 'git-nested'
    launcher.parent.mkdir()
    launcher.write_text('')
    monkeypatch.setattr(scripts.sys, 'argv', [str(launcher)])
    assert scripts.bind_names() == ['git-nested', str(launcher)]


def test_a_relative_launcher_is_bound_by_both_names(monkeypatch, tmp_path):
    (tmp_path / 'git-nested').write_text('')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scripts.sys, 'argv', ['./git-nested'])
    assert scripts.bind_names() == ['git-nested', './git-nested', str(tmp_path / 'git-nested')]


# ============================================================================
# Detecting the shell for a bare `completion`
# ============================================================================


def test_the_parent_process_names_the_shell(monkeypatch):
    monkeypatch.setattr(scripts, '_parent_process_name', lambda: 'fish')
    assert scripts.detect_shell() == 'fish'


def test_the_shell_variable_is_the_fallback(monkeypatch):
    monkeypatch.setattr(scripts, '_parent_process_name', lambda: 'sshd')
    monkeypatch.setenv('SHELL', '/usr/bin/zsh')
    assert scripts.detect_shell() == 'zsh'


def test_bash_is_the_last_resort(monkeypatch):
    monkeypatch.setattr(scripts, '_parent_process_name', lambda: None)
    monkeypatch.delenv('SHELL', raising=False)
    assert scripts.detect_shell() == 'bash'


def test_the_parent_process_name_is_read_from_proc():
    # Whatever ran pytest; only that it answers without raising matters here.
    assert scripts._parent_process_name() is None or isinstance(scripts._parent_process_name(), str)


def test_an_unreadable_parent_is_not_an_error(monkeypatch):
    monkeypatch.setattr(scripts.os, 'getppid', lambda: 0)
    assert scripts._parent_process_name() is None


# ============================================================================
# The command handler
# ============================================================================


def test_the_command_prints_the_script_for_the_requested_shell(git, capsys):
    from git_nested.commands.completion import cmd_completion
    from git_nested.models import CommandContext, Flags

    cmd_completion(CommandContext(git=git, flags=Flags(), completion_shell='fish'))
    assert '__git_nested_complete' in capsys.readouterr().out


def test_the_command_falls_back_to_the_detected_shell(git, capsys, monkeypatch):
    from git_nested.commands.completion import cmd_completion
    from git_nested.models import CommandContext, Flags

    monkeypatch.setattr(scripts, 'detect_shell', lambda: 'bash')
    with contextlib.suppress(SystemExit):
        cmd_completion(CommandContext(git=git, flags=Flags()))
    assert '_git_nested_complete' in capsys.readouterr().out
