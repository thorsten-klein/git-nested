# Squash merges and rebases

## The problem

`parent` in `.gitnested` is your commit at which the nested folder and
upstream were last equal. `branch`, `pull` and `push` rebuild the nested
history from there.

Say you pull on a feature branch. `parent` now points at a commit of that
branch. Then the feature branch is squash-merged, or rebased. The commit
`parent` points at is not part of `main`.

## What git-nested does

It finds the sync point in your history by itself: the commit before the
one that last changed `commit` in `.gitnested`. It warns:

```text
ext/lib: the recorded sync point is not in this history; using 1a2b3c4d5 instead. 'git nested repair ext/lib' records it
```

Everything keeps working.

## Fix it for good

```bash
git nested repair ext/lib
git nested repair --all      # or all of them
```

`repair` writes the new sync point to `parent` and commits that. The
warning is gone.

## When it can not be found

If no commit in your history ever brought the folder in step with upstream,
the commands stop:

```text
the sync point recorded in ext/lib/.gitnested is no longer an ancestor of HEAD
```

Then set it yourself, to a commit where the folder held the upstream commit
in `commit`:

```bash
git nested config ext/lib parent <sha>
git commit -m "lib: fix sync point"
```

## Avoid it

Pull and push nested repositories on the main branch, not on feature
branches. Or merge feature branches with a merge commit.
