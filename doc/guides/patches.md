# Keep local changes as patches

You change a nested repository, but the changes can't go upstream yet. Keep
them as patch files in your repository.

## Set it up

The patches are on by default. Write the first one:

```bash
git nested verify ext/lib
```

`verify` writes your local changes as a patch into `ext/lib/.gitnested.patches`.
Give it a title and a description, and rename it to match. Then commit the
folder.

```bash
git add ext/lib
git commit -m "lib: keep local changes as patches"
```

Until the folder has a patch, the commands work as without patches. So a
nested repository from an older git-nested version keeps working.

Another folder, relative to the nested folder:

```bash
git nested config ext/lib patches ../patches/lib
```

A folder inside the nested folder is never pushed upstream. To turn the
patches off:

```bash
git nested config ext/lib patches false
```

## Split a patch

One patch can become two or more. Split the file by hand, give each its own
title, and name each like `git format-patch` does: `0001-Fix-the-build.patch`
for the title "Fix the build". A pull or `commit` writes the patches again
with these names, so they stay split.

## Paths that stay local

Changes in some paths need not go into a patch, for example a local config.
List them in `.gitnested`:

```yaml
nested:
  patches-ignore:
    - config/local.yaml
```

`verify` does not compare them. A pull keeps your copy, and upstream's
changes there do not come in. A push leaves them out.

## Pull

```bash
git nested pull ext/lib
```

1. git-nested checks that the patches hold all your local changes. If
   not, it stops. Run `git nested verify ext/lib` to write the missing
   patch.
2. It takes the new upstream commit.
3. It applies the patches on top, one by one, with `git am -3`.
4. It writes the patches again and commits them with the pull.

A patch that upstream already has is dropped.

### A patch does not apply

The pull stops and names the patch and a worktree. Fix it there like a
`git am` conflict:

```bash
cd .git/tmp/nested/ext/lib
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

## Other commands

- `verify`: checks the nested repository against the patches in the
  folder.
- `push`: pushes your changes as usual. The folder is left out.
- `push --commit`: upstream now has your changes. The folder is emptied.
- `clone --force`: takes upstream again, and applies the patches on top.
- `commit`: writes the patches from the nested branch.

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

With these, `verify` does not write a patch. If the folder already has a
patch, the command stops with a message.
