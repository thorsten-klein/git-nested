"""Build the Sphinx command reference from the CLI spec tables."""

from __future__ import annotations

from pathlib import Path

from .cli.spec import (
    COMMAND_DESCRIPTION,
    COMMAND_EXAMPLES,
    COMMAND_HELP,
    GLOBAL_ARG_SPECS,
    POSITIONALS,
    SUBPARSER_ARG_SPECS,
    VALID_COMMAND_OPTIONS,
)

_OPTION_VALUE_NAMES = {
    'branch': 'branch',
    'dir': 'dir',
    'exclude': 'path',
    'filter': 'path',
    'message': 'message',
    'method': 'merge|rebase',
    'msg_file': 'file',
    'name': 'name',
    'remote': 'remote',
    'upstream_commit': 'commit',
}

_POSITIONAL_VALUE_NAMES = {
    'git_args': 'git-cmd',
}


def write_sphinx_command_reference(source_dir: Path) -> None:
    """Write the generated command reference pages under a Sphinx source dir."""
    commands_dir = source_dir / 'commands'
    commands_dir.mkdir(exist_ok=True)
    _remove_stale_pages(commands_dir)
    (commands_dir / 'index.md').write_text(command_reference_index(), encoding='utf-8')
    for command in sorted(VALID_COMMAND_OPTIONS):
        (commands_dir / f'{command}.md').write_text(command_reference_page(command), encoding='utf-8')


def _remove_stale_pages(commands_dir: Path) -> None:
    """Remove generated pages that no longer have a matching command."""
    wanted = {'index.md', *(f'{command}.md' for command in VALID_COMMAND_OPTIONS)}
    for path in commands_dir.glob('*.md'):
        if path.name not in wanted:
            path.unlink()


def command_reference_index() -> str:
    """Build the index page of the generated command reference."""
    lines = [
        '# Command reference',
        '',
        'These pages come from `git_nested.cli.spec`, the same tables `--help` uses.',
        '',
        '## Global flags',
        '',
        *(_bullet(_format_flag_names(names), kwargs['help']) for names, kwargs in GLOBAL_ARG_SPECS),
        '',
        'Every command also accepts `-h`, `--help`.',
        '',
        '```{toctree}',
        ':maxdepth: 1',
        '',
        *sorted(VALID_COMMAND_OPTIONS),
        '```',
    ]
    return '\n'.join(lines) + '\n'


def command_reference_page(command: str) -> str:
    """Build one generated command reference page."""
    option_lines = [
        _bullet(_format_flag_names(names, _option_value_name(opt, kwargs)), kwargs['help'])
        for opt, names, kwargs in SUBPARSER_ARG_SPECS
        if opt in VALID_COMMAND_OPTIONS[command]
    ]
    positional_lines = [
        _bullet(_format_positional(name, kwargs), kwargs['help']) for name, kwargs in POSITIONALS.get(command, [])
    ]
    lines = [
        f'# `git nested {command}`',
        '',
        COMMAND_HELP[command],
        '',
        COMMAND_DESCRIPTION[command],
        '',
        '## Options',
        '',
    ]
    if option_lines:
        lines.extend(['Every command also accepts `-h`, `--help`.', '', *option_lines])
    else:
        lines.append('This command has no command-specific options. It still accepts `-h`, `--help`.')
    lines.extend(['', '## Positional arguments', ''])
    if positional_lines:
        lines.extend(positional_lines)
    else:
        lines.append('This command takes no positional arguments.')
    lines.extend(['', '## Examples', '', '```bash', *COMMAND_EXAMPLES[command], '```'])
    return '\n'.join(lines) + '\n'


def _bullet(name: str, help_text: str) -> str:
    return f'- {name} — {help_text}'


def _format_flag_names(names: tuple[str, ...], value_name: str | None = None) -> str:
    suffix = '' if value_name is None else f' <{value_name}>'
    return ', '.join(f'`{name}{suffix}`' for name in names)


def _option_value_name(option: str, kwargs: dict) -> str | None:
    if kwargs.get('action') in {'store_true', 'count'}:
        return None
    if kwargs.get('action') == 'append' or 'dest' in kwargs:
        return _OPTION_VALUE_NAMES[option]
    return None


def _format_positional(name: str, kwargs: dict) -> str:
    if name == 'git_args':
        token = '<git-cmd>...'  # nosec B105 - docs placeholder, not a secret
    elif 'choices' in kwargs:
        token = '<' + '|'.join(str(choice) for choice in kwargs['choices']) + '>'
    else:
        token = f"<{_POSITIONAL_VALUE_NAMES.get(name, name.replace('_', '-'))}>"
    if kwargs.get('nargs') == '?':
        token = f'[{token}]'
    return f'`{token}`'
