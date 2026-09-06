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

# Most commands take the same first positional, so it gets the same text.
_SUBDIR_HELP = "the nested repository to act on"

# Positional arguments, in the order argparse must see them. A command
# absent from this table takes none.
POSITIONALS: dict[str, list[tuple[str, dict]]] = {
    'branch': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'clean': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'clone': [
        ('upstream', {'help': "URL or path of the repository to clone"}),
        ('subdir', {'nargs': '?', 'help': "where to put it; defaults to the name of the upstream"}),
    ],
    'commit': [
        ('subdir', {'nargs': '?', 'help': _SUBDIR_HELP}),
        ('nested_commit_ref', {'nargs': '?', 'help': "branch or commit to add; defaults to nested/<subdir>"}),
    ],
    'completion': [
        ('shell', {'nargs': '?', 'choices': list(COMPLETION_SHELLS), 'help': "shell to print the script for"})
    ],
    'config': [
        ('subdir', {'nargs': '?', 'help': _SUBDIR_HELP}),
        ('key', {'nargs': '?', 'help': "field to read or write; omit to print them all"}),
        ('value', {'nargs': '?', 'help': "new value for the field; omit to read it"}),
    ],
    'diff': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'fetch': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'init': [('subdir', {'nargs': '?', 'help': "subdirectory to turn into a nested repository"})],
    'pull': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'push': [
        ('subdir', {'nargs': '?', 'help': _SUBDIR_HELP}),
        ('nested_branch', {'nargs': '?', 'help': "branch to push; defaults to nested/<subdir>"}),
    ],
}

# The paragraph `git nested <command> --help` opens with. COMMAND_HELP is
# the one-line summary in the command list; this is room to say what the
# command actually does to the repository.
COMMAND_DESCRIPTION: dict[str, str] = {
    'branch': (
        "Build a 'nested/<subdir>' branch from the commits in <subdir> since the last sync, "
        "and check it out in a worktree. Use it to look at the nested history on its own, "
        "or to fix up a pull that stopped on conflicts."
    ),
    'clean': (
        "Delete the branches, refs, remotes and worktrees that other git-nested commands left behind. "
        "Nothing in your own history is touched, so this is also how you abandon a half-finished pull or push."
    ),
    'clone': (
        "Copy an upstream repository into <subdir> and commit it, with a .gitnested file recording where it came from. "
        "The result is ordinary files in ordinary commits: everyone who clones the parent repository gets them, "
        "with no extra command to run."
    ),
    'commit': (
        "Take a 'nested/<subdir>' branch and add it to the current history as a single commit. "
        "This is the step that finishes a pull you resolved by hand."
    ),
    'completion': (
        "Print the shell completion script for git-nested. "
        "With no shell named, the shell that invoked git-nested is guessed."
    ),
    'config': (
        "Read or write the fields of <subdir>/.gitnested. "
        "With no key, every field is printed; with a key, just that one; with a value, the field is written. "
        "The fields git-nested maintains itself (commit, cmdver, filter) can be read but not written."
    ),
    'diff': (
        "Show what <subdir> has locally that its upstream does not, as an ordinary diff. "
        "Nothing is fetched first unless you ask for it."
    ),
    'fetch': (
        "Fetch the upstream branch of <subdir> into a local ref, without changing any file. "
        "Other commands fetch when they need to; this is for looking first."
    ),
    'init': (
        "Turn a subdirectory you already have into a nested repository by writing <subdir>/.gitnested. "
        "The files are left as they are. Without --remote the subdirectory has no upstream yet, "
        "which you can add later with 'git nested config'."
    ),
    'pull': (
        "Fetch the upstream of <subdir> and join the new commits into it, by merge or by rebase. "
        "If that conflicts, the half-finished work is left in a worktree and the way to finish it by hand is printed."
    ),
    'push': (
        "Send the commits you made in <subdir> to its upstream. "
        "Only the changes inside the subdirectory go; the rest of the parent repository is not part of it."
    ),
    'status': (
        "Report every nested repository in this repository: where it comes from, and whether it has local changes. "
        "With -q, just the paths, one per line."
    ),
    'version': "Print the git-nested version, and the versions of git and Python it is running on.",
}

# Examples, printed after the options by `git nested <command> --help`.
COMMAND_EXAMPLES: dict[str, list[str]] = {
    'branch': [
        "git nested branch ext/lib",
        "git nested branch --all",
    ],
    'clean': [
        "git nested clean ext/lib",
        "git nested clean --all",
    ],
    'clone': [
        "git nested clone https://github.com/user/lib ext/lib",
        "git nested clone -b develop https://github.com/user/lib ext/lib",
    ],
    'commit': [
        "git nested commit ext/lib",
        "git nested commit --file=msg.txt ext/lib",
    ],
    'completion': [
        'eval "$(git-nested completion bash)"    # ~/.bashrc',
        'eval "$(git-nested completion zsh)"     # ~/.zshrc, after compinit',
        "git-nested completion fish | source     # ~/.config/fish/config.fish",
    ],
    'config': [
        "git nested config ext/lib",
        "git nested config ext/lib method",
        "git nested config ext/lib method rebase",
    ],
    'diff': [
        "git nested diff ext/lib",
        "git nested diff --all",
    ],
    'fetch': [
        "git nested fetch ext/lib",
        "git nested fetch --all",
    ],
    'init': [
        "git nested init doc",
        "git nested init -r https://github.com/user/lib -b main ext/lib",
    ],
    'pull': [
        "git nested pull ext/lib",
        "git nested pull -M rebase ext/lib",
        "git nested pull --all",
    ],
    'push': [
        "git nested push ext/lib",
        "git nested push --squash -m 'one commit upstream' ext/lib",
    ],
    'status': [
        "git nested status",
        "git nested status -q",
    ],
    'version': [
        "git nested version",
    ],
}
