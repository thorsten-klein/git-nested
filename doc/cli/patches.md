# `git nested patches`

Write the patches of a nested repository.

```text
git nested patches create [<options>] [<subdir>]
git nested patches create --all
```

## What it does

The [patches](../configuration/gitnested-file.md#patches) are the local
changes of `<subdir>`, kept as `git format-patch` files in the patches
folder. `.gitnested` names the folder; they are off without it.

It builds them again in a temporary worktree:

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

The patches folder is read as it is in your working tree. The rest of
`<subdir>` is taken from `HEAD`.

## Arguments

| Argument | Meaning |
|---|---|
| `create` | write the missing patch, and all patches again |
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option | Meaning |
|---|---|
| `-a`, `--all` | act on all nested repositories |

## Examples

```bash
git nested patches create ext/lib
git nested patches create --all
```

## Notes

- The patches must be on, and the setup must be one they work with: no
  `filter`, `exclude` or `path`, and not `squash: false`.
- A file in the folder that is not a patch is refused. A patch has a
  header, as `git format-patch` writes it.

## See also

- [Make your changes to nested repositories visible](../guides/patches.md)
- [`verify`](verify.md): check against any patches or diffs
