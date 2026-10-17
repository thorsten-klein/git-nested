from git_nested.cli.spec import (
    COMMAND_DESCRIPTION,
    COMMAND_EXAMPLES,
    COMMAND_HELP,
    GLOBAL_ARG_SPECS,
    VALID_COMMAND_OPTIONS,
)
from git_nested.docgen import (
    _option_value_name,
    command_reference_index,
    command_reference_page,
    write_sphinx_command_reference,
)


def test_command_reference_index_lists_global_flags_and_commands():
    text = command_reference_index()
    for names, kwargs in GLOBAL_ARG_SPECS:
        assert kwargs['help'] in text
        assert all(f'`{name}`' in text for name in names)
    for command in VALID_COMMAND_OPTIONS:
        assert f'\n{command}\n' in text


def test_command_reference_page_includes_spec_text():
    text = command_reference_page('push')
    assert COMMAND_HELP['push'] in text
    assert COMMAND_DESCRIPTION['push'] in text
    assert '`-b <branch>`' in text
    assert '`--branch <branch>`' in text
    assert '`[<subdir>]`' in text
    assert '`[<nested-branch>]`' in text
    for example in COMMAND_EXAMPLES['push']:
        assert example in text


def test_command_reference_page_handles_special_positionals():
    completion = command_reference_page('completion')
    run = command_reference_page('run')
    assert '`[<bash|zsh|fish>]`' in completion
    assert '`<git-cmd>...`' in run


def test_command_reference_page_handles_commands_without_options_or_arguments():
    text = command_reference_page('version')
    assert 'This command has no command-specific options.' in text
    assert 'This command takes no positional arguments.' in text


def test_write_sphinx_command_reference_replaces_stale_files(tmp_path):
    commands_dir = tmp_path / 'commands'
    commands_dir.mkdir()
    stale = commands_dir / 'old.md'
    stale.write_text('stale', encoding='utf-8')

    write_sphinx_command_reference(tmp_path)

    assert not stale.exists()
    assert (commands_dir / 'index.md').exists()
    for command in VALID_COMMAND_OPTIONS:
        assert (commands_dir / f'{command}.md').exists()


def test_option_value_name_returns_none_when_a_flag_takes_no_value():
    assert _option_value_name('unused', {}) is None
