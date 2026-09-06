"""Turning argv into a command name and the CommandContext to run it with."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from .. import output, refs
from ..models import CommandContext, Flags
from .spec import (
    COMMAND_HELP,
    GLOBAL_ARG_SPECS,
    POSITIONALS,
    SUBPARSER_ARG_SPECS,
    SUPPORTED_OPT_ATTRS,
    VALID_COMMAND_OPTIONS,
)

if TYPE_CHECKING:
    from ..git import GitRunner


def _add_subparser_args(command_subparser: argparse.ArgumentParser, command: str) -> None:
    """Add the flag arguments supported by one command to its subparser."""
    opts = VALID_COMMAND_OPTIONS[command]
    for opt, arg_names, kwargs in SUBPARSER_ARG_SPECS:
        if opt in opts:
            command_subparser.add_argument(*arg_names, **kwargs)


def _add_subparser_positionals(command_subparser: argparse.ArgumentParser, command: str) -> None:
    """Add the positional arguments supported by one command to its subparser."""
    for name, kwargs in POSITIONALS.get(command, []):
        command_subparser.add_argument(name, **kwargs)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and all per-command subparsers."""
    parser = argparse.ArgumentParser(prog='git nested')
    for arg_names, kwargs in GLOBAL_ARG_SPECS:
        parser.add_argument(*arg_names, **kwargs)

    subparsers = parser.add_subparsers(dest='command')
    for command in VALID_COMMAND_OPTIONS:
        command_subparser = subparsers.add_parser(command, help=COMMAND_HELP[command])
        _add_subparser_args(command_subparser, command)
        _add_subparser_positionals(command_subparser, command)

    return parser


def _resolve_positional_args(args: argparse.Namespace) -> tuple[str | None, str | None, str | None]:
    """Resolve upstream/subdir/nested_commit_ref from parsed args.

    Returns:
        tuple: (upstream, subdir, nested_commit_ref)
    """
    upstream = getattr(args, 'upstream', None)
    subdir = getattr(args, 'subdir', None)
    # 'commit's positional is named nested_commit_ref, 'push's is nested_branch --
    # only one of the two is ever present on args, depending on the subcommand.
    nested_commit_ref = getattr(args, 'nested_commit_ref', None) or getattr(args, 'nested_branch', None)

    if upstream and not subdir:
        subdir = refs.guess_subdir(upstream)

    return upstream, subdir, nested_commit_ref


def _supported_and_set(args: argparse.Namespace, opts: list | None, opt: str) -> bool:
    """Check whether opt is valid for the current command and was actually provided."""
    return opt in (opts or []) and getattr(args, opt, None) is not None


def _apply_supported_options(args: argparse.Namespace, flags: Flags) -> None:
    """Copy option values from args to flags when supported by the command and set."""
    opts = VALID_COMMAND_OPTIONS.get(args.command)
    for opt, flag_attr in SUPPORTED_OPT_ATTRS:
        if _supported_and_set(args, opts, opt):
            setattr(flags, flag_attr, getattr(args, opt))


def _validate_message_options(args: argparse.Namespace) -> None:
    """Validate that -m/--file usage is consistent for the current command."""
    opts = VALID_COMMAND_OPTIONS.get(args.command)
    msg_file_set = _supported_and_set(args, opts, 'msg_file')
    if msg_file_set and not Path(args.msg_file).is_file():
        output.error(f"no commit message file at {args.msg_file}")
    if msg_file_set and _supported_and_set(args, opts, 'message'):
        output.error("-m and --file can't be used together")


def _flags_from_args(args: argparse.Namespace) -> Flags:
    """Build a Flags object from parsed args, applying per-command option support rules."""
    flags = Flags()
    flags.all = getattr(args, 'all_flag', False)
    flags.all_deep = getattr(args, 'ALL_flag', False)
    flags.commit = getattr(args, 'commit', False)
    flags.filter = getattr(args, 'filter', [])
    flags.force = getattr(args, 'force', False)
    flags.fetch = getattr(args, 'fetch_flag', False)
    flags.squash = getattr(args, 'squash', False)
    flags.update = getattr(args, 'update', False)
    flags.quiet = getattr(args, 'quiet', False)
    flags.debug = getattr(args, 'debug', False)
    # argparse's `count` action leaves the attribute at None when the flag
    # is absent, and the output layer wants a real count.
    flags.verbose = getattr(args, 'verbose', 0) or 0

    if flags.all_deep:
        flags.all = True

    _apply_supported_options(args, flags)
    _validate_message_options(args)

    return flags


def parse_args(git: GitRunner, args_list: list[str]) -> tuple[str, CommandContext]:
    """Parse command line arguments into a command name and the context to run it with.

    Returns:
        tuple: (command, context). The context's git_tmp/head_commit are left
        unset -- only the caller knows whether the command runs in a repository.
    """
    # Subparsers handle the positional and optional arguments of each command.
    args = build_arg_parser().parse_args(args_list)

    if args.version:
        args.command = 'version'

    if not args.command:
        output.usage_error("no command given; 'git nested --help' lists them")

    upstream, subdir, nested_commit_ref = _resolve_positional_args(args)
    flags = _flags_from_args(args)

    if flags.update and not (flags.branch or flags.remote):
        output.usage_error("--update needs --branch or --remote to have something to update")

    context = CommandContext(
        git=git,
        flags=flags,
        subdir=subdir,
        upstream=upstream,
        nested_commit_ref=nested_commit_ref,
        completion_shell=getattr(args, 'shell', None),
        config_key=getattr(args, 'key', None),
        config_value=getattr(args, 'value', None),
    )
    return args.command, context
