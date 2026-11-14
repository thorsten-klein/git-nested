# `git nested submodules`

Turn all submodules into nested repositories.

```text
git nested submodules init [--recursive] [--resolve-relative <url>] [--only <path> | --ignore <path>]...
```

## What it does

Use it for a repository whose submodules should be plain files. You get one
repository with all the code in it.

The repository itself stays a normal git clone of its upstream. Each
submodule becomes a nested repository.

`init` nests every submodule at the commit it pins. Each submodule gets one
commit. With `--recursive`, it nests their submodules too. With `--only` or
`--ignore`, it nests only some of them.

No gitlink and no `.gitmodules` entry stays for a nested submodule.

## Options

| Option | Meaning |
|---|---|
| `--only <path>` | nest only the submodules at or below this path. The others stay submodules. Give it more than once for more paths |
| `--ignore <path>` | nest all submodules but the ones at or below this path. Give it more than once for more paths. Not with `--only` |
| `--recursive` | nest the submodules of the submodules too, at any depth. Without it, they stay submodules. The choice goes into each `.gitnested` as [`submodules`](../configuration/gitnested-file.md) |
| `--resolve-relative <url>` | resolve relative submodule urls against this url. Without it, `init` stops at a relative url |
| `-S`, `--gpg-sign` | GPG-sign the commits |
| `--signoff` | add a `Signed-off-by:` trailer to the commits |

## Examples

```bash
git clone https://github.com/user/project
cd project
git nested submodules init --recursive
```

### Relative urls

A url like `../lib.git` is relative to the url of the superproject. In a
fork, that is not `origin`. So `init` stops and asks for the url:

```bash
git nested submodules init --resolve-relative https://github.com/org/project
```

Now `../lib.git` is `https://github.com/org/lib.git`. This is only for
the first level. With `--recursive`, a deeper relative url is relative to
the url of its parent submodule, as in git.

### Only some submodules

Name the paths to nest:

```bash
git nested submodules init --only lib/core --only third_party
```

This nests `lib/core` and every submodule below `third_party`. The others
stay submodules.

Or name the ones to keep as submodules:

```bash
git nested submodules init --ignore vendor/big
```

`init` keeps `--only` and `--ignore` in `.gitmodules`, in a `[nested]`
section.

## Notes

- `init` needs a clean working tree.
- If your `.gitattributes` would change files of a nested repository, for
  example `*.bat text eol=crlf`, git-nested adds `-text` for these files to
  `.gitattributes`. So they stay as upstream has them, as in a submodule.
- Push your changes to each submodule's upstream with
  [`push`](push.md), as for any nested repository.

## See also

- [Upstream submodules](../guides/submodules.md)
- [`init --from-submodule`](init.md): nest one submodule.
- [`clone --recurse-submodules`](clone.md): nest a repository with
  submodules in a subdirectory.
