"""The tables that define git-nested's command line.

Everything the parser knows about commands, their flags and their
positionals lives here as plain data, so that anything else that needs to
reason about the CLI -- shell completion, `git nested config`, the man page
-- reads the same tables the parser is built from instead of a copy.
"""

from __future__ import annotations

# Which flags each command accepts. The keys are also the command list:
# the subparsers, and the completion candidates, are built from them.
VALID_COMMAND_OPTIONS: dict[str, list[str]] = {
    'branch': ['all', 'fetch', 'force'],
    'clean': ['ALL', 'all', 'force'],
    'clone': ['branch', 'filter', 'force', 'message', 'method'],
    'commit': ['fetch', 'force', 'message', 'msg_file'],
    'diff': ['all', 'branch', 'remote'],
    'fetch': ['all', 'branch', 'force', 'remote'],
    'init': ['branch', 'remote', 'method'],
    'pull': ['all', 'branch', 'force', 'message', 'method', 'remote', 'update'],
    'push': ['all', 'branch', 'commit', 'force', 'message', 'method', 'msg_file', 'remote', 'squash', 'update'],
    'status': ['ALL', 'all', 'fetch'],
    'version': [],
}

# (option name in VALID_COMMAND_OPTIONS, argparse flag names, argparse kwargs)
SUBPARSER_ARG_SPECS: list[tuple[str, tuple[str, ...], dict]] = [
    ('all', ('-a', '--all'), {'action': 'store_true', 'dest': 'all_flag'}),
    ('ALL', ('-A', '--ALL'), {'action': 'store_true', 'dest': 'ALL_flag'}),
    ('branch', ('-b', '--branch'), {'dest': 'branch'}),
    ('commit', ('-c', '--commit'), {'action': 'store_true'}),
    ('force', ('-f', '--force'), {'action': 'store_true'}),
    ('filter', ('--filter',), {'action': 'append'}),
    ('fetch', ('-F', '--fetch'), {'action': 'store_true', 'dest': 'fetch_flag'}),
    ('method', ('-M', '--method'), {'dest': 'method'}),
    ('message', ('-m', '--message'), {'dest': 'message'}),
    ('msg_file', ('--file',), {'dest': 'msg_file'}),
    ('remote', ('-r', '--remote'), {'dest': 'remote'}),
    ('squash', ('-s', '--squash'), {'action': 'store_true'}),
    ('update', ('-u', '--update'), {'action': 'store_true'}),
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
    'diff': [('subdir', {'nargs': '?'})],
    'fetch': [('subdir', {'nargs': '?'})],
    'init': [('subdir', {'nargs': '?'})],
    'pull': [('subdir', {'nargs': '?'})],
    'push': [('subdir', {'nargs': '?'}), ('nested_branch', {'nargs': '?'})],
}
