# `git nested status`

Report on the nested repositories of this repository.

```text
git nested status [<options>]
```

## What it does

`status` lists every nested repository: where it comes from, how many local
commits it has, how many upstream commits are not pulled yet, and whether
its content differs from upstream.

It reads only. It changes nothing.

## Options

| Option          | Meaning                                                 |
|-----------------|---------------------------------------------------------|
| `-a`, `--all`   | all nested repositories. This is the default            |
| `-A`, `--ALL`   | also the nested repositories inside nested repositories |
| `-F`, `--fetch` | fetch each upstream first                               |
| `--short`       | one line per repository                                 |

The global `-q` prints only the paths. The global `-v` adds the
[nested refs](../concepts/glossary.md).

## Examples

```bash
git nested status
git nested status -F         # fetch first
git nested status --short
git nested -q status         # paths only
git nested -v status         # with refs
```

## Output

```text
1 nested repository:
Git nested repository 'ext/lib':
  Remote URL:      https://github.com/user/lib
  Upstream Ref:    f7e58a0
  Tracking Branch: main
  Pulled Commit:   cce0a6f
  Pull Parent:     b6b2cb9
  Local Commits:   1
  Behind Upstream: 1
  Content:         changed
```

| Line              | Meaning                                                                                      |
|-------------------|----------------------------------------------------------------------------------------------|
| `Nested Branch`   | the nested branch, if it exists                                                              |
| `Remote Name`     | the git remote `branch` made, if it exists                                                   |
| `Remote URL`      | `remote` in `.gitnested`                                                                     |
| `Upstream Ref`    | the last fetched upstream commit                                                             |
| `Tracking Branch` | `branch` in `.gitnested`                                                                     |
| `Pulled Commit`   | `commit` in `.gitnested`: the upstream commit you have                                       |
| `Pull Parent`     | `parent` in `.gitnested`: the sync point                                                     |
| `Worktree`        | the worktree of the nested branch, if there is one                                           |
| `Local Commits`   | your commits in the folder since the sync point. Clone, pull and repair commits do not count |
| `Behind Upstream` | fetched upstream commits you have not pulled yet                                             |
| `Content`         | `same` or `changed`, compared with the upstream commit you have                              |

`Behind Upstream` counts only what was fetched. Use `-F` for fresh numbers.

### `--short`

```text
<subdir> <local commits> <upstream commits not pulled> <changed|same>
```

```text
ext/lib 1 0 changed
ext/util 0 3 same
```

A `-` means git-nested can not tell. For example, nothing was fetched yet,
or the sync point is not in your history.

## See also

- [`diff`](diff.md): see the changes themselves.
- [`fetch`](fetch.md)
