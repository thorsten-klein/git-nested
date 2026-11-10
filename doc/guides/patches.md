# Keep local changes as patches

You change a nested repository, but the changes can't go upstream yet. Keep
them as patch files in your repository.

## Set it up

```bash
git nested config ext/lib patches .gitnested.patches
git nested verify ext/lib
```

`verify` writes your local changes as a patch into the folder. Give it a
title and a description, and rename it to match. Then commit the folder.

```bash
git add ext/lib
git commit -m "lib: keep local changes as patches"
```

The path is relative to the nested folder. A folder inside it is never
pushed upstream.

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

The patches are written again from the result.

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

Not supported yet:

- `filter`, `exclude` and `path`
- `pull --no-squash`, and `squash: false`
- `pull --ignore`
