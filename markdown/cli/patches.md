# `git nested patches`

Write, check, drop or cherry-pick the patches of a nested repository.

```text
git nested patches create [<options>] [<subdir>]
git nested patches verify [<options>] [<subdir>]
git nested patches verify --all
git nested patches drop [<subdir>] <patch>...
git nested patches cherry-pick [<options>] [<subdir>] <commit-or-file>...
```

## What it does

The [patches](../configuration/gitnested-file.md#patches) are the local
changes of `<subdir>`, kept as `git format-patch` files in the patches
folder. `.gitnested` names the folder; they are off without it.

Both actions build the same thing in a temporary worktree:

1. Check out the upstream commit from `.gitnested`. Fetch it only if it is
   missing.
2. Apply the patches with `git am`, one commit each.
3. Compare the result with `<subdir>` in `HEAD`. `.gitnested` files, the
   patches folder and nested repositories inside are left out.
4. Write the patches again from the commits.

`create` then updates the folder:

- What `HEAD` has on top of the patches becomes one more patch, with the
  title `TODO: title`. Fill in the title and the description, and run
  `create` again.
- All patches are written again in one form: no commit id, no signature,
  and a name made from the title.

It does not commit the folder. Commit it yourself.

`verify` only checks. It fails if a change is not in a patch, or if
`create` would change a patch. Use it in CI.

`drop` removes patches, and their changes from `<subdir>`:

1. It checks that the patches hold all local changes, as a pull does.
2. It applies the other patches on the upstream commit. If a later patch
   needs a dropped one, it stops and changes nothing.
3. It puts the result into `<subdir>`, writes the other patches again,
   numbered without gaps, and commits both.

Name each patch by its path or by its file name. The working tree must be
clean.

The patches folder is read as it is in your working tree. The rest of
`<subdir>` is taken from `HEAD`.

`cherry-pick` adds commits or patch files as patches:

1. A commit that is here is taken as it is. Else it is fetched from the
   remote, the tracked one or `-r`. It can be a branch, a tag, a commit id
   or a ref like `refs/pull/42/head`. It is written as a patch, with its
   author, date and message.
2. A file is taken as a patch. A plain diff is refused.
3. Like `drop`, it checks that the patches hold all local changes, applies
   all patches on the upstream commit, puts the result into `<subdir>`, and
   commits it with the patches.

With `--local`, the new patches go into
[`patches-local`](../configuration/gitnested-file.md#patches-local) too,
so a push leaves them out. Once upstream has a cherry-picked commit, the
next pull drops its patch.

## Arguments

| Argument           | Meaning                                                    |
|--------------------|------------------------------------------------------------|
| `create`           | write the missing patch, and all patches again             |
| `verify`           | check that `create` would change nothing                   |
| `drop`             | remove patches, and their changes from `<subdir>`          |
| `cherry-pick`      | add commits or patch files as patches                      |
| `<subdir>`         | the nested repository. Can be left out inside it           |
| `<patch>`          | `drop`: a patch to drop, by its path or file name          |
| `<commit-or-file>` | `cherry-pick`: a commit to fetch and take, or a patch file |

## Options

| Option                    | Meaning                                                   |
|---------------------------|-----------------------------------------------------------|
| `-a`, `--all`             | act on all nested repositories                            |
| `-r`, `--remote <remote>` | `cherry-pick`: fetch from this remote, for example a fork |
| `--local`                 | `cherry-pick`: add the new patches to `patches-local`     |

## Examples

```bash
git nested patches create ext/lib
git nested patches verify ext/lib
git nested patches verify --all
git nested patches drop ext/lib 0002-Old-workaround.patch
git nested patches cherry-pick ext/lib a1b2c3d
git nested patches cherry-pick ext/lib refs/pull/42/head -r https://github.com/fork/lib --local
git nested patches cherry-pick ext/lib ~/fix-build.patch
```

## Notes

- The patches must be on, and the setup must be one they work with: no
  `filter`, `exclude` or `path`, and not `squash: false`.
- A file in the folder that is not a patch is refused. A patch has a
  header, as `git format-patch` writes it.

## See also

- [Make your changes to nested repositories visible](../guides/patches.md)
- [`verify`](verify.md): check against any patches or diffs
