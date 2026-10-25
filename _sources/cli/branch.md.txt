# `git nested branch`

Create a branch holding the local nested commits.

```text
git nested branch [<options>] [<subdir>]
git nested branch --all [<options>]
```

## What it does

`branch` builds the nested branch `nested/<subdir>`. It holds the history of
`<subdir>` as if it were its own repository: the upstream commit, and your
local commits on top. `.gitnested` is left out.

The branch is checked out in a worktree. By default that is
`.git/tmp/nested/<subdir>`.

The branch tracks upstream through a git remote with the same name. So in
the worktree, plain `git fetch`, `git pull` and `git push` talk to upstream.

Use it to:

- look at the nested history on its own,
- fix up the history before a push,
- finish a pull by hand. See [Resolve conflicts](../guides/conflicts.md).

Other changes in your working tree do not block it. If `<subdir>` has
uncommitted changes, `branch` warns and ignores them.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option | Meaning |
|---|---|
| `-a`, `--all` | build the branch for all nested repositories |
| `-d`, `--dir <dir>` | put the worktree here. Default: `.git/tmp/nested/<subdir>` |
| `-n`, `--name <name>` | name the branch. Default: `nested/<subdir>` |
| `-F`, `--fetch` | fetch upstream first |
| `-f`, `--force` | build the branch again if it exists |
| `-S`, `--gpg-sign` | GPG-sign the rebuilt nested commits |

## Examples

```bash
git nested branch ext/lib
git nested branch -d ../lib ext/lib
git nested branch --name lib-fixes ext/lib
git nested branch --all
```

Then work in the worktree:

```bash
git nested run ext/lib log --oneline
cd .git/tmp/nested/ext%2Flib
git commit --amend
cd -
git nested push ext/lib nested/ext%2Flib
```

## Branch names

| Case | Branch name |
|---|---|
| `ext/lib` | `nested/ext%2Flib`. A `/` becomes `%2F`, so it does not clash with `nested/ext` |
| in a linked worktree `wt` of your repository | `nested/ext%2Flib@wt`, so worktrees do not block each other |
| with `--name lib-fixes` | `lib-fixes` |

A name from `--name` is stored in `.git/config`, as
`nested.<subdir>.branchname`. So `run`, `commit`, `push`, `pull` and
`status` use that branch too, until `git nested clean` forgets it.

## Notes

- If the branch exists already, `branch` stops. It shows what the branch
  holds, so you can decide: reuse it, use `--force` to build it again, or
  remove it with [`clean`](clean.md).
- `--dir` pointing at the worktree of the same nested repository builds the
  branch again there. The worktree of anything else is never touched.
- A local branch called `nested` blocks the `nested/...` branches. Rename it,
  or use `--name`.
- `--name` can not be the name of a branch git-nested does not own.
- `--dir` and `--name` can not be used with `--all`.

## See also

- [`run`](run.md), [`commit`](commit.md), [`clean`](clean.md)
- [git config settings](../configuration/git-config.md)
