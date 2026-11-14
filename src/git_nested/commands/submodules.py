"""Turn all submodules into nested repos, and keep them in step with upstream.

The root repo stays a normal clone of the upstream superproject. Its
submodules are nested repos.

- init: nest every submodule, or the ones named, one commit each.
- update: merge an upstream commit, drop the gitlinks it brings, then
  update the nested repos to match. One commit per nested repo.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from .. import checks, configio, content, output, refs, submodules, worktree
from ..constants import GITNESTED_FILENAME
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import clone, commit, config, init, pull

_GITMODULES = '.gitmodules'
_GITATTRIBUTES = '.gitattributes'
# Where a merge that stopped keeps what --continue needs. Written once.
_STATE_FILE = 'nested-submodules-update.json'
_MAX_ARGS = {'init': 0, 'update': 1}
# What init left out, in .gitmodules: update leaves new submodules there out too
_ONLY, _IGNORE = 'nested.only', 'nested.ignore'
# The lines git merge-file marks a conflict with
_CONFLICT_MARKER = re.compile(r'^(<{7}|={7}|>{7})', re.MULTILINE)
# A SHA-1 or SHA-256 commit id
_COMMIT_ID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')


def cmd_submodules(ctx: CommandContext) -> None:
    """Run `submodules init` or `submodules update`."""
    action = ctx.submodules_action or ''
    args = ctx.submodules_args or []
    _check_args(ctx.flags, action, args)
    if action == 'init':
        checks.check_worktree_clean(ctx.git, 'init')
        _nest_all(ctx.git, ctx.flags)
    else:
        _update(ctx, args)


def _given(flags: Flags) -> list[str]:
    """The options of update that were given."""
    options = {
        '--continue': flags.resume,
        '--abort': flags.abort,
        '--dry-run': flags.dry_run,
        '--single-commit': flags.single_commit,
    }
    return [name for name, on in options.items() if on]


def _check_args(flags: Flags, action: str, args: list[str]) -> None:
    given = _given(flags)
    if len(args) > _MAX_ARGS[action]:
        output.usage_error(f"too many arguments for 'submodules {action}'")
    _check_init_options(flags, action)
    if action == 'init' and given:
        output.usage_error(f"{given[0]} only works with 'submodules update'")
    stop = next((name for name in given if name in ('--continue', '--abort')), None)
    if stop and (args or len(given) > 1):
        output.usage_error(f"{stop} takes no other arguments, and no --dry-run or --single-commit")


def _check_init_options(flags: Flags, action: str) -> None:
    """The options of init: only with init, and not --only with --ignore."""
    if flags.only and flags.ignore:
        output.usage_error("--only and --ignore can't be used together")
    init_only = {
        '--only': flags.only,
        '--ignore': flags.ignore,
        '--resolve-relative': flags.resolve_relative,
        '--recursive': flags.recursive,
    }
    picked = next((name for name, value in init_only.items() if value), None)
    if picked and action != 'init':
        output.usage_error(f"{picked} only works with 'submodules init'")


# ============================================================================
# init
# ============================================================================


def _nest_all(git: GitRunner, flags: Flags) -> None:
    """Nest each submodule at the commit it pins. With --recursive, their submodules too.

    With --only, only the submodules at or below its paths. With --ignore,
    all others. The rest stay submodules. Relative submodule urls need
    --resolve-relative.
    """
    links = _selected(git, flags)
    if not links:
        output.say("no submodules to nest")
        return
    if not flags.resolve_relative:
        _refuse_relative_urls(git, links)
    _keep_selection(git, flags)
    # .gitnested keeps the choice, for update
    choice = cast('Flags', replace(flags, submodules='nest' if flags.recursive else 'keep', hint='--recursive'))
    for path in links:
        init.init_from_submodule(git, choice, Path(path), flags.resolve_relative)


def _selected(git: GitRunner, flags: Flags) -> list[str]:
    """The submodules that --only and --ignore leave in. Not the ones git skips: `update = none`."""
    gitmodules = Path(_GITMODULES)
    links = [
        path for path, _ in submodules.gitlinks(git, Path()) if not submodules.skipped_by_git(git, gitmodules, path)
    ]
    if flags.only:
        return _below_any(links, flags.only)
    skipped = set(_below_any(links, flags.ignore)) if flags.ignore else set()
    return [link for link in links if link not in skipped]


def _keep_selection(git: GitRunner, flags: Flags) -> None:
    """Write --only and --ignore into .gitmodules. It is part of the first commit."""
    if not (flags.only or flags.ignore):
        return
    only = [posixpath.normpath(Path(path).as_posix()) for path in flags.only or []]
    ignore = [posixpath.normpath(Path(path).as_posix()) for path in flags.ignore or []]
    _add_selection(git, Path(_GITMODULES), (only, ignore))
    git.run(['add', '--', _GITMODULES])


def _add_selection(git: GitRunner, file: Path, selection: tuple[list[str], list[str]]) -> None:
    """Add the --only and --ignore paths of `selection` to `file`."""
    for key, paths in zip((_ONLY, _IGNORE), selection, strict=True):
        for path in filter(None, paths):
            git.run(['config', '-f', file, '--add', key, path])


def _selection_at(git: GitRunner, rev: str) -> tuple[list[str], list[str]]:
    """The --only and --ignore paths that .gitmodules of `rev` keeps."""
    text = git.check_output(['show', f'{rev}:{_GITMODULES}'], may_fail=True)
    return cast(
        'tuple[list[str], list[str]]',
        tuple(
            git.check_output(['config', '-f', '-', '--get-all', key], may_fail=True, input=text).split('\n')
            if text
            else []
            for key in (_ONLY, _IGNORE)
        ),
    )


def _left_out(path: str, only: list[str], ignore: list[str]) -> bool:
    """Whether init's --only or --ignore leaves `path` out."""
    only, ignore = [p for p in only if p], [p for p in ignore if p]
    return (bool(only) and not any(_below(path, p) for p in only)) or any(_below(path, p) for p in ignore)


def _kept(git: GitRunner, ours: str, target: str) -> set[str]:
    """The submodules of `target` that stay submodules.

    The ones `ours` has as a submodule, also under a new path, and also
    inside nested repos. The ones git skips: `update = none`. And new ones
    that init's --only or --ignore leaves out.
    """
    ours_links = submodules.gitlinks_at(git, ours)
    names = {name for path, (name, _) in _modules_at(git, ours).items() if path in ours_links}
    selection = _selection_at(git, ours)
    target_modules = _modules_at(git, target)
    kept = set(ours_links) | _skipped_by_git_at(git, target)
    for path in submodules.gitlinks_at(git, target):
        if _stays(path, target_modules.get(path, ('', ''))[0], names, selection):
            kept.add(path)
    return kept


def _stays(path: str, name: str, names: set[str], selection: tuple[list[str], list[str]]) -> bool:
    """Whether the submodule at `path` stays one: its name is in `names`, or init left it out."""
    if name and name in names:
        return True
    return not _is_nested(path) and _left_out(path, *selection)


def _refuse_relative_urls(git: GitRunner, links: list[str]) -> None:
    """Fail if a submodule in `links` has a relative url.

    It is relative to the superproject's url. In a fork that is not origin.
    So git-nested does not guess.
    """
    relative = [
        path
        for path in links
        if (found := submodules.entry(git, Path(_GITMODULES), path)) and submodules.is_relative(found[1])
    ]
    if relative:
        raise GitNestedError(
            f"these submodules have a relative url: {', '.join(relative)}\n"
            "Use --resolve-relative <url> to say what they are relative to. "
            "That is the url of the project they come from."
        )


def _below_any(links: list[str], paths: list[str]) -> list[str]:
    """The submodules in `links` at or below one of `paths`. Each path must hit one."""
    wanted = [posixpath.normpath(Path(path).as_posix()) for path in paths]
    for path, given in zip(wanted, paths, strict=True):
        if not any(_below(link, path) for link in links):
            raise GitNestedError(f"{given}: no submodule there")
    return [link for link in links if any(_below(link, path) for path in wanted)]


def _below(link: str, path: str) -> bool:
    """Whether `link` is `path` or below it."""
    return path in ('.', link) or link.startswith(f'{path}/')


# ============================================================================
# update
# ============================================================================


def _update(ctx: CommandContext, args: list[str]) -> None:
    git = ctx.git
    state_file = Path(git.check_output(['rev-parse', '--git-dir'])) / _STATE_FILE
    if ctx.flags.abort:
        _abort(ctx, state_file)
        return
    state = _resume(git, state_file) if ctx.flags.resume else _start(ctx, state_file, args)
    if state is None:
        return
    _finish_merge(git, ctx.flags)
    _run_steps(ctx, state)
    if state['single']:
        _fold_into_merge(git, ctx.flags, _merge_commit(git, state['target']))
    state_file.unlink()


def _run_steps(ctx: CommandContext, state: dict[str, str]) -> None:
    """Do the plan. With --continue, first finish a submodule pull that stopped."""
    # Each step makes its own commit. --single-commit folds them in at the end.
    steps_ctx = cast('CommandContext', replace(ctx, flags=replace(ctx.flags, single_commit=False)))
    for step in _plan(ctx.git, state):
        if step.what == 'pull' and ctx.flags.resume:
            _finish_pending(steps_ctx, step.path)
        _APPLY[step.what](steps_ctx, step)


def _merge_commit(git: GitRunner, target: str) -> str:
    """The merge commit of `target` on this branch."""
    log = git.check_output(['log', '--first-parent', '--merges', '--format=%H %P', f'{target}..HEAD'])
    for line in log.splitlines():
        commit_id, *parents = line.split()
        if target in parents[1:]:
            return commit_id
    raise GitNestedError(f"the merge commit of {target} is gone")


def _abort(ctx: CommandContext, state_file: Path) -> None:
    """Throw away a merge that stopped, and a nested repo's pull that stopped. Nested repos that it updated stay."""
    git = ctx.git
    if not state_file.is_file():
        raise GitNestedError("there is nothing to abort")
    if _merging(git):
        git.run(['merge', '--abort'])
    _drop_stopped_pulls(git, ctx.tmp)
    state_file.unlink()
    output.say(
        "aborted. The nested repos that were updated stay. 'git nested submodules update <commit>' updates the rest."
    )


def _drop_stopped_pulls(git: GitRunner, tmp: Path) -> None:
    """Remove the worktrees and branches of the nested repos whose pull stopped on conflicts."""
    for path, _ in worktree.list_worktrees(git):
        try:
            branch = path.resolve().relative_to(tmp.resolve()).as_posix()
        except ValueError:
            continue
        if worktree.stopped(git, path):
            worktree.delete_branch(git, branch, tmp)


def _resume(git: GitRunner, state_file: Path) -> dict[str, str]:
    """The state of the merge that stopped. The merge must still be there, or be done."""
    if not state_file.is_file():
        raise GitNestedError("there is nothing to continue")
    state = _load(state_file)
    if not _merging(git) and not _is_ancestor(git, state['target'], 'HEAD'):
        raise GitNestedError("The merge of upstream is gone. Start over with 'git nested submodules update --abort'.")
    return state


def _load(state_file: Path) -> dict[str, str]:
    """Read the state file, and check what it says."""
    broken = GitNestedError(f"{state_file.as_posix()} is broken. Start over with --abort.")
    try:
        raw = json.loads(state_file.read_text())
        state = {
            'base': str(raw['base']),
            'target': str(raw['target']),
            'url': str(raw['url']),
            'single': 'yes' if raw.get('single') else '',
        }
    except (ValueError, KeyError, TypeError):
        raise broken from None
    if not all(_COMMIT_ID.fullmatch(state[key]) for key in ('base', 'target')):
        raise broken
    return state


def _start(ctx: CommandContext, state_file: Path, args: list[str]) -> dict[str, str] | None:
    """Start the merge. None if there is nothing to merge, or on --dry-run."""
    git = ctx.git
    if state_file.is_file():
        raise GitNestedError(
            "A 'submodules update' stopped before. Finish it with 'git nested submodules update --continue'."
        )
    if not args:
        _needs_a_commit(git)
    checks.check_worktree_clean(git, 'update')
    ref, remote_url, label = _resolve(git, args)
    target = git.check_output(['rev-parse', f'{ref}^{{commit}}'])
    if _is_ancestor(git, target, 'HEAD'):
        return _catch_up(ctx, state_file, {'base': target, 'target': target, 'url': remote_url, 'single': ''}, label)
    base = git.check_output(['merge-base', 'HEAD', target], may_fail=True)
    if not base:
        raise GitNestedError(f"{label} has no history in common with this branch")
    state = {
        'base': base,
        'target': target,
        'url': remote_url,
        'single': 'yes' if ctx.flags.single_commit else '',
    }
    if ctx.flags.dry_run:
        count = git.check_output(['rev-list', '--count', f'HEAD..{target}'])
        _show_plan(git, state, f"would merge {count} commits of {label}")
        return None
    _start_merge(git, ref)
    # Only now: --continue needs a merge to continue
    state_file.write_text(json.dumps(state))
    _drop_gitlinks(git, state)
    _merge_gitattributes(git, state)
    return state


def _catch_up(ctx: CommandContext, state_file: Path, state: dict[str, str], label: str) -> dict[str, str] | None:
    """The target is merged. Bring the nested repos to its gitlinks, if some are not there yet.

    For example after --abort. Only for the upstream commit of the last
    merge, so an older one does not take the nested repos back.
    """
    git = ctx.git
    if ctx.flags.single_commit:
        output.usage_error("--single-commit only works when 'submodules update' merges")
    last = git.check_output(['log', '-1', '--first-parent', '--merges', '--format=%P', 'HEAD']).split()
    if state['target'] not in last[1:] or all(step.what == 'skip' for step in _plan(git, state)):
        output.say(f"already up to date with {label}")
        return None
    if ctx.flags.dry_run:
        _show_plan(git, state, f"would update the nested repos to {label}")
        return None
    state_file.write_text(json.dumps(state))
    return state


def _needs_a_commit(git: GitRunner) -> None:
    """Fail: update needs a commit. Say what to do about a git merge that is in progress."""
    if _merging(git):
        raise GitNestedError(
            "a git merge is in progress. Run 'git merge --abort'. "
            "Then run 'git nested submodules update <commit>' instead."
        )
    output.usage_error("'submodules update' needs a commit, for example upstream/main")


def _current_branch(git: GitRunner) -> str:
    branch = git.check_output(['symbolic-ref', '--short', '-q', 'HEAD'], may_fail=True)
    if not branch:
        raise GitNestedError("HEAD is detached. Check out a branch first.")
    return branch


def _resolve(git: GitRunner, args: list[str]) -> tuple[str, str, str]:
    """The commit to merge, as given. Return it, the url of its remote, and a name to show."""
    _current_branch(git)
    ref = args[0]
    if not _is_commit(git, ref):
        raise GitNestedError(f"{ref}: no such commit. Fetch it first.")
    return ref, _remote_url_of(git, ref), ref


def _remote_url_of(git: GitRunner, ref: str) -> str:
    """The url of the remote that `ref` comes from. Else of the current branch's remote, else of origin."""
    full = git.check_output(['rev-parse', '--symbolic-full-name', ref], may_fail=True)
    remote = ''
    if full.startswith('refs/remotes/'):
        rest = full.removeprefix('refs/remotes/')
        # A remote name may hold a slash. The longest match wins.
        names = sorted(git.check_output(['remote']).split(), key=len, reverse=True)
        remote = next((name for name in names if rest.startswith(f'{name}/')), '')
    if not remote:
        branch = _current_branch(git)
        remote = git.check_output(['config', f'branch.{branch}.remote'], may_fail=True) or 'origin'
    return git.check_output(['remote', 'get-url', remote], may_fail=True)


def _is_commit(git: GitRunner, ref: str) -> bool:
    return git.run(['rev-parse', '-q', '--verify', f'{ref}^{{commit}}'], may_fail=True).returncode == 0


def _is_ancestor(git: GitRunner, commit: str, of: str) -> bool:
    return git.run(['merge-base', '--is-ancestor', commit, of], may_fail=True).returncode == 0


def _merging(git: GitRunner) -> bool:
    return git.run(['rev-parse', '-q', '--verify', 'MERGE_HEAD'], may_fail=True).returncode == 0


def _start_merge(git: GitRunner, ref: str) -> None:
    result = git.run(['merge', '-q', '--no-commit', '--no-ff', ref], may_fail=True)
    if not _merging(git):
        raise GitNestedError(f"the merge of {ref} failed:\n{result.stdout}{result.stderr}")


def _drop_gitlinks(git: GitRunner, state: dict[str, str]) -> None:
    """Keep the nested folders. Drop the gitlinks that the merge brought.

    The kept submodules stay, see _kept. .gitmodules is merged for them only.
    """
    kept = _kept(git, 'HEAD', state['target'])
    for entry in git.check_output(['ls-files', '-s', '-z']).split('\0'):
        meta, _, path = entry.partition('\t')
        if meta.startswith('160000 ') and path not in kept:
            git.run(['update-index', '--force-remove', '--', path])
            _remove_if_empty(Path(path))
    _merge_gitmodules(git, state, kept)


def _merge_gitmodules(git: GitRunner, state: dict[str, str], kept: set[str]) -> None:
    """Merge .gitmodules of base, HEAD and target, with the kept submodules only.

    So upstream's changes to them come in, and yours stay. A conflict stays
    in the file, like any merge conflict.
    """
    names = {name for path, (name, _) in _modules_at(git, state['target']).items() if path in kept}
    names |= {name for name, _ in _modules_at(git, 'HEAD').values()}
    selection = _selection_at(git, 'HEAD')
    scratch = Path(git.check_output(['rev-parse', '--git-dir'])) / 'nested-gitmodules'
    scratch.mkdir(exist_ok=True)
    files = [
        _kept_modules(git, rev, names, selection, scratch / rev) for rev in ('HEAD', state['base'], state['target'])
    ]
    merged = git.run(['merge-file', '-p', '-L', 'HEAD', '-L', 'base', '-L', 'upstream', *files], may_fail=True)
    git.run(['update-index', '--force-remove', '--', _GITMODULES])
    Path(_GITMODULES).unlink(missing_ok=True)
    if merged.stdout.strip():
        # Markers as comments: git reads .gitmodules as config, and a marker breaks every git command
        text = _CONFLICT_MARKER.sub(r'# \1', merged.stdout)
        Path(_GITMODULES).write_text(text, encoding='utf-8', newline='\n')
        _stage_merged(git, files, conflict=merged.returncode != 0)
    for file in files:
        Path(file).unlink()


def _stage_merged(git: GitRunner, files: list[str], conflict: bool) -> None:
    """Stage the merged .gitmodules. A conflict gets stages 1-3, so git status and --continue know it.

    `files` are the versions of HEAD, base and target.
    """
    if not conflict:
        git.run(['add', '--', _GITMODULES])
        return
    blobs = [git.check_output(['hash-object', '-w', file]) for file in (files[1], files[0], files[2])]
    # -z: on Windows, text mode turns \n into \r\n, and git would read the path as '.gitmodules\r'
    info = ''.join(f'100644 {blob} {stage}\t{_GITMODULES}\0' for stage, blob in enumerate(blobs, start=1))
    git.run(['update-index', '-z', '--index-info'], input=info)


def _kept_modules(git: GitRunner, rev: str, names: set[str], selection: tuple[list[str], list[str]], file: Path) -> str:
    """Write .gitmodules of `rev` to `file`, with only the submodules in `names`, and `selection`."""
    text = git.check_output(['show', f'{rev}:{_GITMODULES}'], may_fail=True)
    file.write_text(f'{text}\n' if text else '', encoding='utf-8', newline='\n')
    others = {name for name, _ in _modules_at(git, rev).values()} - names
    for section in [*(f'submodule.{name}' for name in others), 'nested']:
        git.run(['config', '-f', file, '--remove-section', section], may_fail=True)
    # No section left: the same empty file for each side, so they do not differ by a blank line
    if not file.read_text(encoding='utf-8').strip():
        file.write_text('', encoding='utf-8')
    _add_selection(git, file, selection)
    return file.as_posix()


def _merge_gitattributes(git: GitRunner, state: dict[str, str]) -> None:
    """Merge .gitattributes again without git-nested's block, then put the block back at the end.

    git-nested owns the block. Upstream adds its rules at the end too, so
    a plain merge stops there. A real conflict in the other rules stays.
    """
    if _GITATTRIBUTES not in _conflicts(git):
        return
    files, block = _attributes_without_block(git, state)
    merged = git.run(['merge-file', '-p', *files], may_fail=True)
    for file in files:
        Path(file).unlink()
    if merged.returncode == 0:
        rules = merged.stdout if merged.stdout.endswith('\n') or not merged.stdout else f'{merged.stdout}\n'
        Path(_GITATTRIBUTES).write_text(rules + block, encoding='utf-8', newline='\n')
        git.run(['add', '--', _GITATTRIBUTES])


def _attributes_without_block(git: GitRunner, state: dict[str, str]) -> tuple[list[str], str]:
    """.gitattributes of HEAD, base and target without git-nested's block, in files. Also the block of HEAD."""
    scratch = Path(git.check_output(['rev-parse', '--git-dir'])) / 'nested-gitattributes'
    scratch.mkdir(exist_ok=True)
    files, blocks = [], []
    for rev in ('HEAD', state['base'], state['target']):
        text = git.check_output(['show', f'{rev}:{_GITATTRIBUTES}'], may_fail=True)
        rest, block = content.split_keep_block(f'{text}\n' if text else '')
        (scratch / rev).write_text(rest, encoding='utf-8', newline='\n')
        files.append((scratch / rev).as_posix())
        blocks.append(block)
    return files, blocks[0]


def _conflicts(git: GitRunner, cwd: Path | None = None) -> list[str]:
    """The files with conflicts left, in the worktree at `cwd` or here."""
    return sorted(set(git.check_output(['diff', '--name-only', '--diff-filter=U'], cwd=cwd).split('\n')) - {''})


def _remove_if_empty(path: Path) -> None:
    """A gitlink leaves an empty folder behind."""
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


def _finish_merge(git: GitRunner, flags: Flags) -> None:
    """Commit the merge. Stop if there are conflicts left."""
    if not _merging(git):
        return
    conflicts = _conflicts(git)
    if conflicts:
        raise GitNestedError(
            f"the merge has conflicts in: {', '.join(conflicts)}\n"
            "Fix them and 'git add' them. Then run 'git nested submodules update --continue'."
        )
    git.run(['commit', '-q', '--no-edit', *_signing(flags)])


def _signing(flags: Flags) -> list[str]:
    return [*(['--signoff'] if flags.signoff else []), *(['-S'] if flags.gpg_sign else [])]


def _fold_into_merge(git: GitRunner, flags: Flags, merge: str) -> None:
    """Put the submodule commits into the merge commit. Its message lists them."""
    if git.check_output(['rev-parse', 'HEAD']) == merge:
        return
    message = git.check_output(['log', '-1', '--format=%B', merge])
    changes = git.check_output(['log', '--reverse', '--format=- %s', f'{merge}..HEAD'])
    git.run(['reset', '-q', '--soft', merge])
    git.run(['commit', '-q', '--amend', '--no-verify', '-F', '-', *_signing(flags)], input=f"{message}\n\n{changes}\n")


def _finish_stopped(git: GitRunner, path: str, tree: Path) -> None:
    """Finish the merge, `git am` or rebase that stopped in the worktree of `path`."""
    if git.run(['rev-parse', '-q', '--verify', 'MERGE_HEAD'], cwd=tree, may_fail=True).returncode == 0:
        finish = ['commit', '-q', '--no-edit']
    elif Path(tree, git.check_output(['rev-parse', '--git-path', 'rebase-apply'], cwd=tree)).is_dir():
        # A pull with patches applies them with git am
        finish = ['am', '--continue']
    elif Path(tree, git.check_output(['rev-parse', '--git-path', 'rebase-merge'], cwd=tree)).is_dir():
        finish = ['rebase', '--continue']
    else:
        return
    left = _conflicts(git, tree)
    if left:
        raise GitNestedError(f"{path}: fix the conflicts in {tree.as_posix()} first: {', '.join(left)}")
    git.run(['-c', 'core.editor=true', *finish], cwd=tree)


def _finish_pending(ctx: CommandContext, path: str) -> None:
    """Commit the submodule pull that stopped on conflicts, if you have not done it yet."""
    git = ctx.git
    branch = refs.nested_branch(git, refs.sanitize_subref(path))
    # A rebase that stopped has no branch checked out
    tree = worktree.find_worktree(git, branch) or ctx.tmp / branch
    if not tree.is_dir():
        return
    _finish_stopped(git, path, tree)
    inner = Flags(
        gpg_sign=ctx.flags.gpg_sign, signoff=ctx.flags.signoff, quiet=ctx.flags.quiet, verbose=ctx.flags.verbose
    )
    head = git.check_output(['rev-parse', 'HEAD'])
    commit.cmd_commit(
        cast(
            'CommandContext',
            replace(ctx, flags=inner, subdir=Path(path), upstream=None, nested_commit_ref=None, head_commit=head),
        )
    )


# ============================================================================
# The plan: what changes in the nested repos
# ============================================================================


@dataclass
class _Step:
    """One change to one nested repo.

    `what` is move, remove, nest, pull, url or skip. `to` is the new path of
    a move, or the pin of a nest or pull. `url` is the url to nest from, or
    a new url. `note` is the reason to skip, or a warning.
    """

    what: str
    path: str
    to: str = ''
    url: str | None = None
    note: str = ''

    def text(self) -> str:
        """What the step does, in a few words."""
        return {
            'move': f"move to {self.to}",
            'remove': "remove",
            'nest': f"nest at {self.to[:12]}",
            'pull': f"pull to {self.to[:12]}" + (f" from {self.url}" if self.url else ''),
            'url': f"set remote to {self.url}",
            'skip': "stay as it is",
        }[self.what]


def _module_fields(git: GitRunner, commit: str) -> dict[str, dict[str, str]]:
    """The .gitmodules of `commit`, as {name: {field: value}}, with path, url and update."""
    text = git.check_output(['show', f'{commit}:{_GITMODULES}'], may_fail=True)
    fields: dict[str, dict[str, str]] = {}
    lines = git.check_output(
        ['config', '-f', '-', '--get-regexp', r'^submodule\..*\.(path|url|update)$'], may_fail=True, input=text
    )
    for line in lines.splitlines():
        key, _, value = line.partition(' ')
        name, _, field = key.removeprefix('submodule.').rpartition('.')
        fields.setdefault(name, {})[field] = value
    return fields


def _modules_at(git: GitRunner, commit: str) -> dict[str, tuple[str, str]]:
    """The .gitmodules of `commit`, as {path: (name, url)}."""
    fields = _module_fields(git, commit)
    return {f['path']: (name, f['url']) for name, f in fields.items() if 'path' in f and 'url' in f}


def _skipped_by_git_at(git: GitRunner, commit: str) -> set[str]:
    """The submodules that .gitmodules of `commit` gives `update = none`. git does not check those out."""
    return {f['path'] for f in _module_fields(git, commit).values() if 'path' in f and f.get('update') == 'none'}


def _is_nested(path: str | Path) -> bool:
    return (Path(path) / GITNESTED_FILENAME).is_file()


def _plan(git: GitRunner, state: dict[str, str]) -> list[_Step]:
    """What to do so that the nested repos match the submodules of the target."""
    old, new = submodules.gitlinks_at(git, state['base']), submodules.gitlinks_at(git, state['target'])
    old_modules, new_modules = _modules_at(git, state['base']), _modules_at(git, state['target'])
    steps, moved = _plan_gone(git, old, new, old_modules, new_modules)
    kept = _kept(git, 'HEAD', state['target'])
    old_url_of = dict(old_modules.values())
    for path, pin in sorted(new.items()):
        if path not in kept:
            steps.append(_plan_one(path, pin, new_modules.get(path, ('', '')), old_url_of, state, moved))
    return steps


def _plan_gone(
    git: GitRunner,
    old: dict[str, str],
    new: dict[str, str],
    old_modules: dict[str, tuple[str, str]],
    new_modules: dict[str, tuple[str, str]],
) -> tuple[list[_Step], dict[str, str]]:
    """What to do for the nested repos that upstream moved or removed. Also {new path: old path}."""
    # A move keeps the submodule's name in .gitmodules
    new_path_of = {name: path for path, (name, _) in new_modules.items() if path not in old}
    steps = []
    moved: dict[str, str] = {}
    for path in sorted(p for p in set(old) - set(new) if _is_nested(p)):
        step = _plan_gone_one(git, path, new_path_of.get(old_modules.get(path, ('', ''))[0]))
        if step.what == 'move':
            moved[step.to] = path
        steps.append(step)
    return steps, moved


def _plan_gone_one(git: GitRunner, path: str, to: str | None) -> _Step:
    """Move the nested repo at `path` to `to`, or remove it if there is no `to`."""
    if to and Path(to).exists():
        return _Step('skip', path, note=f"upstream moved it to {to}, but that path is taken. It stays")
    if to:
        return _Step('move', path, to=to)
    note = "your changes in it go too. They stay in the history" if _has_local_changes(git, path) else ''
    return _Step('remove', path, note=note)


def _plan_one(
    path: str,
    pin: str,
    module: tuple[str, str],
    old_url_of: dict[str, str],
    state: dict[str, str],
    moved: dict[str, str],
) -> _Step:
    """What to do for the submodule at `path` that upstream pins at `pin`."""
    name, url = module
    if not url:
        return _Step('skip', path, note=".gitmodules has no url for it, so it stays as it is")
    resolved = submodules.resolve(url, state['url'])
    # Compare urls as .gitmodules has them. Resolved, a relative url depends on the remote.
    new_url = resolved if old_url_of.get(name, url) != url else None
    here = Path(moved.get(path, path))
    if not _is_nested(here):
        if here.is_dir() and any(here.iterdir()):
            return _Step('skip', path, note="the path is taken, so the submodule stays empty")
        return _Step('nest', path, to=pin, url=resolved)
    return _plan_nested(path, pin, here, new_url)


def _plan_nested(path: str, pin: str, here: Path, new_url: str | None) -> _Step:
    """What to do for a submodule that is nested already, at `here`."""
    current = NestedConfig.from_file(here / GITNESTED_FILENAME)
    if current.pin and current.commit != pin:
        return _Step('skip', path, note=f"it has the pin {current.pin}, so it stays. Upstream pins {pin[:12]}")
    if current.commit != pin:
        return _Step('pull', path, to=pin, url=new_url)
    if new_url and current.remote != new_url:
        return _Step('url', path, url=new_url)
    return _Step('skip', path, note='')


def _has_local_changes(git: GitRunner, path: str) -> bool:
    """Whether path differs from the upstream commit it records. False if that can't be told."""
    commit = NestedConfig.from_file(Path(path) / GITNESTED_FILENAME).commit
    try:
        return not content.matches_upstream(git, Path(path), commit)
    except GitNestedError:
        return False


def _show_plan(git: GitRunner, state: dict[str, str], heading: str) -> None:
    output.say(heading)
    for step in _plan(git, state):
        for line in _step_lines(git, step):
            output.say(line)


def _step_lines(git: GitRunner, step: _Step) -> list[str]:
    """What --dry-run shows for `step`. For a pull, also what it does deeper down."""
    lines = []
    if step.what != 'skip' or step.note:
        lines.append(f"{step.path}: would {step.text()}" + (f" ({step.note})" if step.note else ''))
    if step.what == 'pull':
        lines += _deeper(git, step.path, step.to, step.url)
    return lines


def _deeper(git: GitRunner, path: str, pin: str, url: str | None) -> list[str]:
    """What a pull of the nested repo at `path` to `pin` would do to the nested repos inside it."""
    config = NestedConfig.from_file(Path(path) / GITNESTED_FILENAME)
    if config.submodules == 'keep':
        return []
    _have_commit(git, url or config.remote, pin)
    lines = []
    for relative, inner_pin in sorted(submodules.gitlinks_at(git, pin).items()):
        lines += _deeper_one(git, f'{path}/{relative}', inner_pin)
    gone = set(submodules.gitlinks_at(git, config.commit)) - set(submodules.gitlinks_at(git, pin))
    lines += [f"{path}/{relative}: would remove" for relative in sorted(gone) if _is_nested(f'{path}/{relative}')]
    return lines


def _deeper_one(git: GitRunner, path: str, pin: str) -> list[str]:
    """What a pull would do to the inner submodule at `path`, which its parent now pins at `pin`."""
    if not _is_nested(path):
        return [] if Path(path).exists() else [f"{path}: would nest at {pin[:12]}"]
    if NestedConfig.from_file(Path(path) / GITNESTED_FILENAME).commit == pin:
        return []
    return [f"{path}: would pull to {pin[:12]}", *_deeper(git, path, pin, None)]


def _have_commit(git: GitRunner, remote: str, commit: str) -> None:
    """Fetch `commit` from `remote`, unless it is here already."""
    if git.run(['cat-file', '-e', f'{commit}^{{commit}}'], may_fail=True).returncode:
        git.network(['fetch', '--no-tags', '--quiet', remote, commit], f"fetching {commit[:12]} from {remote}")


def _apply_skip(_ctx: CommandContext, step: _Step) -> None:
    if step.note:
        output.warn(f"{step.path}: {step.note}")


def _apply_move(ctx: CommandContext, step: _Step) -> None:
    Path(step.to).parent.mkdir(parents=True, exist_ok=True)
    ctx.git.run(['mv', '--', step.path, step.to])
    message = f"git nested submodules: move {step.path} to {step.to}"
    content.commit_gitnested_update(ctx.git, ctx.flags, Path(step.to), message)
    output.say(f"{step.path}: moved to {step.to}")


def _apply_remove(ctx: CommandContext, step: _Step) -> None:
    if step.note:
        output.warn(f"{step.path}: {step.note}")
    ctx.git.run(['rm', '-r', '-q', '--', step.path])
    content.commit_gitnested_update(ctx.git, ctx.flags, Path(step.path), f"git nested submodules: remove {step.path}")
    output.say(f"{step.path}: removed, upstream dropped it")


def _apply_nest(ctx: CommandContext, step: _Step) -> None:
    flags = cast('Flags', replace(ctx.flags, submodules=_choice_of_the_others(ctx.git)))
    clone.clone_at(ctx.git, flags, Path(step.path), step.url or '', step.to)


def _choice_of_the_others(git: GitRunner) -> str | None:
    """What the nested repos do with their submodules: 'keep' if one keeps them, else 'nest'.

    None if no .gitnested says it.
    """
    files = git.check_output(['ls-files', '-z', '--', f':(glob)**/{GITNESTED_FILENAME}']).split('\0')
    choices = {(configio.read(Path(path)).get('nested') or {}).get('submodules') for path in files if path}
    return next((choice for choice in ('keep', 'nest') if choice in choices), None)


def _apply_url(ctx: CommandContext, step: _Step) -> None:
    subdir = Path(step.path)
    config.write_field(ctx.git, subdir / GITNESTED_FILENAME, 'remote', step.url or '')
    content.commit_gitnested_update(ctx.git, ctx.flags, subdir, f"git nested submodules: new url for {step.path}")
    output.say(f"{step.path}: remote set to {step.url}")


def _apply_pull(ctx: CommandContext, step: _Step) -> None:
    try:
        pull.pull_to(ctx, Path(step.path), step.url, step.to)
    except GitNestedError as e:
        tree = _stopped_tree(ctx, step.path)
        if tree is None:
            raise
        patch = re.search(r'the patch (\S+) does not apply', e.message)
        why = f" The patch {patch[1]} does not apply." if patch else ''
        raise GitNestedError(_stopped_message(ctx.git, step.path, tree, why)) from None


def _stopped_tree(ctx: CommandContext, path: str) -> Path | None:
    """The worktree where the pull of `path` stopped on conflicts, if it did."""
    branch = refs.nested_branch(ctx.git, refs.sanitize_subref(path))
    # A rebase that stopped has no branch checked out
    tree = worktree.find_worktree(ctx.git, branch) or ctx.tmp / branch
    return tree if tree.is_dir() and worktree.stopped(ctx.git, tree) else None


def _stopped_message(git: GitRunner, path: str, tree: Path, why: str) -> str:
    """How to go on after a conflict in a nested repo: the `submodules` way only."""
    files = _conflicts(git, tree)
    return (
        f"{path}: the update stopped on conflicts in {', '.join(files) or 'its files'}.{why}\n"
        "Fix them there, and 'git add' them:\n\n"
        f"  cd {Path(os.path.relpath(tree)).as_posix()}\n\n"
        f"Then run 'git nested submodules update --continue'. It finishes {path} and goes on with the others.\n"
        "Or throw the update away: 'git nested submodules update --abort'."
    )


# Each step makes one commit, or none for skip.
_APPLY: dict[str, Callable[[CommandContext, _Step], None]] = {
    'skip': _apply_skip,
    'move': _apply_move,
    'remove': _apply_remove,
    'nest': _apply_nest,
    'pull': _apply_pull,
    'url': _apply_url,
}
