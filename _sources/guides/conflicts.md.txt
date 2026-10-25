# Resolve conflicts

A pull joins upstream changes with your local changes. If both changed the
same lines, git can not join them on its own. Then the pull stops.

## What you see

```text
git-nested: ext/lib: the pull is unfinished, git merge failed:
...

The conflicts are in a worktree of their own at .git/tmp/nested/ext%2Flib.
Resolve them there and hand the result back:

  1. cd .git/tmp/nested/ext%2Flib
  2. resolve the conflicts ('git status' lists them)
  3. 'git add' each file you resolved
  4. git commit
  5. if more conflicts appear, go back to step 2
  6. cd /path/to/your/repo
  7. git nested commit ext/lib
```

Your own working tree is not touched. The half-done merge waits in a worktree
of its own.

## Finish the pull

Follow the printed steps:

```bash
cd .git/tmp/nested/ext%2Flib
git status                 # lists the files with conflicts
# edit the files, remove the <<<<<<< ======= >>>>>>> markers
git add hello.py
git commit                 # with the rebase method: git rebase --continue
cd -
git nested commit ext/lib
```

`git nested commit` puts the result into `ext/lib`, updates `.gitnested` and
makes one commit. It also removes the worktree.

After `pull --pin <commit>`, step 7 is `git nested commit --pin=<commit> ext/lib`.
The pin then goes into `.gitnested` as well.

### With the rebase method

Step 4 is `git rebase --continue`. Repeat steps 2 to 4 until the rebase is
done. After `git nested commit`, you can push the rebased commits without
rebasing again:

```bash
git nested push ext/lib nested/ext%2Flib
```

## Give up instead

```bash
git nested clean ext/lib
```

This removes the worktree and the nested branch. Your repository is as it
was before the pull.

## Do it all by hand

You can also take each step yourself:

```bash
git nested fetch ext/lib     # get the newest upstream
git nested branch ext/lib    # build the nested branch, in a worktree
git nested run ext/lib merge refs/nested/ext/lib/fetch
# resolve the conflicts in the worktree, then commit there
git nested commit ext/lib    # add the result as one commit
git nested clean ext/lib     # remove what is left
```

## Tips

- `git nested -v pull ext/lib` shows each step. `-vv` shows every git
  command.
- A worktree left from an earlier pull blocks the next one. The error says
  so. Finish it or run `git nested clean ext/lib`.
- Your repository can not be on a `nested/...` branch while you run
  git-nested.
