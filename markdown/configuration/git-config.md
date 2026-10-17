# git config settings

Most settings live in `.gitnested`. A few live in git config, because they
are about your own clone, not about the nested repository.

## Settings you set

### `nested.verify`

```bash
git config nested.verify true
```

By default git-nested does not run the hooks of your repository on its own
commits. Those hooks are for your changes, not for upstream content.
`nested.verify true` runs `pre-commit` and `commit-msg` on them too.

See [Hooks and signing](../guides/hooks-and-signing.md).

### `user.signingKey`

git’s own setting. `-S` uses it to pick the GPG key.

## Settings git-nested writes

You do not need to set these. They are listed so you know what they are.

### `nested.<subdir>.branchname`

The branch name from `git nested branch --name`. The other commands use it
instead of `nested/<subdir>`. `git nested clean` removes it.

### `remote.<nested-branch>.*` and `branch.<nested-branch>.*`

[`git nested branch`](../cli/branch.md) adds a git remote with the name of
the nested branch. It points at upstream:

- it fetches the tracked branch,
- it fetches no tags,
- it pushes the nested branch to the tracked branch.

So plain `git fetch`, `git pull` and `git push` work in the worktree.
`git nested clean` removes the remote.
