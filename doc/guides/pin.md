# Pin a release

You want a release of upstream, not its newest commit. There are two ways.

## Track a tag

```bash
git nested clone -b v1.2 https://github.com/user/lib ext/lib
```

`branch` is now `v1.2`. A tag does not move, so there is nothing new to
pull. To update, switch to the next tag:

```bash
git nested pull -b v1.3 -u ext/lib
```

## Track the branch, stay at a release

```bash
git nested clone -b main --pin v1.2 https://github.com/user/lib ext/lib
```

`branch` stays `main`, and `pin` is `v1.2`.

- git-nested checks that `v1.2` is on `main`.
- A normal `pull` stays at the pin.
- `push` still works, against `main`.

Move the pin forward:

```bash
git nested pull --pin v1.3 ext/lib
```

This is a normal pull to `v1.3`, with a merge. Your local changes stay.

Change the pin without pulling:

```bash
git nested config ext/lib pin v1.3
git commit -m "lib: pin v1.3"
```

Remove the pin to follow `main` again:

```bash
git nested config ext/lib pin ""
git commit -m "lib: follow main"
git nested pull ext/lib
```

A pin can be a tag or a commit.
