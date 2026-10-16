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
    'branch': ['all', 'dir', 'fetch', 'force', 'gpg_sign', 'name'],
    'clean': ['ALL', 'all', 'force'],
    'clone': ['branch', 'filter', 'force', 'gpg_sign', 'message', 'method', 'recurse_submodules', 'signoff'],
    'commit': ['fetch', 'force', 'gpg_sign', 'message', 'msg_file', 'signoff'],
    'completion': [],
    'config': [],
    'diff': ['all', 'branch', 'remote'],
    'fetch': ['all', 'branch', 'force', 'remote'],
    'init': ['branch', 'from_submodule', 'gpg_sign', 'remote', 'method', 'signoff'],
    'pull': ['all', 'branch', 'force', 'gpg_sign', 'message', 'method', 'remote', 'signoff', 'update'],
    'repair': ['all', 'gpg_sign', 'message', 'msg_file', 'signoff'],
    'run': [],
    'push': [
        'all',
        'branch',
        'commit',
        'force',
        'gpg_sign',
        'message',
        'method',
        'msg_file',
        'remote',
        'signoff',
        'squash',
        'update',
    ],
    'status': ['ALL', 'all', 'fetch', 'short'],
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
    'repair': "point a nested repository's sync point back into the current history",
    'run': "run a git command in the worktree of a nested repository",
    'status': "report on the nested repositories of this repository",
    'version': "print version information",
}

# (argparse flag names, argparse kwargs) for the flags every command takes.
GLOBAL_ARG_SPECS: list[tuple[tuple[str, ...], dict]] = [
    (('--version',), {'action': 'store_true', 'help': "print the git-nested version number"}),
    (('-q', '--quiet'), {'action': 'store_true', 'help': "report only warnings and errors"}),
    (('-v', '--verbose'), {'action': 'count', 'help': "narrate the steps being taken; twice to log every git command"}),
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
    (
        'dir',
        ('-d', '--dir'),
        {'dest': 'dir', 'help': "where to put the worktree; defaults to .git/tmp/nested/<subdir>"},
    ),
    (
        'commit',
        ('-c', '--commit'),
        {'action': 'store_true', 'help': "record the pushed commit in .gitnested; needs a push to the tracked branch"},
    ),
    ('force', ('-f', '--force'), {'action': 'store_true', 'help': "force the operation"}),
    (
        'from_submodule',
        ('--from-submodule',),
        {'action': 'store_true', 'help': "turn the submodule at <subdir> into a nested repository"},
    ),
    (
        'recurse_submodules',
        ('--recurse-submodules',),
        {'action': 'store_true', 'help': "nest the submodules of upstream too, at the commits it pins"},
    ),
    (
        'gpg_sign',
        ('-S', '--gpg-sign'),
        {'action': 'store_true', 'dest': 'gpg_sign', 'help': "GPG-sign the commits git-nested makes, nested ones too"},
    ),
    (
        'signoff',
        ('--signoff',),
        {'action': 'store_true', 'help': "add a Signed-off-by trailer to the commit git-nested makes"},
    ),
    ('filter', ('--filter',), {'action': 'append', 'help': "only consider this path of the nested repository"}),
    (
        'fetch',
        ('-F', '--fetch'),
        {'action': 'store_true', 'dest': 'fetch_flag', 'help': "fetch the upstream content first"},
    ),
    ('method', ('-M', '--method'), {'dest': 'method', 'help': "join method: 'merge' (default) or 'rebase'"}),
    (
        'name',
        ('-n', '--name'),
        {'dest': 'name', 'help': "name of the nested branch; defaults to nested/<subdir>"},
    ),
    ('message', ('-m', '--message'), {'dest': 'message', 'help': "commit message"}),
    ('msg_file', ('--file',), {'dest': 'msg_file', 'help': "file to read the commit message from"}),
    ('remote', ('-r', '--remote'), {'dest': 'remote', 'help': "upstream remote to push/pull/fetch"}),
    (
        'short',
        ('--short',),
        {'action': 'store_true', 'help': "one line per repository: <subdir> <local commits> <behind> <changed|same>"},
    ),
    (
        'squash',
        ('-s', '--squash'),
        {'action': 'store_true', 'help': "squash the pushed commits into one, with -m/--file as its message"},
    ),
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
    ('dir', 'dir'),
    ('name', 'name'),
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
    'repair': [('subdir', {'nargs': '?', 'help': _SUBDIR_HELP})],
    'run': [
        ('subdir', {'help': _SUBDIR_HELP}),
        # argparse.REMAINDER, spelled out to keep this module free of argparse:
        # everything after <subdir> goes to git untouched, options included.
        ('git_args', {'nargs': '...', 'help': "the git command to run, with its arguments"}),
    ],
}

# The paragraph `git nested <command> --help` opens with. COMMAND_HELP is
# the one-line summary in the command list; this is room to say what the
# command actually does to the repository.
COMMAND_DESCRIPTION: dict[str, str] = {
    'branch': (
        "Build a 'nested/<subdir>' branch from the commits in <subdir> since the last sync, "
        "and check it out in a worktree, at <dir> if given. Use it to look at the nested history on its own, "
        "or to fix up a pull that stopped on conflicts. If <dir> already holds the worktree of <subdir>, "
        "the branch is rebuilt there; the worktree of anything else is never touched. "
        "--name picks another branch name than nested/<subdir>; it is remembered, "
        "so the other commands use that branch too, until 'git nested clean'."
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
    'repair': (
        "Fix the parent recorded in <subdir>/.gitnested when it is no longer part of the current history, "
        "as happens when a branch with a pull or clone on it is squash-merged or rebased. "
        "The new parent is the commit before the one that last changed the upstream commit, "
        "which is what that pull would have recorded had it been made here; the change is committed. "
        "A parent that is still part of the history is left alone."
    ),
    'run': (
        "Run 'git -C <worktree> <git command>' in the worktree of <subdir>, wherever 'git nested branch' "
        "put it. git's output and exit code are passed through unchanged. "
        "There has to be a worktree already: create it with 'git nested branch <subdir>'."
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
        "git nested branch -d ../lib ext/lib",
        "git nested branch --name lib-fixes ext/lib",
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
    'repair': [
        "git nested repair ext/lib",
        "git nested repair --all",
    ],
    'run': [
        "git nested run ext/lib log --oneline",
        "git nested run ext/lib status",
    ],
    'status': [
        "git nested status",
        "git nested status -q",
    ],
    'version': [
        "git nested version",
    ],
}
