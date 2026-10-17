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

`pull` keeps them nested. After the pull, each one moves to the commit
upstream pins now.

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
