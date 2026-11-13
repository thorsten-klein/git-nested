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

## Create

```bash
git nested patches create ext/lib
```

- `create` applies the patches on the upstream commit, with `git am`. What
  HEAD has on top becomes one more patch. Then it writes all patches again.

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

## Other commands

- `push`: pushes your changes as usual. The folder is left out.
- `diff` and `status`: the folder does not count as a local change.

## Nested repositories inside

A nested repository inside is not part of the outer patches. It can have
its own `patches` folder:

```bash
git nested config ext/lib/inner patches .gitnested.patches
```

## Limits

The patches do not work yet with:

- `filter`, `exclude` and `path`: the nested folder is then only a part of
  upstream, and the patches would have to be on that part.
- `squash: false`.

With these, `patches create` stops with a message.
