"""Turning argv into a command name, a Flags object and its positionals."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import output, refs
from ..models import Flags
from .spec import POSITIONALS, SUBPARSER_ARG_SPECS, SUPPORTED_OPT_ATTRS, VALID_COMMAND_OPTIONS


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
    parser.add_argument('--version', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-v', '--verbose', action='count')

    subparsers = parser.add_subparsers(dest='command')
    for command in VALID_COMMAND_OPTIONS:
        command_subparser = subparsers.add_parser(command)
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
        output.error(f"Commit msg file at {args.msg_file} not found")
    if msg_file_set and _supported_and_set(args, opts, 'message'):
        output.error("fatal: options '-m' and '--file' cannot be used together")


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
    flags.verbose = getattr(args, 'verbose', 0)

    if flags.all_deep:
        flags.all = True

    _apply_supported_options(args, flags)
    _validate_message_options(args)

    return flags


def parse_args(args_list: list[str]) -> tuple[str, Flags, str | None, str | None, str | None]:
    """Parse command line arguments.

    Returns:
        tuple: (command, flags, subdir, upstream, nested_commit_ref)
    """
    # Subparsers handle the positional and optional arguments of each command.
    args = build_arg_parser().parse_args(args_list)

    if args.version:
        args.command = 'version'

    if not args.command:
        output.usage_error("Missing command")

    upstream, subdir, nested_commit_ref = _resolve_positional_args(args)
    flags = _flags_from_args(args)

    if flags.update and not (flags.branch or flags.remote):
        output.usage_error("Can't use '--update' without '--branch' or '--remote'.")

    return args.command, flags, subdir, upstream, nested_commit_ref
