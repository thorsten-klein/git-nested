# `git nested submodules`

Turn all submodules into nested repositories and keep them up to date.

```text
git nested submodules init [--recursive] [--resolve-relative <url>] [--only <path> | --ignore <path>]...
git nested submodules update [<options>] <commit>
git nested submodules update --continue
git nested submodules update --abort
```

## What it does

Use it for a repository whose submodules should be plain files. You get one
repository with all the code in it.

The repository itself stays a normal git clone of its upstream. Upstream
commits keep their SHAs and authors. Each submodule becomes a nested
repository.

- `init` nests every submodule at the commit it pins. With `--recursive`,
  it nests their submodules too. Each submodule gets one commit. With
  `--only` or `--ignore`, it nests only some of them.
- `update <commit>` merges an upstream commit, for example `upstream/main`.
  Then it changes the nested repositories the way upstream changed its
  submodules. Each changed submodule gets one commit. It does not fetch.
  If the commit is merged already, it only updates the nested
  repositories that lag behind.

`update` handles these upstream changes:

| Upstream did | `update` does |
|---|---|
| moved a pin | pull the nested repository to the new commit. Your changes stay |
| added a submodule | nest it. Its submodules too, unless a `.gitnested` says `submodules: keep` |
| removed a submodule | remove the nested repository. A warning says if you changed it |
| moved a submodule | move the folder. Your changes stay |
| changed a url | write the new `remote` to `.gitnested` |

No gitlink and no `.gitmodules` entry comes back for a nested submodule.
Nested repositories that you added yourself are not touched.

A submodule with `update = none` in `.gitmodules` stays a submodule, as in
git. git does not check those out either.

## Arguments

| Argument | Meaning |
|---|---|
| `<commit>` | `update`: what to merge. A branch like `upstream/main`, a tag, or a SHA. Fetch it first |

## Options

| Option | Meaning |
|---|---|
| `--only <path>` | `init`: nest only the submodules at or below this path. The others stay submodules. Give it more than once for more paths |
| `--ignore <path>` | `init`: nest all submodules but the ones at or below this path. Give it more than once for more paths. Not with `--only` |
| `--recursive` | `init`: nest the submodules of the submodules too, at any depth. Without it, they stay submodules. The choice goes into each `.gitnested` as [`submodules`](../configuration/gitnested-file.md), and `update` follows it |
| `--resolve-relative <url>` | `init`: resolve relative submodule urls against this url. Without it, `init` stops at a relative url |
| `--dry-run` | show what would change, also deeper down. Change nothing. It may fetch the commits it needs to look at |
| `--single-commit` | `update <commit>`: make one merge commit with all submodule changes in it |
| `--continue` | go on after a stop on conflicts |
| `--abort` | throw away an update that stopped on conflicts |
| `-S`, `--gpg-sign` | GPG-sign the commits |
| `--signoff` | add a `Signed-off-by:` trailer to the commits |

## Examples

```bash
git clone https://github.com/user/project
cd project
git nested submodules init --recursive
git fetch origin
git nested submodules update origin/main
```

### A fork

Your fork is `origin`. The project you forked is `upstream`:

```bash
git remote add upstream https://github.com/org/project
git nested submodules init --recursive
git fetch upstream
git nested submodules update upstream/main
git push origin main
```

`update` takes a tag or a SHA too. For example, to follow releases:

```bash
git fetch upstream --tags
git nested submodules update v2.0
```

### Not with `git merge` or `git pull`

Merge upstream with `update`, not with git itself. git can't put a gitlink
where a nested folder is, so a plain `git merge` stops, or brings gitlinks
into your history. If you started one, throw it away and use `update`:

```bash
git merge --abort
git nested submodules update upstream/main
```

### Relative urls

A url like `../lib.git` is relative to the url of the superproject. In a
fork, that is not `origin`. So `init` stops and asks for the url:

```bash
git nested submodules init --resolve-relative https://github.com/org/project
```

Now `../lib.git` is `https://github.com/org/lib.git`. This is only for
the first level. With `--recursive`, a deeper relative url is relative to
the url of its parent submodule, as in git. Later, `update` resolves new
relative urls against the remote of the commit it merges.

### Only some submodules

Name the paths to nest:

```bash
git nested submodules init --only lib/core --only third_party
```

This nests `lib/core` and every submodule below `third_party`. The others
stay submodules. `update` updates them as submodules.

`init` keeps `--only` and `--ignore` in `.gitmodules`, in a `[nested]`
section. So `update` leaves a new submodule out too, if `init` would have
left it out. Upstream's changes to `.gitmodules` come in for the
submodules that stay. Your own changes there stay too. On a conflict
there, the conflict lines start with `#`. So git can still read the file.

Or name the ones to keep as submodules:

```bash
git nested submodules init --ignore vendor/big
```

### See first

```bash
git nested submodules update --dry-run upstream/main
```

```text
would merge 3 commits of upstream/main
modules/core: would pull to 1a2b3c4d5e6f
modules/core/third_party/lib: would pull to 7d8e9f0a1b2c
docs: would nest at 9f8e7d6c5b4a
tools: would remove (your changes in it go too. They stay in the history)
```

### Conflicts

A conflict outside the submodules stops the merge:

```bash
git nested submodules update upstream/main
# fix the files, then
git add <files>
git nested submodules update --continue
```

A conflict inside a submodule stops it too. The message says where:

```text
modules/core: the update stopped on conflicts in src/main.c.
Fix them there, and 'git add' them:

  cd .git/tmp/nested/modules/core

Then run 'git nested submodules update --continue'. It finishes modules/core and goes on with the others.
Or throw the update away: 'git nested submodules update --abort'.
```

To give up instead:

```bash
git nested submodules update --abort
```

Nested repositories that were updated already stay updated. The stopped
one goes back. Run `git nested submodules update upstream/main` again to
update the rest.

### Keep a submodule back

Set a pin. Then `update` leaves it where it is, with a warning:

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

Your own commits never have a gitlink. Use them for builds and releases. To search for a bug with `git bisect`, add
`--first-parent`.

By default, the merge commit comes first. One commit per submodule follows.
At the merge commit, the submodules are still at their old commits. If every
commit must build, use `--single-commit`. Its message lists the submodule
changes.

## Notes

- `init` and `update` need a clean working tree. `update` needs a branch,
  not a detached HEAD.
- If upstream moves a submodule to a path you use already, it stays where
  it is. A warning says so.
- If upstream adds a submodule at a path you use already, it is not nested.
  A warning says so.
- If your `.gitattributes` would change files of a nested repository, for
  example `*.bat text eol=crlf`, git-nested adds `-text` for these files to
  `.gitattributes`. So they stay as upstream has them, as in a submodule.
  `update` keeps this block at the end of the file, also when upstream adds
  rules there.
- Push your changes to each submodule's upstream with
  [`push`](push.md), as for any nested repository.
- Changes to the upstream superproject itself are not pushed by this command.

## See also

- [Upstream submodules](../guides/submodules.md)
- [`init --from-submodule`](init.md): nest one submodule.
- [`clone --recurse-submodules`](clone.md): nest a repository with
  submodules in a subdirectory.
