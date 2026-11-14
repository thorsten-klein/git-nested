# Hooks and signing

## Hooks

git-nested does not run the hooks of your repository on its own commits.
Your hooks are for your own changes. Upstream content may not pass them, and
it is not yours to fix.

To run `pre-commit` and `commit-msg` on git-nested's commits too:

```bash
git config nested.verify true
```

If a hook then rejects a commit, the command stops and undoes its staged
changes. Nothing else is lost, because the working tree was clean before.

The `post-checkout` hook never runs for the worktrees git-nested makes.

## Sign-off

`--signoff` adds a `Signed-off-by:` trailer to the commit git-nested makes:

```bash
git nested pull --signoff ext/lib
```

`clone`, `init`, `pull`, `push`, `commit` and `repair` take it.

## GPG signing

`-S` signs the commit git-nested makes with GPG:

```bash
git nested pull -S ext/lib
```

For `branch`, `pull` and `push`, `-S` also signs the nested commits it
rebuilds. So a push sends signed commits upstream.

git's `user.signingKey` picks the key:

```bash
git config user.signingKey <key-id>
```

`clone`, `init`, `pull`, `push`, `commit`, `repair` and `branch` take `-S`.
