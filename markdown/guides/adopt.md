# Adopt an existing folder

Your repository already has a copy of an upstream in `ext/lib`. Maybe
someone copied it in by hand. Now you want to pull and push it with
git-nested, without replacing the files.

## The files match an upstream commit

```bash
git nested clone --adopt https://github.com/user/lib ext/lib
```

git-nested looks for the newest upstream commit with exactly the same files.
It records that commit, records your `HEAD` as `parent`, and commits only the
new `.gitnested`. Your files stay as they are.

If no upstream commit matches, it stops. Then use the next way.

## You know the upstream commit

Maybe you changed the files after you copied them. Then no commit matches
exactly. If you know which upstream commit you started from:

```bash
git nested init ext/lib -r https://github.com/user/lib --commit abc123
```

git-nested records `abc123`. Your changes since then count as local changes.
The next pull joins them with upstream. The next push sends them.

## You do not know the commit

Find it with git first, for example by date or by a version file. Or give up
the local changes and clone again:

```bash
git rm -r ext/lib
git commit -m "Remove copy of lib"
git nested clone https://github.com/user/lib ext/lib
```

## Notes

- git must track the files in `ext/lib`.
- `--adopt` can not be used with `--filter` or `--recurse-submodules`.
