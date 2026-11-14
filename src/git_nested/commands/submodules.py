"""Turn all submodules into nested repos, and keep them in step with upstream.

The root repo stays a normal clone of the upstream superproject. Its
submodules are nested repos.

- init: nest every submodule, or the ones named, one commit each.
- merge: merge an upstream commit, drop the gitlinks it brings, then update
  the nested repos to match. One commit per nested repo.
- pull: fetch, then merge.
"""

from __future__ import annotations

import json
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
# Where a merge that stopped keeps what --continue needs. Written once.
_STATE_FILE = 'nested-submodules-pull.json'
_MAX_ARGS = {'init': 0, 'merge': 1, 'pull': 2}
# What init left out, in .gitmodules: merge and pull leave new submodules there out too
_ONLY, _IGNORE = 'nested.only', 'nested.ignore'
# The lines git merge-file marks a conflict with
_CONFLICT_MARKER = re.compile(r'^(<{7}|={7}|>{7})', re.MULTILINE)
# A SHA-1 or SHA-256 commit id
_COMMIT_ID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')


def cmd_submodules(ctx: CommandContext) -> None:
    """Run `submodules init`, `merge` or `pull`."""
    action = ctx.submodules_action or ''
    args = ctx.submodules_args or []
    _check_args(ctx.flags, action, args)
    if action == 'init':
        checks.check_worktree_clean(ctx.git, 'init')
        _nest_all(ctx.git, ctx.flags)
    else:
        _merge(ctx, action, args)


def _given(flags: Flags) -> list[str]:
    """The options of merge and pull that were given."""
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
        output.usage_error(f"{given[0]} only works with 'submodules merge' and 'submodules pull'")
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
    # .gitnested keeps the choice, for merge and pull
    choice = cast('Flags', replace(flags, submodules='nest' if flags.recursive else 'keep', hint='--recursive'))
    for path in links:
        init.init_from_submodule(git, choice, Path(path), flags.resolve_relative)


def _selected(git: GitRunner, flags: Flags) -> list[str]:
    """The submodules that --only and --ignore leave in."""
    links = [path for path, _ in submodules.gitlinks(git, Path())]
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
    inside nested repos. And new ones that init's --only or --ignore leaves
    out.
    """
    ours_links = submodules.gitlinks_at(git, ours)
    names = {name for path, (name, _) in _modules_at(git, ours).items() if path in ours_links}
    only, ignore = _selection_at(git, ours)
    target_modules = _modules_at(git, target)
    kept = set(ours_links)
    for path in submodules.gitlinks_at(git, target):
        name = target_modules.get(path, ('', ''))[0]
        if path in ours_links or (name and name in names) or (not _is_nested(path) and _left_out(path, only, ignore)):
            kept.add(path)
    return kept


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
# merge and pull
# ============================================================================


def _merge(ctx: CommandContext, action: str, args: list[str]) -> None:
    git = ctx.git
    state_file = Path(git.check_output(['rev-parse', '--git-dir'])) / _STATE_FILE
    if ctx.flags.abort:
        _abort(git, state_file)
        return
    state = _resume(git, state_file) if ctx.flags.resume else _start(ctx, state_file, action, args)
    if state is None:
        return
    _finish_merge(git, ctx.flags, state['action'])
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
        _APPLY[step.what](steps_ctx, step, state['action'])


def _merge_commit(git: GitRunner, target: str) -> str:
    """The merge commit of `target` on this branch."""
    log = git.check_output(['log', '--first-parent', '--merges', '--format=%H %P', f'{target}..HEAD'])
    for line in log.splitlines():
        commit_id, *parents = line.split()
        if target in parents[1:]:
            return commit_id
    raise GitNestedError(f"the merge commit of {target} is gone")


def _abort(git: GitRunner, state_file: Path) -> None:
    """Throw away a merge that stopped. Nested repos that it already updated stay."""
    if not state_file.is_file():
        raise GitNestedError("there is nothing to abort")
    if _merging(git):
        git.run(['merge', '--abort'])
    state_file.unlink()
    output.say("aborted")


def _resume(git: GitRunner, state_file: Path) -> dict[str, str]:
    """The state of the merge that stopped. The merge must still be there, or be done."""
    if not state_file.is_file():
        raise GitNestedError("there is nothing to continue")
    state = _load(state_file)
    if not _merging(git) and not _is_ancestor(git, state['target'], 'HEAD'):
        raise GitNestedError(
            f"The merge of upstream is gone. Start over with 'git nested submodules {state['action']} --abort'."
        )
    return state


def _load(state_file: Path) -> dict[str, str]:
    """Read the state file, and check what it says."""
    broken = GitNestedError(f"{state_file.as_posix()} is broken. Start over with --abort.")
    try:
        raw = json.loads(state_file.read_text())
        state = {
            'action': 'merge' if raw['action'] == 'merge' else 'pull',
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


def _start(ctx: CommandContext, state_file: Path, action: str, args: list[str]) -> dict[str, str] | None:
    """Start the merge. None if there is nothing to merge, or on --dry-run."""
    git = ctx.git
    if state_file.is_file():
        raise GitNestedError(
            f"A 'submodules {action}' stopped before. Finish it with 'git nested submodules {action} --continue'."
        )
    if not args and _merging(git):
        return _take_over(ctx, state_file, action)
    checks.check_worktree_clean(git, 'pull')
    ref, remote_url, label = _fetch(git, args) if action == 'pull' else _resolve(git, args)
    target = git.check_output(['rev-parse', f'{ref}^{{commit}}'])
    if _is_ancestor(git, target, 'HEAD'):
        output.say(f"already up to date with {label}")
        return None
    base = git.check_output(['merge-base', 'HEAD', target], may_fail=True)
    if not base:
        raise GitNestedError(f"{label} has no history in common with this branch")
    state = {
        'action': action,
        'base': base,
        'target': target,
        'url': remote_url,
        'single': 'yes' if ctx.flags.single_commit else '',
    }
    if ctx.flags.dry_run:
        _show_plan(git, state, label)
        return None
    _start_merge(git, ref)
    # Only now: --continue needs a merge to continue
    state_file.write_text(json.dumps(state))
    _drop_gitlinks(git, state)
    return state


def _take_over(ctx: CommandContext, state_file: Path, action: str) -> dict[str, str] | None:
    """Finish a `git merge` that stopped on the submodules. None on --dry-run.

    A plain git merge can't put a gitlink where a nested folder is. So it
    stops. This drops the gitlinks, and the steps update the nested repos.
    """
    git = ctx.git
    _current_branch(git)
    target = git.check_output(['rev-parse', 'MERGE_HEAD'])
    state = {
        'action': action,
        'base': git.check_output(['merge-base', 'HEAD', target]),
        'target': target,
        'url': _remote_url_of(git, _remote_ref_at(git, target)),
        'single': 'yes' if ctx.flags.single_commit else '',
    }
    if ctx.flags.dry_run:
        _show_plan(git, state, 'the merge in progress')
        return None
    state_file.write_text(json.dumps(state))
    _drop_gitlinks(git, state)
    return state


def _remote_ref_at(git: GitRunner, commit: str) -> str:
    """A remote-tracking branch at `commit`, else `commit` itself."""
    refs = git.check_output(['for-each-ref', '--points-at', commit, '--format=%(refname)', 'refs/remotes'])
    return next(iter(refs.split()), commit)


def _current_branch(git: GitRunner) -> str:
    branch = git.check_output(['symbolic-ref', '--short', '-q', 'HEAD'], may_fail=True)
    if not branch:
        raise GitNestedError("HEAD is detached. Check out a branch first.")
    return branch


def _fetch(git: GitRunner, args: list[str]) -> tuple[str, str, str]:
    """Fetch what to merge. Return the ref to merge, the url of its remote, and a name to show."""
    current = _current_branch(git)
    ref, remote = _fetch_named(git, args, current) if args else _fetch_upstream(git, current)
    url = git.check_output(['remote', 'get-url', remote], may_fail=True) or remote
    return ref, url, ' '.join(args) if args else ref


def _fetch_named(git: GitRunner, args: list[str], current: str) -> tuple[str, str]:
    """Fetch <branch> from <remote>, like git pull. Return FETCH_HEAD and the remote."""
    remote = args[0]
    if remote not in git.check_output(['remote']).split() and _is_commit(git, remote):
        raise GitNestedError(f"{remote} is not a remote. To merge it, run 'git nested submodules merge {remote}'.")
    branch = args[1] if len(args) > 1 else current
    git.network(['fetch', '-q', remote, branch], f"fetching {branch} from {remote}")
    return 'FETCH_HEAD', remote


def _fetch_upstream(git: GitRunner, current: str) -> tuple[str, str]:
    """Fetch the remote of the current branch. Return its upstream branch and the remote."""
    ref = git.check_output(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'], may_fail=True)
    if not ref:
        raise GitNestedError("This branch has no upstream. Name a remote and a branch.")
    remote = git.check_output(['config', f'branch.{current}.remote'])
    git.network(['fetch', '-q', remote], f"fetching {remote}")
    return ref, remote


def _resolve(git: GitRunner, args: list[str]) -> tuple[str, str, str]:
    """The commit to merge, as given. Return it, the url of its remote, and a name to show."""
    _current_branch(git)
    if not args:
        output.usage_error("'submodules merge' needs a commit, or a git merge in progress")
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
    file.write_text(git.check_output(['show', f'{rev}:{_GITMODULES}'], may_fail=True) + '\n', encoding='utf-8')
    others = {name for name, _ in _modules_at(git, rev).values()} - names
    for section in [*(f'submodule.{name}' for name in others), 'nested']:
        git.run(['config', '-f', file, '--remove-section', section], may_fail=True)
    _add_selection(git, file, selection)
    return file.as_posix()


def _remove_if_empty(path: Path) -> None:
    """A gitlink leaves an empty folder behind."""
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


def _finish_merge(git: GitRunner, flags: Flags, action: str) -> None:
    """Commit the merge. Stop if there are conflicts left."""
    if not _merging(git):
        return
    conflicts = sorted(set(git.check_output(['diff', '--name-only', '--diff-filter=U']).split('\n')) - {''})
    if conflicts:
        raise GitNestedError(
            f"the merge has conflicts in: {', '.join(conflicts)}\n"
            f"Fix them and 'git add' them. Then run 'git nested submodules {action} --continue'."
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


def _finish_pending(ctx: CommandContext, path: str) -> None:
    """Commit the submodule pull that stopped on conflicts, if you have not done it yet."""
    git = ctx.git
    branch = refs.nested_branch(git, refs.sanitize_subref(path))
    tree = worktree.find_worktree(git, branch)
    if tree is None:
        return
    if git.run(['rev-parse', '-q', '--verify', 'MERGE_HEAD'], cwd=tree, may_fail=True).returncode == 0:
        left = git.check_output(['diff', '--name-only', '--diff-filter=U'], cwd=tree).split()
        if left:
            raise GitNestedError(f"{path}: fix the conflicts in {tree.as_posix()} first: {', '.join(left)}")
        git.run(['commit', '-q', '--no-edit'], cwd=tree)
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


def _modules_at(git: GitRunner, commit: str) -> dict[str, tuple[str, str]]:
    """The .gitmodules of `commit`, as {path: (name, url)}."""
    text = git.check_output(['show', f'{commit}:{_GITMODULES}'], may_fail=True)
    fields: dict[str, dict[str, str]] = {}
    lines = git.check_output(
        ['config', '-f', '-', '--get-regexp', r'^submodule\..*\.(path|url)$'], may_fail=True, input=text
    )
    for line in lines.splitlines():
        key, _, value = line.partition(' ')
        name, _, field = key.removeprefix('submodule.').rpartition('.')
        fields.setdefault(name, {})[field] = value
    return {f['path']: (name, f['url']) for name, f in fields.items() if 'path' in f and 'url' in f}


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


def _show_plan(git: GitRunner, state: dict[str, str], ref: str) -> None:
    count = git.check_output(['rev-list', '--count', f"HEAD..{state['target']}"])
    output.say(f"would merge {count} commits of {ref}")
    for step in _plan(git, state):
        if step.what != 'skip' or step.note:
            output.say(f"{step.path}: would {step.text()}" + (f" ({step.note})" if step.note else ''))


def _apply_skip(_ctx: CommandContext, step: _Step, _action: str) -> None:
    if step.note:
        output.warn(f"{step.path}: {step.note}")


def _apply_move(ctx: CommandContext, step: _Step, _action: str) -> None:
    Path(step.to).parent.mkdir(parents=True, exist_ok=True)
    ctx.git.run(['mv', '--', step.path, step.to])
    message = f"git nested submodules: move {step.path} to {step.to}"
    content.commit_gitnested_update(ctx.git, ctx.flags, Path(step.to), message)
    output.say(f"{step.path}: moved to {step.to}")


def _apply_remove(ctx: CommandContext, step: _Step, _action: str) -> None:
    if step.note:
        output.warn(f"{step.path}: {step.note}")
    ctx.git.run(['rm', '-r', '-q', '--', step.path])
    content.commit_gitnested_update(ctx.git, ctx.flags, Path(step.path), f"git nested submodules: remove {step.path}")
    output.say(f"{step.path}: removed, upstream dropped it")


def _apply_nest(ctx: CommandContext, step: _Step, _action: str) -> None:
    flags = cast('Flags', replace(ctx.flags, submodules=_choice_of_the_others(ctx.git)))
    clone.clone_at(ctx.git, flags, Path(step.path), step.url or '', step.to)


def _choice_of_the_others(git: GitRunner) -> str | None:
    """What the nested repos do with their submodules: 'keep' if one keeps them, else 'nest'.

    None if no .gitnested says it.
    """
    files = git.check_output(['ls-files', '-z', '--', f':(glob)**/{GITNESTED_FILENAME}']).split('\0')
    choices = {(configio.read(Path(path)).get('nested') or {}).get('submodules') for path in files if path}
    return next((choice for choice in ('keep', 'nest') if choice in choices), None)


def _apply_url(ctx: CommandContext, step: _Step, _action: str) -> None:
    subdir = Path(step.path)
    config.write_field(ctx.git, subdir / GITNESTED_FILENAME, 'remote', step.url or '')
    content.commit_gitnested_update(ctx.git, ctx.flags, subdir, f"git nested submodules: new url for {step.path}")
    output.say(f"{step.path}: remote set to {step.url}")


def _apply_pull(ctx: CommandContext, step: _Step, action: str) -> None:
    try:
        pull.pull_to(ctx, Path(step.path), step.url, step.to)
    except GitNestedError as e:
        raise GitNestedError(
            f"{e.message.rstrip()}\n\n"
            f"Shorter: fix the files there and 'git add' them. Then run 'git nested submodules {action} --continue'. "
            "It commits the pull and goes on with the other submodules."
        ) from None


# Each step makes one commit, or none for skip.
_APPLY: dict[str, Callable[[CommandContext, _Step, str], None]] = {
    'skip': _apply_skip,
    'move': _apply_move,
    'remove': _apply_remove,
    'nest': _apply_nest,
    'pull': _apply_pull,
    'url': _apply_url,
}
