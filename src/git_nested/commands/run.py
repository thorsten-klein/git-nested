"""Running a git command in the worktree of a nested repository."""

from __future__ import annotations

import subprocess

from .. import output, worktree
from ..cli import setup
from ..models import CommandContext


def cmd_run(ctx: CommandContext) -> None:
    """Run `git -C <worktree> <git_args>` for the nested repository's worktree.

    git's own output goes straight to the terminal, unlike everything else
    git-nested runs: the command may be interactive (a pager, `add -p`), so
    it gets the streams as they are, and its exit code becomes ours.
    """
    git = ctx.git
    subdir, _, subref, _ = setup.setup_command(git, 'run', ctx.flags, ctx.subdir, None)

    if not ctx.git_args:
        output.usage_error(f"no git command given; e.g. 'git nested run {subdir.as_posix()} log'")

    branch = f'nested/{subref}'
    path = worktree.find_worktree(git, branch)
    if path is None:
        output.error(
            f"{subdir.as_posix()}: no worktree of {branch} to run in; "
            f"create one with 'git nested branch {subdir.as_posix()}'"
        )

    output.verbose(f"running git in {path.as_posix()}")
    returncode = subprocess.run(['git', '-C', path, *ctx.git_args], check=False).returncode
    if returncode:
        raise SystemExit(returncode)
