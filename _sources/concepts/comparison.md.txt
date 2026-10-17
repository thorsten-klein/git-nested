# Compared to submodule and subtree

git has two built-in ways to use another repository: `git submodule` and
`git subtree`. This page compares them with git-nested.

## Short answer

| | submodule | subtree | git-nested |
|---|---|---|---|
| Files are in your repository | no, only a link | yes | yes |
| Plain `git clone` gets everything | no | yes | yes |
| Others need access to upstream | yes | no | no |
| Remembers URL and branch | yes | no | yes, in `.gitnested` |
| Short commands | no | no | yes |
| Clean history | yes | no, many merge commits | yes, one commit per pull |
| Push changes back | yes | yes | yes |
| Fast with long history | yes | no | yes |

## git submodule

A submodule stores only a link: the URL and one commit. The files are not in
your repository.

- Everyone who clones has to run `git submodule update --init`.
- Everyone needs access to every submodule repository.
- `git pull` does not update submodules on its own.
- If the upstream repository moves or disappears, old commits can not be
  checked out any more.
- Removing or moving a submodule takes many steps.

With git-nested the files are part of your repository. A plain `git clone`
gets them, and every commit is complete.

To switch, see [`git nested init --from-submodule`](../cli/init.md).

## git subtree

A subtree copies the files in, like git-nested. But:

- It has no state file. You give the URL and branch on every command.
- Others can not see that a folder is a subtree.
- Its history has many merge commits.
- It gets slow as the history grows.

git-nested keeps the URL and branch in `.gitnested`. A pull is one commit.
Everyone can see the `.gitnested` file.

## Who needs what

**People who only use your project**
- Get everything with `git clone`.
- Do not need git-nested.
- Do not need access to upstream.

**People who pull or push nested repositories**
- Install git-nested.
- Use short commands like `git nested pull ext/lib`.
- Get tab completion.

**Maintainers**
- Get a self-contained repository.
- Can change many nested repositories in one commit.
- Need no extra setup.
