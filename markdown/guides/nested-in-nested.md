# Nested repositories inside nested repositories

An upstream can use git-nested itself. Then a nested repository contains
nested repositories of its own:

```text
app/                    your repository
  ext/b/                nested from upstream b
    .gitnested
    inner/              nested in b, from upstream c
      .gitnested        written by b, about c
      .gitnested.level2 written by your clone, about c
```

## Level files

When you clone `b`, git-nested finds `inner/.gitnested` in it. It writes
`inner/.gitnested.level2` next to it. One level deeper gets
`.gitnested.level3`, and so on.

A level file is a copy of the `.gitnested` next to it, but its `parent` is
empty. The `parent` in `.gitnested` belongs to the history of `b`, not to
yours.

## Pull and push the inner one

Use its path:

```bash
git nested pull ext/b/inner
git nested push ext/b/inner
```

git-nested uses the level file with the highest number. It keeps the plain
`.gitnested` up to date too. The first pull has no sync point yet, so it
may stop with conflicts. See [Resolve conflicts](conflicts.md).

## Pull and push the outer one

```bash
git nested pull ext/b
git nested push ext/b
```

Level files are never pushed upstream.

## Status

```bash
git nested status        # only the outermost: ext/b
git nested status -A     # ext/b and ext/b/inner
```

`--all` only takes the outermost repositories. `-A` takes all, for
`status` and `clean`.
