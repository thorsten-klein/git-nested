# `git nested config`

Read or write a nested repository's configuration.

```text
git nested config [<subdir>]                  # print all fields
git nested config [<subdir>] <key>            # print one field
git nested config [<subdir>] <key> <value>    # set one field
```

## What it does

`config` reads and writes the fields of `<subdir>/.gitnested`. Use it
instead of editing the file by hand.

- With no key, it prints every field the file sets, one per line:
  `<key> <value>`.
- With a key, it prints the value. A field that is not set prints nothing.
- With a key and a value, it sets the field and stages the file. It does
  not commit. Commit it yourself.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository. Can be left out inside it |
| `<key>` | the field to read or write |
| `<value>` | the new value |

## Keys

| Key | Meaning | Writable |
|---|---|---|
| `remote` | the upstream repository | yes |
| `branch` | the upstream branch | yes |
| `method` | how upstream history is joined: `merge` or `rebase` | yes |
| `squash` | whether pull makes one parent commit: `true` or `false` | yes |
| `commit` | the upstream commit currently nested | no |
| `parent` | the commit the nested history hangs off | yes |
| `filter` | the paths of the upstream repository that are nested | no |
| `exclude` | the paths of the upstream repository that are left out | no |
| `path` | the directory of the upstream repository that is nested, at the root of the subdir | no |
| `pin` | a commit or tag of the branch to nest, instead of its newest commit | yes |
| `cmdver` | the git-nested version that last wrote this file | no |
| `readonly` | `true` makes push refuse, for a repository that is only pulled | yes |

The other keys are written by the commands themselves. Setting one by hand
would describe a state the repository is not in.

[The `.gitnested` file](../configuration/gitnested-file.md) explains each
key.

## Examples

```bash
git nested config ext/lib
git nested config ext/lib method
git nested config ext/lib method rebase
git nested config ext/lib readonly true
git commit -m "lib: pull with rebase, never push"
```

## Notes

- A relative path as a `remote` value is taken relative to the folder you
  are in, like git does. It is stored relative to the top of your
  repository.
- An unknown key, or a bad value for `method`, `squash` or `readonly`, is
  refused.
