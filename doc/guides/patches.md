# Make your changes to nested repositories visible

You change a nested repository, but the changes can't go upstream yet. Keep
them as patch files in your repository to make your changes visible.

## Set it up

The patches are off by default. Turn them on with a folder, relative to
the nested folder:

```bash
git nested config ext/lib patches .gitnested.patches
```

A folder inside the nested folder is never pushed upstream. Write the first patch:

```bash
git nested patches create ext/lib
```

It writes your local changes as a patch into the folder, with a TODO
title. Fill in the title and the description, and run it again: it names
the file after the title. Then commit the folder.

```bash
git nested patches create ext/lib
git add ext/lib/.gitnested.patches
git commit -m "lib: keep local changes as patches"
```

Until the folder has a patch, the other commands work as without patches.
So a nested repository from an older git-nested version keeps working.

To turn the patches off again:

```bash
git nested config ext/lib patches false
```

## The format

Each file in the folder ends in `.patch` and is a `git format-patch` file:
a header with author and subject, then the diff. Other files are ignored.
`git am` also takes a patch from `hg export`.

`patches create` writes all patches in one form: no commit id, no
signature, and a name made from the title. So a patch only changes when
its content changes. A plain diff, without the header, is refused.

## Create and check

```bash
git nested patches create ext/lib
git nested patches verify ext/lib
```

- `create` applies the patches on the upstream commit, with `git am`. What
  HEAD has on top becomes one more patch. Then it writes all patches again.
- `verify` only checks. It fails if a change is not in a patch, or if
  `create` would change a patch.

## Split a patch

One patch can become two or more. Split the file by hand and give each
part its own title. Then run `patches create`: it names each file after its
title. The patches stay split from then on.

## Common tasks

### Keep a local fix

Change the files, commit, and write the patch:

```bash
vi ext/lib/src/a.c
git commit -am "lib: fix the build"
git nested patches create ext/lib
```

Fill in the title and the description. Run `patches create` again to name
the file, and commit it:

```bash
sed -i 's/TODO: title/Fix the build/; s/TODO: description/We build with -Werror./' \
    ext/lib/.gitnested.patches/0001-TODO-title.patch
git nested patches create ext/lib
git add ext/lib/.gitnested.patches
git commit -m "lib: keep the build fix as a patch"
```

### Check the patches in CI

```bash
git nested patches verify --all
```

### Update to a new upstream version

```bash
git nested pull ext/lib
```

The patches go on top of the new version. A patch that upstream has
merged in the meantime is dropped.

### Drop a patch

```bash
git nested patches drop ext/lib 0002-Old-workaround.patch
```

It removes the patch and its changes from `ext/lib`, writes the other
patches again and commits both.

### Look at the patches as commits

```bash
git nested branch --from-patches ext/lib
git nested run ext/lib log --format='%h %an %s'
```

The branch holds the upstream commit and one commit per patch. It fails if
the patches do not give what HEAD has in `ext/lib`.

### Offer one patch upstream

Build the branch, put the one patch on upstream, and push it to a new
branch. The remote has the name of the branch:

```bash
git nested branch --from-patches ext/lib
cd .git/tmp/nested/ext%2Flib
git fetch
git switch -c fix-build nested/ext%2Flib/main
git cherry-pick ':/Fix the build'
git push nested/ext%2Flib fix-build
cd -
git nested clean ext/lib
git branch -D fix-build
```

Then open a pull request for `fix-build` upstream. Once it is merged, the
next pull drops the patch.

## Pull

```bash
git nested pull ext/lib
```

1. git-nested checks that the patches hold all your local changes. If
   not, it stops. Run `git nested patches create ext/lib` to write the
   missing patch.
2. It takes the new upstream commit.
3. It applies the patches on top, one by one, with `git am -3`.
4. It writes the patches again and commits them with the pull.

A patch that upstream already has is dropped.

### A patch does not apply

The pull stops and names the patch and a worktree. Fix it there like a
`git am` conflict:

```bash
cd .git/tmp/nested/ext%2Flib
# fix the files
git add <file>
git am --continue
cd -
git nested commit ext/lib
```

If a later patch conflicts too, `git am --continue` stops there. Fix it the
same way and continue, until all patches are applied. Then run
`git nested commit`.

The patches are written again from the result, one per patch. Patches you
split stay split.

## Paths that stay local

Changes in some paths need not go into a patch, for example a local config.
List them in `.gitnested`:

```yaml
nested:
  patches-ignore:
    - config/local.yaml
```

`patches create` and `patches verify` leave them out. A pull keeps your
copy, and upstream's changes there do not come in. A push leaves them out.

## Patches that stay local

Some patches will never go upstream. A push leaves them out if:

- `.gitnested` lists them, by file name:

  ```yaml
  nested:
    patches-local:
      - 0003-Use-our-CI-image.patch
  ```

  A name with no patch file is an error. After a patch is renumbered or
  renamed, fix the list.

- or their title starts with `git-nested local:`, for example
  `git-nested local: Use our CI image`.

The push sends upstream plus the other patches. `push --commit` keeps only
the local patches in the folder, on top of the new upstream commit.
`push --dry-run` lists them. If a pushed patch needs a local one, the push
stops and sends nothing.

## Other commands

- `push`: pushes your changes as usual. The folder is left out.
- `push --commit`: upstream now has your changes. The folder keeps only the
  patches that stay local.
- `clone --force`: starts over. It takes upstream again and empties the
  folder, so the local changes are gone.
- `commit`: writes the patches from the nested branch.
- `branch --from-patches`: builds the nested branch from upstream and the
  patches, one commit per patch. It stops if the patches do not give what
  HEAD has.
- `diff` and `status`: the folder does not count as a local change.

## Nested repositories inside

A nested repository inside is not part of the outer patches. A pull keeps
it as it is. It can have its own `patches` folder:

```bash
git nested config ext/lib/inner patches .gitnested.patches
```

## Limits

The patches do not work yet with:

- `filter`, `exclude` and `path`: the nested folder is then only a part of
  upstream, and the patches would have to be on that part.
- `pull --no-squash` and `squash: false`: such a pull keeps upstream's
  history, and the patches are applied on a squashed upstream commit.
- `pull --ignore`: use [`patches-ignore`](#paths-that-stay-local) instead.

With these, `patches create` and `patches verify` stop with a message. If
the folder already has a patch, the other commands stop too.
