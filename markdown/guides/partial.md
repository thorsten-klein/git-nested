# Nest only a part of upstream

Sometimes you need only some files of upstream. git-nested has three ways to
pick them. You choose them at clone time.

| Option             | Use it to                                              |
|--------------------|--------------------------------------------------------|
| `--exclude <path>` | leave a few paths out, for example test data           |
| `--filter <path>`  | keep only a few paths                                  |
| `--path <dir>`     | take one folder of upstream as the whole nested folder |

Each choice is stored in `.gitnested`. `pull` and `push` follow it.

## Leave paths out: `--exclude`

```bash
git nested clone --exclude tests --exclude docs/big.pdf https://github.com/user/lib ext/lib
```

- Each `--exclude` is a file or a folder of upstream.
- `pull` keeps them out.
- `push` never deletes them upstream.

## Keep only some paths: `--filter`

```bash
git nested clone --filter src --filter LICENSE https://github.com/user/lib ext/lib
```

Each `--filter` is one of:

- a file of upstream,
- a folder of upstream, with everything in it,
- a regular expression. It must match the whole path, for example
  `docs/.*\.md`.

A push gives back the files you left out, as they are upstream. So they are
not deleted there.

You can use `--filter` and `--exclude` together. Then git-nested keeps what
the filter selects, minus the excluded paths.

## One folder: `--path`

Upstream has `javascript/`, and you want only that, as `ext/js/`:

```bash
git nested clone --path javascript https://github.com/user/lib ext/js
```

- `ext/js/` holds what upstream has in `javascript/`.
- `pull` takes only that folder.
- `push` puts your changes back under `javascript/`.

`--path` can not be used with `--filter`.

## Limits

- `pull --no-squash` and `squash: false` do not work with any of these. The
  upstream commits would bring back the files you left out.
- `filter`, `exclude` and `path` can not be changed with `git nested config`.
  To change them, clone again:

```bash
git nested clone --force --exclude tests https://github.com/user/lib ext/lib
```
