# Everyday tasks

A short list of the tasks you do most often. Each one links to the full
reference.

All examples use a nested repository in `ext/lib`.

## Add a repository

```bash
git nested clone https://github.com/user/lib ext/lib
```

Leave out the folder, and git-nested uses the name of the repository:
`lib`. Add `-b <branch>` to track another branch than the default one.
See [`clone`](../cli/clone.md).

## See where everything stands

```bash
git nested status            # all nested repositories, in detail
git nested status --short    # one line each
git nested status -F         # fetch first, to see new upstream commits
```

See [`status`](../cli/status.md).

## Get new upstream changes

```bash
git nested pull ext/lib
git nested pull --all        # every nested repository
```

See [`pull`](../cli/pull.md). If it stops with conflicts, see
[Resolve conflicts](../guides/conflicts.md).

## See what you changed

```bash
git nested diff ext/lib
```

See [`diff`](../cli/diff.md).

## Send your changes upstream

To a review branch, for a pull request:

```bash
git nested push ext/lib            # pushes to <your-repo>-<branch>
git nested push ext/lib -b fix-x   # or name the branch yourself
```

Straight to the tracked branch:

```bash
git nested push ext/lib -b main --commit
```

Look first, change nothing:

```bash
git nested push ext/lib --dry-run
```

See [`push`](../cli/push.md).

## Work from inside the folder

Like git, git-nested works from any folder of your repository. Inside a
nested repository you can leave out the folder:

```bash
cd ext/lib
git nested pull       # same as 'git nested pull ext/lib' from the top
```

## Change a setting

```bash
git nested config ext/lib                  # show all fields
git nested config ext/lib branch develop   # track another branch
git commit -m "lib: track develop"
```

See [`config`](../cli/config.md).

## Clean up after a failed pull or push

```bash
git nested clean ext/lib
```

See [`clean`](../cli/clean.md).

## Undo

Every git-nested command that changes your project makes a normal commit.
So you can undo it like any commit:

```bash
git reset --hard HEAD~1
git nested clean ext/lib
```
