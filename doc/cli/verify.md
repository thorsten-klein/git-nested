# `git nested verify`

Check that a nested repository is its upstream commit plus patches or diffs.

```text
git nested verify [<options>] <subdir> patches [--] [<patch>...]
git nested verify [<options>] <subdir> diff [--] [<diff>...]
```

## What it does

1. Checks out the upstream commit from `.gitnested` in a temporary
   worktree. Fetches it only if it is missing.
2. Applies the files there, in order, with `git apply`.
3. Compares the result with `<subdir>` in `HEAD`. `.gitnested` files are
   left out.

Without files, it checks that `<subdir>` has no local changes.

The files can be git patches (`git format-patch`) or plain diffs
(`git diff`, `diff -u`). Paths are relative to `<subdir>`.

Your working tree and branches are not touched.

### When it differs

The command fails and lists the changed files.

- `patches`: it writes the missing patch, numbered after the others, next
  to the last patch or into `--output`. Fill in its TODO title and
  description, rename it, and commit it.
- `diff`: with `--output`, it writes the whole diff to that file.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository |
| `patches` or `diff` | the kind of files |
| `<patch>`, `<diff>` | the files to apply, in order |

## Options

| Option | Meaning |
|---|---|
| `-o`, `--output <path>` | `patches`: folder for the missing patch. `diff`: file for the whole diff |
| `-k`, `--keep` | keep the temporary worktree |
| `--ignore <path>` | do not compare this path of `<subdir>`. Can be repeated |

## Examples

```bash
git nested verify ext/lib patches -- patches/lib/*.patch
git nested verify -o patches/lib ext/lib patches
git nested verify ext/lib diff lib.diff
git nested verify -o lib.diff ext/lib diff lib.diff
git nested verify --ignore ext/lib/build ext/lib patches
```

### Skip a folder

```bash
git nested verify --ignore ext/lib/build ext/lib patches -- patches/lib/*.patch
```

Changes in `ext/lib/build` do not count. They are also left out of the
missing patch or diff that is written. Give the path like `<subdir>`.

## See also

- [`diff`](diff.md)
