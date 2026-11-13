# `git nested patches`

Write, check or drop the patches of a nested repository.

```text
git nested patches create [<options>] [<subdir>]
git nested patches verify [<options>] [<subdir>]
git nested patches verify --all
git nested patches drop [<subdir>] <patch>...
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

## Arguments

| Argument | Meaning |
|---|---|
| `create` | write the missing patch, and all patches again |
| `verify` | check that `create` would change nothing |
| `drop` | remove patches, and their changes from `<subdir>` |
| `<subdir>` | the nested repository. Can be left out inside it |
| `<patch>` | `drop`: a patch to drop, by its path or file name |

## Options

| Option | Meaning |
|---|---|
| `-a`, `--all` | act on all nested repositories |

## Examples

```bash
git nested patches create ext/lib
git nested patches verify ext/lib
git nested patches verify --all
git nested patches drop ext/lib 0002-Old-workaround.patch
```

## Notes

- The patches must be on, and the setup must be one they work with: no
  `filter`, `exclude` or `path`, and not `squash: false`.
- A file in the folder that is not a patch is refused. A patch has a
  header, as `git format-patch` writes it.

## See also

- [Make your changes to nested repositories visible](../guides/patches.md)
- [`verify`](verify.md): check against any patches or diffs
