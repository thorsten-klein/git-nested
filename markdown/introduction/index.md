# About git-nested

git-nested puts another git repository into a folder of your repository.
The files are ordinary files in ordinary commits. You can still pull new
changes from the other repository, and push your changes back to it.

## What problem does it solve?

Many projects use code from other repositories: a library, shared build
scripts, a firmware SDK. git has two tools for this, and both have problems:

- **git submodule** only stores a link to the other repository. Everyone
  who clones your project has to run extra commands. Everyone needs access
  to the other repository. If it moves or disappears, your history breaks.
- **git subtree** copies the files in. But it has no state file. You have
  to type the URL and branch on every command. Its history gets messy, and
  it gets slow with many commits.

git-nested copies the files in, like subtree. A small file, `.gitnested`,
remembers where they came from. So the commands stay short:

```bash
git nested clone https://github.com/user/lib ext/lib
git nested pull ext/lib
git nested push ext/lib
```

See [Compared to submodule and subtree](../concepts/comparison.md) for the
details.

## How it works, in short

1. `git nested clone` fetches the other repository. It copies its files into
   your folder and makes one commit. It writes `ext/lib/.gitnested` with the
   URL, the branch and the upstream commit.
2. You work on your project as usual. You may change files in `ext/lib/` too.
3. `git nested pull` fetches the new upstream commits. It joins them with
   your local changes and makes one commit.
4. `git nested push` rebuilds the history of `ext/lib/` as if it were its own
   repository, and pushes it upstream.

[How it works](../concepts/how-it-works.md) explains each step.

## Who has to install git-nested?

Only the people who pull or push nested repositories. Everyone else clones
your project with plain `git clone` and gets all files. There is nothing to
set up, and no access to the other repositories is needed.

## Why use it?

- **Self-contained.** Your repository has all files. Every commit is
  complete.
- **Simple.** The commands feel like git. The URL and branch are stored
  once.
- **Clean history.** By default one pull is one commit.
- **Flexible.** Each branch of your project can have its nested
  repositories in another state.
- **Safe to try.** Everything is a normal commit. `git reset` undoes it.

## Where it comes from

git-nested is based on [git-subrepo](https://github.com/ingydotnet/git-subrepo)
by Ingy döt Net. It is a rewrite in Python, with many new features.

## Next steps

- [Install git-nested](install.md)
- [git-nested in 5 minutes](../quickstart/05-minutes.md)
