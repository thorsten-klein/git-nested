# Many nested repositories at once

## `--all`

Many commands take `--all`. They then run once for each nested repository:

```bash
git nested fetch --all
git nested pull --all
git nested push --all
git nested diff --all
git nested branch --all
git nested repair --all
git nested clean --all
```

`--all` only takes the outermost nested repositories. A nested repository
inside another one is handled with the outer one.
`status` and `clean` also take `-A` to list or clean the inner ones too.

## One commit for all: `--single-commit`

By default each pull makes its own commit. To make one commit for all:

```bash
git nested pull --all --single-commit
```

The message lists each nested repository:

```text
git nested pull --all

- ext/lib
- ext/util
```

`-m` sets another message.

## One branch across all: `--all -b`

Many repositories may share a branch name, for example `release/2.0`. Use
it for all of them at once:

```bash
git nested fetch --all -b release/2.0
git nested pull --all -b release/2.0
git nested push --all -b release/2.0
```

A repository whose upstream has no such branch is skipped:

```text
ext/util: skipped, https://github.com/user/util has no branch release/2.0
```

Add `-u` to `pull` to make the new branch the tracked branch:

```bash
git nested pull --all -b release/2.0 -u
```

`-b` with `--all` only works for `fetch`, `pull` and `push`.

## Read-only repositories

`push --all` skips repositories with `readonly: true`. See
[`readonly`](../configuration/gitnested-file.md#readonly).

## Scripts

`status --short` prints one line per repository. It is easy to read in a
script:

```bash
git nested status -F --short | while read -r subdir local behind content; do
  [ "$behind" != 0 ] && [ "$behind" != - ] && echo "$subdir has $behind new upstream commits"
done
```
