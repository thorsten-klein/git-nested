"""Shell completion candidates, computed from the parser's own tables.

The shell scripts `git nested completion` prints are thin: every <TAB>
shells back out to the hidden `__complete` subcommand, which lands here.
That is what keeps the candidates from drifting away from the parser --
both are built from `cli.spec`, so a new command or flag is offered the
moment it is added there.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .. import discovery, gitfile
from ..cli.spec import (
    COMMAND_HELP,
    GLOBAL_ARG_SPECS,
    POSITIONALS,
    SUBPARSER_ARG_SPECS,
    VALID_COMMAND_OPTIONS,
)
from ..constants import COMPLETION_SHELLS
from ..models import Flags

if TYPE_CHECKING:
    from ..git import GitRunner

# (word offered, description shown next to it). The description is only
# rendered by the shells that have a column for it -- see scripts.py.
Candidate = tuple[str, str]

# argparse adds these to every parser itself, so they are not in the spec.
HELP_FLAGS: list[Candidate] = [
    ('-h', "show this help message and exit"),
    ('--help', "show this help message and exit"),
]

# argparse actions that consume no following word. Anything else in the
# spec takes a value, and a <TAB> right after it completes that value
# rather than another flag.
_VALUELESS_ACTIONS = ('store_true', 'count')

# The words a shell may pass through ahead of the real arguments: the
# command line starts with `git nested` or with `git-nested`, depending on
# how the user invoked it, and neither is something to complete.
_COMMAND_WORDS = ('git', 'nested', 'git-nested')

# `clone` and `init` name a subdir that does not exist yet, so the nested
# repositories are the wrong candidates for them -- plain directories are.
_NEW_SUBDIR_COMMANDS = ('clone', 'init')


def _nested_subdirs(git: GitRunner, _cur: str) -> list[Candidate]:
    """Every nested repository in the current repository."""
    return [(str(subdir), '') for subdir in discovery.find_all_nested_repositories(git, Flags(all_deep=True))]


def _nested_branches(git: GitRunner, _cur: str) -> list[Candidate]:
    """Every local nested/* branch."""
    branches = git.check_output(['for-each-ref', '--format=%(refname:short)', 'refs/heads/nested/'], may_fail=True)
    return [(branch, '') for branch in branches.splitlines()]


def _shells(_git: GitRunner, _cur: str) -> list[Candidate]:
    """The shells a completion script can be printed for."""
    return [(shell, f"print the {shell} completion script") for shell in COMPLETION_SHELLS]


def _is_offerable_dir(entry: Path) -> bool:
    """Whether a directory entry is worth offering as a subdir candidate."""
    return entry.is_dir() and not entry.name.startswith('.')


def _directory_prefix(cur: str) -> Path:
    """The directory to list for a partly typed path.

    The prefix is taken off the string rather than via Path.parent, which
    normalises a trailing slash away: `ext/<TAB>` asks for what is inside
    `ext`, not for `ext` itself all over again.
    """
    if '/' not in cur:
        return Path()
    head = cur.rsplit('/', 1)[0]
    return Path(head or '/')


def _directories(_git: GitRunner, cur: str) -> list[Candidate]:
    """The directories under whatever path prefix has been typed so far."""
    base = _directory_prefix(cur)
    try:
        entries = sorted(entry for entry in base.iterdir() if _is_offerable_dir(entry))
    except OSError:
        return []
    return [(f"{entry.as_posix()}/", '') for entry in entries]


def _config_keys(_git: GitRunner, _cur: str) -> list[Candidate]:
    """The fields of a .gitnested file, described."""
    return list(gitfile.CONFIG_FIELDS.items())


_POSITIONAL_CANDIDATES: dict[str, Callable[[GitRunner, str], list[Candidate]]] = {
    'key': _config_keys,
    'nested_branch': _nested_branches,
    'nested_commit_ref': _nested_branches,
    'shell': _shells,
    'subdir': _nested_subdirs,
}

# Keyed by the option name in VALID_COMMAND_OPTIONS. An option absent from
# here takes a value git-nested cannot enumerate (a URL, a message, a path
# the shell completes better itself), so it offers nothing.
_VALUE_CANDIDATES: dict[str, list[Candidate]] = {
    'method': [('merge', "merge the upstream history"), ('rebase', "rebase onto the upstream history")],
}

# `config <subdir> <key> <value>`: what the third positional may be, keyed
# by the second. A key absent from here takes a value nothing can enumerate.
_CONFIG_VALUE_CANDIDATES: dict[str, list[Candidate]] = {
    'method': _VALUE_CANDIDATES['method'],
}


def _flag_candidates(command: str | None) -> list[Candidate]:
    """The flags accepted at this point: a command's own, or the global ones."""
    if command is None:
        return [*HELP_FLAGS, *((name, kwargs.get('help', '')) for names, kwargs in GLOBAL_ARG_SPECS for name in names)]
    opts = VALID_COMMAND_OPTIONS[command]
    return [
        *HELP_FLAGS,
        *(
            (name, kwargs.get('help', ''))
            for opt, names, kwargs in SUBPARSER_ARG_SPECS
            if opt in opts
            for name in names
        ),
    ]


def _value_flags() -> dict[str, str]:
    """Flag name -> option name, for the flags that consume the next word."""
    return {
        name: opt
        for opt, names, kwargs in SUBPARSER_ARG_SPECS
        if kwargs.get('action') not in _VALUELESS_ACTIONS
        for name in names
    }


def _is_command_word(word: str) -> bool:
    """Whether `word` is part of the `git nested` / `git-nested` prefix."""
    return PurePosixPath(word).name in _COMMAND_WORDS


def _strip_command_words(words: list[str]) -> list[str]:
    """Drop the invocation prefix a shell passes through ahead of the arguments.

    Doing it here rather than in each emitted script is what lets all three
    scripts hand over the whole command line unchanged, however it was
    spelled -- `git nested`, `git-nested`, or a path to a checkout's
    launcher.
    """
    index = 0
    while index < len(words) and _is_command_word(words[index]):
        index += 1
    return words[index:]


def _consumed_positionals(prev: list[str]) -> list[str]:
    """The positional words already typed, in order, with flags and their values dropped.

    An empty word is dropped too: a shell that cannot represent the word
    under the cursor any other way passes it as an empty argument, and it
    is not a positional anyone has typed yet.
    """
    value_flags = _value_flags()
    positionals = []
    skip = False
    for word in prev:
        if skip:
            skip = False
        elif word.startswith('-'):
            skip = word in value_flags
        elif word:
            positionals.append(word)
    return positionals


def _positional_candidates(git: GitRunner, cur: str, command: str, positionals: list[str]) -> list[Candidate]:
    """Candidates for the next positional of `command`, if it has one left."""
    # positionals[0] is the command itself, so the argument already typed
    # ahead of the one being completed sits at positionals[index].
    specs = POSITIONALS.get(command, [])
    index = len(positionals) - 1
    if index >= len(specs):
        return []
    name = specs[index][0]
    if name == 'subdir' and command in _NEW_SUBDIR_COMMANDS:
        return _directories(git, cur)
    if name == 'value':
        return _CONFIG_VALUE_CANDIDATES.get(positionals[index], [])
    provider = _POSITIONAL_CANDIDATES.get(name)
    return provider(git, cur) if provider else []


def _command_candidates(git: GitRunner, cur: str, positionals: list[str]) -> list[Candidate]:
    """Candidates once the command word is known.

    A word already begun with '-' can only be a flag, so the positional
    providers are skipped for it -- they would shell out to git to build a
    list every one of whose entries is about to be filtered away.
    """
    command = positionals[0]
    if command not in VALID_COMMAND_OPTIONS:
        return []
    if cur.startswith('-'):
        return _flag_candidates(command)
    return [
        *_positional_candidates(git, cur, command, positionals),
        *_flag_candidates(command),
    ]


def _all_candidates(git: GitRunner, cur: str, prev: list[str]) -> list[Candidate]:
    """Every candidate valid at this point, before filtering by what has been typed."""
    pending = _value_flags().get(prev[-1]) if prev else None
    if pending is not None:
        return _VALUE_CANDIDATES.get(pending, [])

    positionals = _consumed_positionals(prev)
    if not positionals:
        return [*((name, COMMAND_HELP[name]) for name in VALID_COMMAND_OPTIONS), *_flag_candidates(None)]
    return _command_candidates(git, cur, positionals)


def candidates(git: GitRunner, words: list[str]) -> list[Candidate]:
    """The candidates for the last word of `words`, which is the one being completed."""
    cur = words[-1] if words else ''
    prev = _strip_command_words(words[:-1])
    return [candidate for candidate in _all_candidates(git, cur, prev) if candidate[0].startswith(cur)]


def _candidate_line(candidate: Candidate, describe: bool) -> str:
    """One output line: the word alone, or word and description separated by a tab."""
    word, description = candidate
    if describe and description:
        return f"{word}\t{description}"
    return word


def _print_candidates(git: GitRunner, words: list[str]) -> None:
    """Print one line per candidate, honouring a leading --describe."""
    describe = bool(words) and words[0] == '--describe'
    for candidate in candidates(git, words[1:] if describe else words):
        print(_candidate_line(candidate, describe))


def handle_dunder_complete(git: GitRunner, argv: list[str]) -> bool:
    """Serve the hidden `__complete` subcommand, if that is what `argv` asks for.

    Returns:
        True if `argv` was a completion request and has been answered.

    Anything at all going wrong while computing candidates is swallowed: this
    runs on every <TAB> the user presses, and a traceback (or a SystemExit --
    output.error() calls sys.exit(1) when a candidate needs a git command
    that fails, e.g. outside a repository) landing on their prompt is far
    worse than an empty candidate list.
    """
    if not argv or argv[0] != '__complete':
        return False
    try:
        _print_candidates(git, argv[1:])
    except (Exception, SystemExit):  # NOSONAR(S5754) deliberate, see docstring above
        return True
    return True
