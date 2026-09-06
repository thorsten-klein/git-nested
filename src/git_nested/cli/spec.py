"""The tables that define git-nested's command line.

Everything the parser knows about commands, their flags and their
positionals lives here as plain data, so that anything else that needs to
reason about the CLI -- shell completion, `git nested config`, the man page
-- reads the same tables the parser is built from instead of a copy.
"""

from __future__ import annotations

from ..constants import COMPLETION_SHELLS

# Which flags each command accepts. The keys are also the command list:
# the subparsers, and the completion candidates, are built from them.
VALID_COMMAND_OPTIONS: dict[str, list[str]] = {
    'branch': ['all', 'fetch', 'force'],
    'clean': ['ALL', 'all', 'force'],
    'clone': ['branch', 'filter', 'force', 'message', 'method'],
    'commit': ['fetch', 'force', 'message', 'msg_file'],
    'completion': [],
    'config': [],
    'diff': ['all', 'branch', 'remote'],
    'fetch': ['all', 'branch', 'force', 'remote'],
    'init': ['branch', 'remote', 'method'],
    'pull': ['all', 'branch', 'force', 'message', 'method', 'remote', 'update'],
    'push': ['all', 'branch', 'commit', 'force', 'message', 'method', 'msg_file', 'remote', 'squash', 'update'],
    'status': ['ALL', 'all', 'fetch'],
    'version': [],
}

# One line per command, shown by `git nested --help` and offered as the
# description of each command by shell completion.
COMMAND_HELP: dict[str, str] = {
    'branch': "create a branch holding the local nested commits",
    'clean': "remove the branches, refs and remotes nested operations created",
    'clone': "clone an upstream repository into a subdirectory",
    'commit': "add a nested branch to the current history as one commit",
    'completion': "print the shell completion script for git-nested",
    'config': "read or write a nested repository's configuration",
    'diff': "show a nested repository's local changes against upstream",
    'fetch': "fetch upstream content for a nested repository",
    'init': "turn an existing subdirectory into a nested repository",
    'pull': "update a nested repository from its upstream",
    'push': "push a nested repository's local changes upstream",
    'status': "report on the nested repositories of this repository",
    'version': "print version information",
}

# (argparse flag names, argparse kwargs) for the flags every command takes.
GLOBAL_ARG_SPECS: list[tuple[tuple[str, ...], dict]] = [
    (('--version',), {'action': 'store_true', 'help': "print the git-nested version number"}),
    (('-q', '--quiet'), {'action': 'store_true', 'help': "report only warnings and errors"}),
    (('-v', '--verbose'), {'action': 'count', 'help': "narrate the steps being taken; twice to log every git command"}),
    (('-d', '--debug'), {'action': 'store_true', 'help': "log every git command as it is issued"}),
]

# (option name in VALID_COMMAND_OPTIONS, argparse flag names, argparse kwargs)
SUBPARSER_ARG_SPECS: list[tuple[str, tuple[str, ...], dict]] = [
    ('all', ('-a', '--all'), {'action': 'store_true', 'dest': 'all_flag', 'help': "act on all nested repositories"}),
    (
        'ALL',
        ('-A', '--ALL'),
        {'action': 'store_true', 'dest': 'ALL_flag', 'help': "act on all nested repositories and their sub-nesteds"},
    ),
    ('branch', ('-b', '--branch'), {'dest': 'branch', 'help': "upstream branch to push/pull/fetch"}),
    ('commit', ('-c', '--commit'), {'action': 'store_true', 'help': "record the pushed commit in .gitnested"}),
    ('force', ('-f', '--force'), {'action': 'store_true', 'help': "force the operation"}),
    ('filter', ('--filter',), {'action': 'append', 'help': "only consider this path of the nested repository"}),
    (
        'fetch',
        ('-F', '--fetch'),
        {'action': 'store_true', 'dest': 'fetch_flag', 'help': "fetch the upstream content first"},
    ),
    ('method', ('-M', '--method'), {'dest': 'method', 'help': "join method: 'merge' (default) or 'rebase'"}),
    ('message', ('-m', '--message'), {'dest': 'message', 'help': "commit message"}),
    ('msg_file', ('--file',), {'dest': 'msg_file', 'help': "file to read the commit message from"}),
    ('remote', ('-r', '--remote'), {'dest': 'remote', 'help': "upstream remote to push/pull/fetch"}),
    ('squash', ('-s', '--squash'), {'action': 'store_true', 'help': "squash the pushed commits into one"}),
    (
        'update',
        ('-u', '--update'),
        {'action': 'store_true', 'help': "write the --branch/--remote override to .gitnested"},
    ),
]

# (option name in the parsed args namespace, attribute name on Flags)
SUPPORTED_OPT_ATTRS: list[tuple[str, str]] = [
    ('branch', 'branch'),
    ('remote', 'remote'),
    ('method', 'method'),
    ('message', 'message'),
    ('msg_file', 'message_file'),
]

# Positional arguments, in the order argparse must see them. A command
# absent from this table takes none.
POSITIONALS: dict[str, list[tuple[str, dict]]] = {
    'branch': [('subdir', {'nargs': '?'})],
    'clean': [('subdir', {'nargs': '?'})],
    'clone': [('upstream', {}), ('subdir', {'nargs': '?'})],
    'commit': [('subdir', {'nargs': '?'}), ('nested_commit_ref', {'nargs': '?'})],
    'completion': [('shell', {'nargs': '?', 'choices': list(COMPLETION_SHELLS)})],
    'config': [('subdir', {'nargs': '?'}), ('key', {'nargs': '?'}), ('value', {'nargs': '?'})],
    'diff': [('subdir', {'nargs': '?'})],
    'fetch': [('subdir', {'nargs': '?'})],
    'init': [('subdir', {'nargs': '?'})],
    'pull': [('subdir', {'nargs': '?'})],
    'push': [('subdir', {'nargs': '?'}), ('nested_branch', {'nargs': '?'})],
}
