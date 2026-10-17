# `git nested init`

Turn an existing subdirectory into a nested repository.

```text
git nested init [<options>] <subdir>
git nested init --from-submodule <subdir>
```

## What it does

`init` writes `<subdir>/.gitnested` and commits it. The files in `<subdir>`
stay as they are.

Use it when:

- you have code in your repository that should get its own upstream
  repository,
- you have a copy of an upstream and know which upstream commit it is,
- you want to replace a git submodule.

It needs a clean working tree. git must track files in `<subdir>`.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the folder to turn into a nested repository |

## Options

| Option | Meaning |
|---|---|
| `-r`, `--remote <remote>` | the upstream URL or path. Without it, `remote` is `none` |
| `-b`, `--branch <branch>` | the upstream branch. Default: `init.defaultBranch` of git, or `main` |
| `-c`, `--commit <commit>` | the upstream commit the current content is based on. Needs `--remote` |
| `-M`, `--method <merge\|rebase>` | the join method. Default: `merge` |
| `--from-submodule` | turn the git submodule at `<subdir>` into a nested repository |
| `-S`, `--gpg-sign` | GPG-sign the commit |
| `--signoff` | add a `Signed-off-by:` trailer to the commit |

## Examples

### New code, new upstream

You have `lib/` in your repository. Now it should live in its own
repository too:

```bash
git nested init lib -r https://github.com/user/lib
git nested push lib --commit
```

The upstream may be empty. The first push makes the branch there.
`--commit` records the pushed commit in `.gitnested`, so later pulls and
pushes start from it.

### No upstream yet

```bash
git nested init lib
```

`remote` is `none`. Add it later:

```bash
git nested config lib remote https://github.com/user/lib
git commit -m "lib: set upstream"
```

### A copy of upstream

`ext/lib` holds upstream commit `abc123`, maybe with your own changes on
top. Tell git-nested:

```bash
git nested init ext/lib -r https://github.com/user/lib --commit abc123
```

The next pull and push start from that commit. Your changes since then are
kept as local changes. If you do not know the commit, try
[`clone --adopt`](clone.md#a-folder-you-already-have). It looks for a
matching commit.

### From a submodule

```bash
git nested init --from-submodule ext/lib
```

This removes the submodule and clones the same URL at the same commit into
its place. A relative submodule URL is resolved against the `origin` remote
of your repository. See [Upstream submodules](../guides/submodules.md).

## Notes

- `--commit` must be a commit on the upstream branch.
- `<subdir>` must not have a `.gitnested` yet.

## See also

- [`clone`](clone.md)
- [Adopt an existing folder](../guides/adopt.md)
