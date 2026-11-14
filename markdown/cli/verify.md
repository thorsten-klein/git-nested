# `git nested verify`

Check that a nested repository is its upstream commit plus patches or diffs.

```text
git nested verify [<options>] <subdir> [--patches <patch>...]
git nested verify [<options>] <subdir> --diffs [<diff>...]
```

## What it does

1. Checks out the upstream commit from `.gitnested` in a temporary
   worktree. Fetches it only if it is missing.
2. Applies the files there, in order: patches with `git am`, and diffs
   with `git apply`.
3. Compares the result with `<subdir>` in `HEAD`. `.gitnested` files are
   left out.

Without `--diffs`, the files are patches.

Patches are `git format-patch` files: a header with author and subject,
then the diff. Diffs can be plain (`git diff`, `diff -u`). Paths are
relative to `<subdir>`. A plain diff given as a patch is refused: `git am`
needs the header.

Your working tree and branches are not touched.

Without files, it checks that `<subdir>` has no local changes. For the
[patches](../configuration/gitnested-file.md#patches) folder of
`.gitnested`, use [`patches`](patches.md).

Nested repositories inside `<subdir>` and the patches folder are not
compared. They are not upstream content.

### When it differs

The command fails and lists the changed files.

- Patches: it writes the missing patch, numbered after the others. It goes
  into `--output`, else next to the last patch. Fill in its TODO title and
  description, rename it, and commit it.
- `--diffs`: with `--output`, it writes the whole diff to that file.

## Arguments

| Argument   | Meaning               |
|------------|-----------------------|
| `<subdir>` | the nested repository |

## Options

| Option                  | Meaning                                                                   |
|-------------------------|---------------------------------------------------------------------------|
| `--patches <patch>...`  | the patches to apply, in order                                            |
| `--diffs <diff>...`     | the diffs to apply, in order                                              |
| `-o`, `--output <path>` | patches: folder for the missing patch. `--diffs`: file for the whole diff |
| `-k`, `--keep`          | keep the temporary worktree                                               |
| `--ignore <path>`       | do not compare this path. Can be repeated                                 |

## Examples

```bash
git nested verify ext/lib --patches patches/lib/*.patch
git nested verify -o patches/lib ext/lib
git nested verify ext/lib --diffs lib.diff
git nested verify -o lib.diff ext/lib --diffs lib.diff
git nested verify --ignore ext/lib/build ext/lib
```

`--patches` and `--diffs` take all the files after them. So put `<subdir>`
first.

### Skip a folder

```bash
git nested verify --ignore ext/lib/build ext/lib --patches patches/lib/*.patch
```

Changes in `ext/lib/build` do not count. They are not in the written patch
or diff either. Give the path like `<subdir>`.

## See also

- [`diff`](diff.md)
- [`patches`](patches.md)
- [Make your changes to nested repositories visible](../guides/patches.md)
