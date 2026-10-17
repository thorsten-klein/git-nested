"""Turning argv into a command name and the CommandContext to run it with."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from .. import output, refs
from ..models import CommandContext, Flags
from .spec import (
    COMMAND_DESCRIPTION,
    COMMAND_EXAMPLES,
    COMMAND_HELP,
    GLOBAL_ARG_SPECS,
    POSITIONALS,
    SUBPARSER_ARG_SPECS,
    SUPPORTED_OPT_ATTRS,
    VALID_COMMAND_OPTIONS,
)

if TYPE_CHECKING:
    from ..git import GitRunner


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and all per-command subparsers."""
    parser = argparse.ArgumentParser(prog='git nested')
    for arg_names, kwargs in GLOBAL_ARG_SPECS:
        parser.add_argument(*arg_names, **kwargs)
    subparsers = parser.add_subparsers(dest='command')
    for command in VALID_COMMAND_OPTIONS:
        _add_subparser(subparsers, command)
    return parser


def _add_subparser(subparsers: argparse._SubParsersAction, command: str) -> None:
    """Add the subparser of one command, with its flags, positionals and help texts.

    RawDescriptionHelpFormatter so that the examples keep their line breaks;
    argparse would otherwise reflow them into a paragraph. That leaves the
    description unwrapped too, so it is wrapped here -- to a fixed width
    rather than the terminal's, which keeps `--help` reproducible.
    """
    examples = "\n".join(f"  {line}" for line in COMMAND_EXAMPLES[command])
    command_subparser = subparsers.add_parser(
        command,
        help=COMMAND_HELP[command],
        description=textwrap.fill(COMMAND_DESCRIPTION[command], width=78),
        epilog=f"examples:\n{examples}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    for opt, arg_names, kwargs in SUBPARSER_ARG_SPECS:
        if opt in VALID_COMMAND_OPTIONS[command]:
            command_subparser.add_argument(*arg_names, **kwargs)
    for name, kwargs in POSITIONALS.get(command, []):
        command_subparser.add_argument(name, **kwargs)


def _flags_from_args(args: argparse.Namespace) -> Flags:
    """Build a Flags object from parsed args, applying per-command option support rules."""
    flags = Flags(
        adopt=getattr(args, 'adopt', False),
        all=getattr(args, 'all_flag', False) or getattr(args, 'ALL_flag', False),
        all_deep=getattr(args, 'ALL_flag', False),
        commit=getattr(args, 'commit', False),
        exclude=getattr(args, 'exclude', []),
        filter=getattr(args, 'filter', []),
        force=getattr(args, 'force', False),
        from_submodule=getattr(args, 'from_submodule', False),
        recurse_submodules=getattr(args, 'recurse_submodules', False),
        gpg_sign=getattr(args, 'gpg_sign', False),
        signoff=getattr(args, 'signoff', False),
        single_commit=getattr(args, 'single_commit', False),
        fetch=getattr(args, 'fetch_flag', False),
        short=getattr(args, 'short', False),
        no_squash=getattr(args, 'no_squash', False),
        squash=getattr(args, 'squash', False),
        update=getattr(args, 'update', False),
        quiet=getattr(args, 'quiet', False),
        # argparse's `count` action leaves the attribute at None when the flag
        # is absent, and the output layer wants a real count.
        verbose=getattr(args, 'verbose', 0) or 0,
    )
    # A subparser only has the attributes of the options its command takes.
    for opt, flag_attr in SUPPORTED_OPT_ATTRS:
        if getattr(args, opt, None) is not None:
            setattr(flags, flag_attr, getattr(args, opt))

    if flags.message_file and not Path(flags.message_file).is_file():
        output.error(f"no commit message file at {flags.message_file}")
    if flags.message_file and flags.message:
        output.error("-m and --file can't be used together")
    return flags


# Flags that name one thing, so they make no sense for every nested repository at once.
_SINGLE_TARGET_FLAGS = (
    ('dir', "--dir names one worktree, so it can't be used with --all"),
    ('name', "--name names one branch, so it can't be used with --all"),
)


def _check_flags(flags: Flags) -> None:
    """Reject the flags that cannot be honoured together."""
    for attr, message in _SINGLE_TARGET_FLAGS:
        if flags.all and getattr(flags, attr):
            output.usage_error(message)
    if flags.update and not (flags.branch or flags.remote):
        output.usage_error("--update needs --branch or --remote to have something to update")


def parse_args(git: GitRunner, args_list: list[str]) -> tuple[str, CommandContext]:
    """Parse command line arguments into a command name and the context to run it with.

    Returns:
        tuple: (command, context). The context's git_tmp/head_commit are left
        unset -- only the caller knows whether the command runs in a repository.
    """
    args = build_arg_parser().parse_args(args_list)

    if args.version:
        args.command = 'version'
    if not args.command:
        output.usage_error("no command given; 'git nested --help' lists them")

    flags = _flags_from_args(args)
    _check_flags(flags)
    if flags.single_commit and not flags.all:
        output.usage_error("--single-commit needs --all")

    upstream = getattr(args, 'upstream', None)
    subdir = getattr(args, 'subdir', None)
    if upstream and not subdir:
        subdir = refs.guess_subdir(upstream)

    context = CommandContext(
        git=git,
        flags=flags,
        subdir=subdir,
        upstream=upstream,
        # 'commit's positional is named nested_commit_ref, 'push's is nested_branch --
        # only one of the two is ever present on args, depending on the subcommand.
        nested_commit_ref=getattr(args, 'nested_commit_ref', None) or getattr(args, 'nested_branch', None),
        completion_shell=getattr(args, 'shell', None),
        config_key=getattr(args, 'key', None),
        config_value=getattr(args, 'value', None),
        git_args=getattr(args, 'git_args', None),
    )
    return args.command, context
