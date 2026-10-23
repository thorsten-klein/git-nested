# `git nested clone`

Clone an upstream repository into a subdirectory.

```text
git nested clone [<options>] <upstream> [<subdir>]
```

## What it does

`clone` fetches the upstream branch and copies its files into `<subdir>`.
It writes `<subdir>/.gitnested` and makes one commit. Everyone who clones
your repository gets these files. They need nothing else.

It also works in a new repository with no commits yet. The clone commit then
becomes the first commit.

It needs a clean working tree.

## Arguments

| Argument | Meaning |
|---|---|
| `<upstream>` | URL or path of the repository to clone |
| `<subdir>` | where to put it. Default: the name of the upstream, for example `lib` for `https://github.com/user/lib.git` |

A relative path as `<upstream>` is taken relative to the folder you are
in. It is stored relative to the top of your repository. So it keeps
working in every clone of your repository that has the same layout.

## Options

| Option | Meaning |
|---|---|
| `-b`, `--branch <branch>` | the upstream branch to track. Default: the default branch of upstream. A tag or a commit works too |
| `--pin <commit\|tag>` | nest this commit or tag of the branch, not its newest commit |
| `-M`, `--method <merge\|rebase>` | the join method for later pulls and pushes. Default: `merge` |
| `--merge`, `--rebase` | short for `-M merge` and `-M rebase` |
| `--filter <path>` | only nest this path of upstream. Give it more than once for more paths |
| `--exclude <path>` | leave this path of upstream out. Give it more than once for more paths |
| `--path <dir>` | nest only this folder of upstream, at the top of `<subdir>` |
| `--recurse-submodules` | nest the submodules of upstream too, at the commits it pins |
| `--adopt` | keep the files already in `<subdir>`. Only add `.gitnested` |
| `-f`, `--force` | clone again over an existing nested repository |
| `-m`, `--message <message>` | the commit message. Default: a generated one |
| `-S`, `--gpg-sign` | GPG-sign the commit |
| `--signoff` | add a `Signed-off-by:` trailer to the commit |

## Examples

```bash
git nested clone https://github.com/user/lib ext/lib
git nested clone https://github.com/user/lib            # into ./lib
git nested clone -b develop https://github.com/user/lib ext/lib
git nested clone --rebase https://github.com/user/lib ext/lib
```

### A release

`-b` takes a tag. Then there is no branch to follow later:

```bash
git nested clone -b v1.2 https://github.com/user/lib ext/lib
```

To follow the branch but stay at a release, pin it:

```bash
git nested clone -b main --pin v1.2 https://github.com/user/lib ext/lib
```

See [Pin a release](../guides/pin.md).

### Only a part of upstream

```bash
git nested clone --exclude tests https://github.com/user/lib ext/lib
git nested clone --filter src --filter LICENSE https://github.com/user/lib ext/lib
git nested clone --path javascript https://github.com/user/lib ext/js
```

See [Nest only a part of upstream](../guides/partial.md).

### A folder you already have

If `ext/lib` already holds a copy of upstream, keep it:

```bash
git nested clone --adopt https://github.com/user/lib ext/lib
```

See [Adopt an existing folder](../guides/adopt.md).

### Clone again

`--force` replaces an existing nested repository with upstream as it is now.
Local changes in it are dropped. A new URL or branch is recorded:

```bash
git nested clone --force https://github.com/other/lib ext/lib
git nested clone --force -b develop https://github.com/user/lib ext/lib
```

If nothing changed, it does nothing and says "already up to date".

## Notes

- `<subdir>` must be empty or not exist, unless you use `--adopt` or
  `--force`.
- `--path` can not be used with `--filter`.
- `--adopt` can not be used with `--filter` or `--recurse-submodules`.
- Without `--recurse-submodules`, submodules of upstream stay empty, and
  git-nested warns about it. See [Upstream submodules](../guides/submodules.md).
- If upstream is empty, `clone` stops. Use [`init`](init.md) and then
  [`push`](push.md) to fill it.

## See also

- [`init`](init.md): turn a folder into a nested repository without
  copying.
- [The `.gitnested` file](../configuration/gitnested-file.md)
