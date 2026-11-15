# Upstream submodules

## When upstream has submodules

A plain clone leaves the submodules of upstream empty. git-nested warns
about it.

To nest them too, add `--recurse-submodules`:

```bash
git nested clone --recurse-submodules https://github.com/user/lib ext/lib
```

Each submodule becomes a nested repository of its own, inside `ext/lib`.
Each one stays at the commit upstream pins.

### Pull

`pull` keeps them nested. Each one is pulled to the commit upstream pins
now. Your changes in it stay.

If one of them stops on conflicts, finish it as the message says. Then run
the same `pull` again. It updates the other ones.

`pull --force` takes upstream as it is. Inner nested repositories lose
their changes too. Add `--recurse-submodules` to nest them again.

If upstream adds a new submodule, a plain pull leaves it empty. To nest it
too:

```bash
git nested pull --recurse-submodules ext/lib
```

### Push

`push` sends them back to upstream as submodules again. Upstream sees no
difference.

## Replace your own submodule

You have a submodule in your repository and want it nested instead:

```bash
git nested init --from-submodule ext/lib
```

This:

1. removes the submodule, from `.gitmodules` and `.git/modules` too,
2. clones the same URL at the same commit into `ext/lib`,
3. makes one commit.

A relative submodule URL is resolved against the `origin` remote of your
repository.

## Turn a whole repository into one

Your repository has many submodules, maybe submodules in submodules. You
want all of them as plain files, and still follow upstream:

```bash
git nested submodules init --recursive
git fetch origin
git nested submodules update origin/main
```

`init --recursive` nests all of them, at any depth. Without
`--recursive`, it nests only the first level. `--only <path>` nests only
some. `update` merges upstream, keeps its commits, and
changes the nested repositories the way upstream changed its submodules.

To see what `update` would do first:

```bash
git nested submodules update --dry-run origin/main
```

In a fork, update from the project you forked:

```bash
git nested submodules init --recursive
git fetch upstream
git nested submodules update upstream/main
```

Use `update` instead of `git merge` or `git pull`. A plain git merge
can't put a gitlink where a nested folder is.

See [`submodules`](../cli/submodules.md). It also explains how the merged
history looks, and how to keep a submodule back.
