# `git nested submodules`

Turn all submodules into nested repositories and keep them up to date.

```text
git nested submodules init [--recursive] [--resolve-relative <url>] [--only <path> | --ignore <path>]...
git nested submodules pull [<options>] [<remote> [<branch>]]
git nested submodules merge [<options>] <commit>
git nested submodules (pull | merge) --continue
git nested submodules (pull | merge) --abort
```

## What it does

Use it for a repository whose submodules should be plain files. You get one
repository with all the code in it.

The repository itself stays a normal git clone of its upstream. Upstream
commits keep their SHAs and authors. Each submodule becomes a nested
repository.

- `init` nests every submodule at the commit it pins. With `--recursive`,
  it nests their submodules too. Each submodule gets one commit. With `--only` or
  `--ignore`, it nests only some of them.
- `merge` merges an upstream commit. Then it changes the nested
  repositories the way upstream changed its submodules. Each changed
  submodule gets one commit. `merge` does not fetch.
- `pull` fetches, then does the same as `merge`.

`merge` and `pull` handle these upstream changes:

| Upstream did | They do |
|---|---|
| moved a pin | pull the nested repository to the new commit. Your changes stay |
| added a submodule | nest it. Its submodules too, unless a `.gitnested` says `submodules: keep` |
| removed a submodule | remove the nested repository. A warning says if you changed it |
| moved a submodule | move the folder. Your changes stay |
| changed a url | write the new `remote` to `.gitnested` |

No gitlink and no `.gitmodules` comes back. Nested repositories that you
added yourself are not touched. A real submodule that you kept stays a
submodule.

## Arguments

| Argument | Meaning |
|---|---|
| `<remote>` | `pull`: the remote to fetch from. Default: the remote of the current branch |
| `<branch>` | `pull`: the branch to fetch. Default: the name of the current branch |
| `<commit>` | `merge`: what to merge. A branch like `upstream/main`, a tag, or a SHA |

## Options

| Option | Meaning |
|---|---|
| `--only <path>` | `init`: nest only the submodules at or below this path. The others stay submodules. Give it more than once for more paths |
| `--ignore <path>` | `init`: nest all submodules but the ones at or below this path. Give it more than once for more paths. Not with `--only` |
| `--recursive` | `init`: nest the submodules of the submodules too, at any depth. Without it, they stay submodules. The choice goes into each `.gitnested` as [`submodules`](../configuration/gitnested-file.md), and `merge` and `pull` follow it |
| `--resolve-relative <url>` | `init`: resolve relative submodule urls against this url. Without it, `init` stops at a relative url |
| `--dry-run` | show what would change. Change nothing. `pull` still fetches |
| `--single-commit` | make one merge commit with all submodule changes in it |
| `--continue` | go on after a stop on conflicts |
| `--abort` | throw away a merge that stopped on conflicts |
| `-S`, `--gpg-sign` | GPG-sign the commits |
| `--signoff` | add a `Signed-off-by:` trailer to the commits |

## Examples

```bash
git clone https://github.com/user/project
cd project
git nested submodules init
git nested submodules pull
```

### A fork

Your fork is `origin`. The project you forked is `upstream`:

```bash
git remote add upstream https://github.com/org/project
git nested submodules init
git nested submodules pull upstream main
git push origin main
```

To pull with no arguments, let your branch follow upstream once. Pushes
still go to your fork:

```bash
git fetch upstream
git branch -u upstream/main
git config remote.pushDefault origin
git nested submodules pull
```

### After a `git merge`

You can also merge upstream with git itself. git stops on each changed
submodule: it can't put a gitlink where a nested folder is. Then run
`submodules pull` or `submodules merge` with no arguments. It finishes
that merge and updates the nested repositories:

```bash
git merge upstream/main
git nested submodules pull
```

Other conflicts stop it as usual. Fix them, `git add` them, then run
`git nested submodules pull --continue`.

You can also fetch first, and merge what you fetched:

```bash
git fetch upstream
git nested submodules merge --dry-run upstream/main
git nested submodules merge upstream/main
```

`merge` takes a tag or a SHA too. For example, to follow releases:

```bash
git fetch upstream --tags
git nested submodules merge v2.0
```

### Relative urls

A url like `../lib.git` is relative to the url of the superproject. In a
fork, that is not `origin`. So `init` stops and asks for the url:

```bash
git nested submodules init --resolve-relative https://github.com/org/project
```

Now `../lib.git` is `https://github.com/org/lib.git`. This is only for
the first level. With `--recursive`, a deeper relative url is relative to
the url of its parent submodule, as in git. Later, `merge` and `pull`
resolve new relative urls against the remote they merge from.

### Only some submodules

Name the paths to nest:

```bash
git nested submodules init --only lib/core --only third_party
```

This nests `lib/core` and every submodule below `third_party`. The others
stay submodules. `merge` and `pull` update them as submodules.

`init` keeps `--only` and `--ignore` in `.gitmodules`, in a `[nested]`
section. So `merge` and `pull` leave a new submodule out too, if `init`
would have left it out. Upstream's changes to `.gitmodules` come in for
the submodules that stay. Your own changes there stay too. On a conflict
there, the conflict lines start with `#`. So git can still read the file.

Or name the ones to keep as submodules:

```bash
git nested submodules init --ignore vendor/big
```

### See first

```bash
git nested submodules pull --dry-run
```

```text
would merge 3 commits of upstream/main
modules/core: would pull to 1a2b3c4d5e6f
docs: would nest at 9f8e7d6c5b4a
tools: would remove (your changes in it go too. They stay in the history)
```

### Conflicts

A conflict outside the submodules stops the merge:

```bash
git nested submodules pull
# fix the files, then
git add <files>
git nested submodules pull --continue
```

A conflict inside a submodule stops it too. The message says where the
files are:

```bash
# fix the files there, then
git -C <the folder from the message> add <files>
git nested submodules pull --continue
```

`--continue` commits that submodule. Then it goes on with the others.

To give up instead:

```bash
git nested submodules pull --abort
```

Nested repositories that were updated already stay updated.

### Keep a submodule back

Set a pin. Then `merge` and `pull` leave it where it is, with a warning:

```bash
git nested config modules/core pin 1a2b3c4
```

To follow upstream again, remove the `pin` line from
`modules/core/.gitnested`.

## History

The merge keeps the upstream commits as they are. So they still have their
submodules:

- `git checkout` of an upstream commit or tag shows empty submodule
  folders.
- `git log -p` of an upstream commit shows the submodule changes as gitlink
  changes.

Your own commits never have a gitlink. Use them for builds and releases. To
search for a bug with `git bisect`, add `--first-parent`.

By default, the merge commit comes first. One commit per submodule follows.
At the merge commit, the submodules are still at their old commits. If every
commit must build, use `--single-commit`. Its message lists the submodule
changes.

## Notes

- `init`, `merge` and `pull` need a clean working tree. `merge` and `pull`
  need a branch, not a detached HEAD.
- If upstream moves a submodule to a path you use already, it stays where
  it is. A warning says so.
- If upstream adds a submodule at a path you use already, it is not nested.
  A warning says so.
- `pull upstream/main` does not work. That is not a remote. Use
  `pull upstream main`, or `merge upstream/main`.
- If your `.gitattributes` would change files of a nested repository, for
  example `*.bat text eol=crlf`, git-nested adds `-text` for these files to
  `.gitattributes`. So they stay as upstream has them, as in a submodule.
- Push your changes to each submodule's upstream with
  [`push`](push.md), as for any nested repository.
- Changes to the upstream superproject itself are not pushed by this command.

## See also

- [Upstream submodules](../guides/submodules.md)
- [`init --from-submodule`](init.md): nest one submodule.
- [`clone --recurse-submodules`](clone.md): nest a repository with
  submodules in a subdirectory.
