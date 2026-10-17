# The `.gitnested` file

Each nested repository has a `.gitnested` file at its top. It records where
the content comes from, and how far it is in step with upstream.

- It is committed to your repository.
- It is never pushed upstream.
- It is YAML. All fields sit under `nested:`.

Read and change it with [`git nested config`](../cli/config.md), not by
hand.

## Example

```yaml
# This subdirectory is managed by "git nested".
# Refer to: https://github.com/thorsten-klein/git-nested#readme
#
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: merge  # optional: this is the default
  cmdver: 1.1.1
  remote: https://github.com/user/lib
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

## Fields

Fields that are not set take their default. A new `.gitnested` marks the
lines that only repeat the default with `# optional: this is the default`.
You can delete these lines. git-nested keeps the marks while the file has
any.

| Field | Default | Set by | Writable with `config` |
|---|---|---|---|
| [`remote`](#remote) | required | clone, init, `-u` | yes |
| [`branch`](#branch) | required | clone, init, `-u` | yes |
| [`commit`](#commit) | empty | clone, pull, push `--commit` | no |
| [`parent`](#parent) | empty | clone, pull, push `--commit`, repair | yes |
| [`method`](#method) | `merge` | clone, init, `-M` | yes |
| [`squash`](#squash) | `true` | you | yes |
| [`filter`](#filter) | all files | clone `--filter` | no |
| [`exclude`](#exclude) | nothing | clone `--exclude` | no |
| [`path`](#path) | the whole upstream | clone `--path` | no |
| [`pin`](#pin) | empty | clone `--pin`, pull `--pin` | yes |
| [`readonly`](#readonly) | `false` | you | yes |
| [`cmdver`](#cmdver) | | every write | no |

### `remote`

The upstream repository: a URL or a path. A relative path is relative to the
top of your repository.

`none` means there is no upstream yet. `fetch`, `diff` and `status` skip
it. `init` without `-r` writes `none`.

### `branch`

The upstream branch to follow. `-b` changes it for one command. `-b` with
`-u` changes it for good.

A tag or a commit works too. Then there is nothing new to pull.

### `commit`

The upstream commit your files are based on. Each pull updates it. A push
updates it only with `--commit`.

### `parent`

The sync point: your commit at which the nested files and upstream were
last equal. git-nested rebuilds the nested history from there.

A squash merge or a rebase can leave it on a history you do not have any
more. See [Squash merges and rebases](../guides/squash-merges.md).

### `method`

How upstream changes and your changes are joined: `merge` or `rebase`. See
[How it works](../concepts/how-it-works.md#what-does-merge-or-rebase-mean-here).

### `squash`

`true`: a pull makes one plain commit. `false`: a pull keeps the upstream
commits as the second parent of the pull commit, like `pull --no-squash`.

`false` does not work together with `filter`, `exclude` or `path`.

### `filter`

A list of paths of upstream to nest. Everything else is left out. Each entry
is a file, a folder, or a regular expression that must match the whole path.

```yaml
nested:
  filter:
  - src
  - LICENSE
  - docs/.*\.md
```

See [Nest only a part of upstream](../guides/partial.md).

### `exclude`

A list of paths of upstream to leave out: files or folders. A push never
deletes them upstream.

### `path`

One folder of upstream. Its content is nested at the top of the nested
folder. A push puts your changes back under it.

### `pin`

A commit or tag on `branch`. A pull stays there instead of taking the
newest commit. `pull --pin <new>` moves it. See
[Pin a release](../guides/pin.md).

### `readonly`

`true` makes `push` refuse. With `--all` the repository is skipped. Use it
for code you only take from upstream.

### `cmdver`

The git-nested version that last wrote the file. For information only.

## Level files

A nested repository can contain nested repositories of its own. Then
git-nested writes `.gitnested.level2`, `.gitnested.level3`, … next to their
`.gitnested`. See
[Nested repositories inside nested repositories](../guides/nested-in-nested.md).

## Line endings

git-nested writes the file with LF line endings and UTF-8 on every system.
So it is the same on Windows and Linux.
