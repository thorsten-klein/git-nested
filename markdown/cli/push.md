# `git nested push`

Push a nested repository’s local changes upstream.

```text
git nested push [<options>] [<subdir> [<nested-branch>]]
git nested push --all [<options>]
```

## What it does

1. Pick the target branch upstream. See below.
2. Fetch it. If it has commits you do not have, stop. Pull first.
3. Build the nested branch from your local commits.
4. Push it to the target branch.
5. With `--commit`, record the pushed commit in `.gitnested` and commit
   that.

Only changes inside `<subdir>` are pushed. `.gitnested` is never pushed.

Without `--commit`, other changes in your working tree do not block a push.
If `<subdir>` itself has uncommitted changes, `push` warns and uses only what
is committed.

## The target branch

| You give                                                   | Push goes to                                   |
|------------------------------------------------------------|------------------------------------------------|
| `-b <name>`                                                | `<name>`                                       |
| nothing, and upstream has the tracked branch               | `<your repo>-<branch>`, for example `app-main` |
| nothing, and upstream does not have the tracked branch yet | the tracked branch                             |

`<your repo>` is the name of the top folder of your repository.

So by default a push makes a **review branch**. Open a pull request from it
upstream. After it is merged, run [`pull`](pull.md).

To push straight to the tracked branch, name it, and record the push:

```bash
git nested push -b main --commit ext/lib
```

## Arguments

| Argument          | Meaning                                                         |
|-------------------|-----------------------------------------------------------------|
| `<subdir>`        | the nested repository. Can be left out inside it                |
| `<nested-branch>` | a branch to push as it is. Default: build `nested/<subdir>` now |

## Options

| Option                          | Meaning                                                                      |
|---------------------------------|------------------------------------------------------------------------------|
| `-a`, `--all`                   | push all nested repositories. Read-only ones are skipped                     |
| `--single-commit`               | with `--all` and `--commit`: one commit for all of them                      |
| `-b`, `--branch <branch>`       | the upstream branch to push to                                               |
| `-r`, `--remote <remote>`       | push to this upstream, just this time                                        |
| `-u`, `--update`                | write the `-b` / `-r` value to `.gitnested`                                  |
| `-c`, `--commit`                | record the pushed commit in `.gitnested`. Needs a push to the tracked branch |
| `--dry-run`                     | show the target branch and the commits, then stop                            |
| `-s`, `--squash`                | push all local commits as one commit                                         |
| `-m`, `--message <message>`     | the message for `--squash` or `--commit`                                     |
| `--file <file>`                 | read that message from a file                                                |
| `--tag <name>`                  | also tag the pushed upstream commit                                          |
| `-M`, `--method <merge|rebase>` | the join method, just this time                                              |
| `--merge`, `--rebase`           | short for `-M merge` and `-M rebase`                                         |
| `-f`, `--force`                 | force-push, even if upstream has commits you do not have                     |
| `-S`, `--gpg-sign`              | GPG-sign the commits git-nested makes, nested ones too                       |
| `--signoff`                     | add a `Signed-off-by:` trailer to the commit                                 |

## Examples

```bash
git nested push ext/lib                         # to the review branch
git nested push -b fix-parser ext/lib           # to a branch you name
git nested push -b main --commit ext/lib        # to the tracked branch
git nested push --rebase ext/lib                # linear history upstream
git nested push --all -b release/2.0
```

### Look first

```bash
git nested push --dry-run ext/lib
```

```text
ext/lib: would push to https://github.com/user/lib (app-main)
  9a38b6d lib: add bye
```

Nothing is pushed or changed.

### One commit upstream

```bash
git nested push --squash -m "Add bye()" ext/lib
```

Without `-m` the message lists the subjects of the squashed commits. With
only one commit, its own message is used.

### Tag a release

```bash
git nested push -b main --commit --tag v1.4 ext/lib
```

With nothing new to push, `--tag` tags the upstream commit `ext/lib` already
has. With `--all` it tags each one.

### Push a branch you fixed by hand

After [`branch`](branch.md) and some work in its worktree:

```bash
git nested push ext/lib nested/ext%2Flib
```

## Notes

- With the `rebase` method, the nested branch is rebased onto upstream
  first. If that fails, nothing is pushed.
- `--commit` needs a clean working tree.
- `--commit` refuses a push to another branch than the tracked one. The
  next pull would start from a commit that branch does not have. With
  `-b` or `-r`, add `-u` to track them.
- `--dry-run` can not be used with `--commit`.
- `--squash` can not be used with `<nested-branch>`.
- A read-only nested repository is refused. With `--all` it is skipped.
  See [`readonly`](../configuration/gitnested-file.md#readonly).
- Files left out with `filter` or `exclude` are never deleted upstream.
- A nested repository you added inside `<subdir>` is not pushed. Level
  files are not pushed either. A nested repository that came from upstream
  goes back as it came, also as a submodule.

## See also

- [`pull`](pull.md)
- [How it works](../concepts/how-it-works.md#push)
