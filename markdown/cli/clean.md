# `git nested clean`

Remove the branches, refs and remotes nested operations created.

```text
git nested clean [<options>] [<subdir>]
git nested clean --all [<options>]
```

## What it does

`clean` removes what other commands left behind for `<subdir>`:

- the nested branch,
- its worktree,
- the git remote [`branch`](branch.md) made,
- the branch name `--name` stored.

Nothing in your own history is touched. So `clean` is also how you give up
a pull or push that is half done.

It works without `.gitnested` too, for example after a reset undid the
clone.

## Arguments

| Argument   | Meaning                                          |
|------------|--------------------------------------------------|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option          | Meaning                                                 |
|-----------------|---------------------------------------------------------|
| `-a`, `--all`   | clean all nested repositories                           |
| `-A`, `--ALL`   | also the nested repositories inside nested repositories |
| `-f`, `--force` | also remove the refs under `refs/nested/<subdir>/`      |

With `--all --force`, `clean` also removes every leftover `nested/*`
branch of this worktree, and all nested refs. That catches nested
repositories that do not exist any more.

## Examples

```bash
git nested clean ext/lib
git nested clean --all
git nested clean --all --force
```

## See also

- [Resolve conflicts](../guides/conflicts.md)
