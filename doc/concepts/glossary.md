# Glossary

The words this documentation uses, in alphabetical order.

**`.gitnested` file**
: A small YAML file in each nested folder. It records the upstream, the
  branch, the upstream commit and the sync point. It is committed to your
  repository, but never pushed upstream. See
  [The `.gitnested` file](../configuration/gitnested-file.md).

**join method**
: How a pull puts upstream changes and your local changes together:
  `merge` (the default) or `rebase`. Set it with `-M`, `--merge` or
  `--rebase`, or with the `method` field.

**level file**
: A `.gitnested.level2`, `.gitnested.level3`, … file. It lets you pull and
  push a nested repository that sits inside another nested repository. See
  [Nested repositories inside nested repositories](../guides/nested-in-nested.md).

**local commit**
: A commit of your repository that changes files in a nested folder, made
  after the last sync. `push` sends these upstream.

**nested branch**
: A local branch, `nested/<subdir>` by default. It holds the history of the
  nested folder as if it were its own repository. `branch`, `pull` and
  `push` build it. `clean` removes it.

**nested folder, `<subdir>`**
: The folder in your repository that holds the nested repository, for
  example `ext/lib`. The commands take it as their first argument.

**nested refs**
: Refs under `refs/nested/<subdir>/`: `fetch`, `branch`, `commit`, `push`.
  They remember the last fetched, built, committed and pushed commits.
  `git nested status -v` shows them. `git nested clean --force` removes
  them.

**nested repository**
: A folder of your repository whose content comes from another repository.
  It has a `.gitnested` file.

**parent repository**
: Your repository: the one that holds the nested folders.

**parent, sync point**
: The commit of your repository at which the nested folder and upstream
  were last equal. It is stored as `parent` in `.gitnested`. git-nested
  rebuilds the nested history from there.

**read-only**
: A nested repository you only pull. `push` refuses it. Set `readonly` to
  `true` with `git nested config`.

**review branch**
: The branch `push` uses upstream when you give no `-b`:
  `<parent repository name>-<tracked branch>`, for example `app-main`. You
  can open a pull request from it.

**squash**
: By default a pull makes one commit in your repository. With
  `--no-squash` the upstream commits are kept too, as the second parent of
  that commit.

**tracked branch**
: The upstream branch a nested repository follows. It is stored as
  `branch` in `.gitnested`.

**upstream**
: The other repository: the one whose content is nested. Its URL or path
  is stored as `remote` in `.gitnested`.

**upstream commit**
: The commit of upstream that the nested folder is based on. It is stored
  as `commit` in `.gitnested`.

**worktree**
: A second working folder of your repository, made with `git worktree`.
  git-nested checks out the nested branch there, under
  `.git/tmp/nested/<subdir>` by default. You resolve conflicts there.
