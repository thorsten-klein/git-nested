# `.gitnested` examples

This page shows how `.gitnested` looks in common cases. Each example comes
in YAML and in TOML. Both mean the same.

- YAML is the default.
- TOML needs Python 3.11 or newer. See
  [The `.gitnested` file](gitnested-file.md#toml).
- [The `.gitnested` file](gitnested-file.md) explains every field.

git-nested writes most fields itself. You set the others with
[`git nested config`](../cli/config.md) or with options of `clone`.

## After a clone

```bash
git nested clone https://github.com/user/lib ext/lib
```

YAML:

```yaml
# This subdirectory is managed by "git nested".
# Refer to: https://github.com/thorsten-klein/git-nested#readme
#
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: merge
  cmdver: 1.1.1
  remote: https://github.com/user/lib
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

TOML:

```toml
# This subdirectory is managed by "git nested".
# Refer to: https://github.com/thorsten-klein/git-nested#readme
#
[nested]
commit = "401b344cd6917389538657fa06cd5f007dfb664c"
method = "merge"
cmdver = "1.1.1"
remote = "https://github.com/user/lib"
branch = "main"
parent = "b2dfdc71d112c5e7102726c32c323901a9457630"
```

The examples below leave out the comment lines on top.

## The smallest file

Only `remote` and `branch` are needed. git-nested fills in the rest on the
next pull.

YAML:

```yaml
nested:
  remote: https://github.com/user/lib
  branch: main
```

TOML:

```toml
[nested]
remote = "https://github.com/user/lib"
branch = "main"
```

## No upstream yet

```bash
git nested init ext/lib
```

`init` without `-r` writes the remote `none`. Set the real remote later
with `git nested config ext/lib remote <url>`.

YAML:

```yaml
nested:
  commit: ''
  method: merge
  cmdver: 1.1.1
  remote: none
  branch: main
```

TOML:

```toml
[nested]
commit = ""
method = "merge"
cmdver = "1.1.1"
remote = "none"
branch = "main"
```

## Rebase, keep the upstream commits, never push

```bash
git nested clone --rebase https://github.com/user/lib ext/lib
git nested config ext/lib squash false
git nested config ext/lib readonly true
```

- `method: rebase` puts your changes on top of upstream.
- `squash: false` keeps the upstream commits in your history.
- `readonly: true` makes `push` refuse.

YAML:

```yaml
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: rebase
  cmdver: 1.1.1
  remote: https://github.com/user/lib
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
  squash: 'false'
  readonly: 'true'
```

TOML:

```toml
[nested]
commit = "401b344cd6917389538657fa06cd5f007dfb664c"
method = "rebase"
cmdver = "1.1.1"
remote = "https://github.com/user/lib"
branch = "main"
parent = "b2dfdc71d112c5e7102726c32c323901a9457630"
squash = "false"
readonly = "true"
```

`true` and `false` also work without quotes.

## Only a part of upstream

```bash
git nested clone --filter src --filter 'docs/.*\.md' --exclude src/tests https://github.com/user/lib ext/lib
```

- `filter` lists what to take. A regular expression must match the whole
  path.
- `exclude` lists what to leave out.

YAML:

```yaml
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: merge
  cmdver: 1.1.1
  filter:
  - src
  - docs/.*\.md
  exclude:
  - src/tests
  remote: https://github.com/user/lib
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

TOML:

```toml
[nested]
commit = "401b344cd6917389538657fa06cd5f007dfb664c"
method = "merge"
cmdver = "1.1.1"
filter = ["src", "docs/.*\\.md"]
exclude = ["src/tests"]
remote = "https://github.com/user/lib"
branch = "main"
parent = "b2dfdc71d112c5e7102726c32c323901a9457630"
```

In a TOML string, `\` is written `\\`.

See [Nest only a part of upstream](../guides/partial.md).

## One folder of upstream

```bash
git nested clone --path lib/python https://github.com/user/monorepo ext/lib
```

The content of `lib/python` is at the top of `ext/lib`.

YAML:

```yaml
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: merge
  cmdver: 1.1.1
  path: lib/python
  remote: https://github.com/user/monorepo
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

TOML:

```toml
[nested]
commit = "401b344cd6917389538657fa06cd5f007dfb664c"
method = "merge"
cmdver = "1.1.1"
path = "lib/python"
remote = "https://github.com/user/monorepo"
branch = "main"
parent = "b2dfdc71d112c5e7102726c32c323901a9457630"
```

## Pinned to a release

```bash
git nested clone --pin v2.1.0 https://github.com/user/lib ext/lib
```

A pull stays at `v2.1.0`. `git nested pull ext/lib --pin v2.2.0` moves on.

YAML:

```yaml
nested:
  commit: 9a38b6d7c1e04f2b8d5a6e3f1c2b4a7d8e9f0a1b
  method: merge
  cmdver: 1.1.1
  pin: v2.1.0
  remote: https://github.com/user/lib
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

TOML:

```toml
[nested]
commit = "9a38b6d7c1e04f2b8d5a6e3f1c2b4a7d8e9f0a1b"
method = "merge"
cmdver = "1.1.1"
pin = "v2.1.0"
remote = "https://github.com/user/lib"
branch = "main"
parent = "b2dfdc71d112c5e7102726c32c323901a9457630"
```

See [Pin a release](../guides/pin.md).
