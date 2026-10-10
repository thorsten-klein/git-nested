"""The long-form text git-nested prints.

Short messages stay next to the code that emits them -- a one-line result or
error reads better where it happens than behind an indirection. What lives
here is the other kind: the multi-paragraph recovery instructions, where the
wording is the point and the surrounding function is only deciding when to
show it.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

# Written above the YAML of every .gitnested file, so that someone who opens
# one without knowing what it is finds out.
GITNESTED_HEADER = textwrap.dedent("""\
    # This subdirectory is managed by "git nested".
    # Refer to: https://github.com/thorsten-klein/git-nested#readme
    #
    """)


def sync_point_lost(gitnested: Path, subdir: Path, previous: str) -> str:
    """What to do when the recorded parent is no longer an ancestor of HEAD.

    The parent is the last commit at which the nested subdir and its upstream
    were identical; everything git-nested reconstructs is measured from it. A
    rebase that rewrote it leaves nothing to measure from, so the only way out
    is to point the file at the rewritten commit by hand.
    """
    # rstrip: the search for the previous sync point can come up empty, and
    # 'parent:' on its own is still the right thing to write -- with a
    # trailing space it would not be.
    setting = f"parent: {previous}".rstrip()
    return textwrap.dedent(f"""\
        the recorded sync point is no longer an ancestor of HEAD

        The sync point is the commit at which {subdir.as_posix()} and its upstream were last
        equal. A rebase usually rewrites it. To recover, set

            {setting}

        in {gitnested.as_posix()}, then check the result with 'git nested branch {subdir.as_posix()}'.""")


def worktree_exists(subdir: Path, worktree_path: str | None, prunable: bool) -> str:
    """What to do about a leftover nested/<subdir> worktree standing in the way.

    `prunable` picks the ending: with a .gitnested file present, `git nested
    clean` knows about the worktree and can take it away; without one it does
    not, and the two git commands that do it by hand are spelled out instead.
    """
    remedy = "  git nested clean\n" if prunable else f"  rm -rf {worktree_path}\n  git worktree prune\n"
    return (
        f"{subdir.as_posix()}: a worktree is already checked out on nested/{subdir.as_posix()}\n\n"
        f"Pass --force to work around the check, or remove the worktree:\n\n{remedy}"
    )


def pull_conflict_help(subdir: Path, worktree: Path, method: str, message_file: str | None, subref: str) -> str:
    """How to finish a pull by hand after its merge or rebase hit conflicts.

    git-nested has already left the half-finished operation in a worktree of
    its own, so the recovery is an ordinary conflict resolution followed by
    handing the result back -- which is what the numbered steps spell out.
    """
    resume = "git rebase --continue" if method == 'rebase' else "git commit"
    commit = (
        f"git nested commit --file={message_file} {subdir.as_posix()}"
        if message_file
        else f"git nested commit {subdir.as_posix()}"
    )
    text = textwrap.dedent(f"""\

        The conflicts are in a worktree of their own at {worktree.as_posix()}.
        Resolve them there and hand the result back:

          1. cd {worktree.as_posix()}
          2. resolve the conflicts ('git status' lists them)
          3. 'git add' each file you resolved
          4. {resume}
          5. if more conflicts appear, go back to step 2
          6. cd {Path.cwd()}
          7. {commit}
        """)
    if method == 'rebase':
        text += textwrap.dedent(f"""
            Your local changes can then be pushed without redoing the rebase:

              git nested push {subdir.as_posix()} nested/{subref}
            """)
    return text + textwrap.dedent(f"""
        See 'git help {method}' for the conflict resolution itself.

        To throw the pull away and go back to where you started instead:

          git nested clean {subdir.as_posix()}
        """)
