# `git nested run`

Run a git command in the worktree of a nested repository.

```text
git nested run <subdir> <git-command> [<args>...]
```

## What it does

`run` runs `git -C <worktree> <git-command> <args>` in the worktree that
[`branch`](branch.md) made. You do not need to change folders.

Everything after `<subdir>` goes to git as it is, options too. git's output
and exit code are passed through. Interactive commands, such as a pager or
`git add -p`, work too.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository |
| `<git-command> [<args>...]` | the git command to run |

## Examples

```bash
git nested branch ext/lib
git nested run ext/lib log --oneline
git nested run ext/lib status
git nested run ext/lib rebase -i HEAD~3
git nested run ext/lib push
```

## Notes

- There has to be a worktree. Make it with `git nested branch <subdir>`.
- The worktree is found by branch, so `branch -d <dir>` works too.

## See also

- [`branch`](branch.md)
