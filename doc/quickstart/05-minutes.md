# git-nested in 5 minutes

This page walks you through clone, push and pull. It uses two local
repositories, so you need no server and no account. Copy the commands into
a terminal and run them one by one.

You need git-nested installed. See [Install git-nested](../introduction/install.md).

## 1. Make an upstream repository

First make a small library. This is the "upstream": the repository you
want to nest.

```bash
mkdir /tmp/try-nested && cd /tmp/try-nested

git init -b main lib
cd lib
echo "def hello(): return 'hello'" > hello.py
git add hello.py
git commit -m "Add hello"
cd ..

# a bare copy plays the server
git clone --bare lib lib.git
```

## 2. Make your project

```bash
git init -b main app
cd app
echo "# My app" > README.md
git add README.md
git commit -m "Start app"
```

## 3. Clone the library into your project

```bash
git nested clone ../lib.git ext/lib
```

```text
ext/lib: cloned from ../lib.git (main)
```

The files of the library are now in `ext/lib/`, next to a new file
`.gitnested`:

```bash
ls -A ext/lib
```

```text
.gitnested
hello.py
```

git-nested made one commit:

```bash
git log --oneline
```

```text
e08d501 git nested clone
b2dfdc7 Start app
```

`.gitnested` remembers where the files come from:

```yaml
# This subdirectory is managed by "git nested".
# Refer to: https://github.com/thorsten-klein/git-nested#readme
#
nested:
  commit: 401b344cd6917389538657fa06cd5f007dfb664c
  method: merge  # optional: this is the default
  cmdver: 1.1.1
  remote: ../lib.git
  branch: main
  parent: b2dfdc71d112c5e7102726c32c323901a9457630
```

- `remote` and `branch` say where upstream is.
- `commit` is the upstream commit you have now.
- `parent` is your commit from just before the clone.

[The `.gitnested` file](../configuration/gitnested-file.md) explains every field.

## 4. Look at the status

```bash
git nested status
```

```text
1 nested repository:
Git nested repository 'ext/lib':
  Remote URL:      ../lib.git
  Upstream Ref:    401b344
  Tracking Branch: main
  Pulled Commit:   401b344
  Pull Parent:     b2dfdc7
  Local Commits:   0
  Behind Upstream: 0
  Content:         same
```

No local commits, nothing new upstream, same content.

## 5. Change the library in your project

Edit the nested files like any other file, and commit as usual:

```bash
echo "def bye(): return 'bye'" >> ext/lib/hello.py
git commit -am "lib: add bye"
```

`status --short` prints one line per nested repository:

```bash
git nested status --short
```

```text
ext/lib 1 0 changed
```

One local commit, nothing new upstream, the content differs from upstream.

## 6. Push the change upstream

```bash
git nested push ext/lib -b main --commit
```

```text
ext/lib: pushed to ../lib.git (main)
```

The library now has your commit:

```bash
git -C ../lib.git log --oneline
```

```text
9a38b6d lib: add bye
401b344 Add hello
```

- `-b main` pushes to the `main` branch of upstream.
- `--commit` records the pushed commit in `.gitnested`. So your project
  knows upstream has your change.

> [!TIP]
> Without `-b`, git-nested pushes to a new branch `app-main` upstream:
> the name of your project, then the tracked branch. You can then open a
> pull request there. See [`git nested push`](../cli/push.md).

## 7. Pull a change from upstream

Someone else changes the library:

```bash
cd ../lib
git pull ../lib.git main
echo "VERSION = 2" > version.py
git add version.py
git commit -m "Add version"
git push ../lib.git main
cd ../app
```

Pull it into your project:

```bash
git nested pull ext/lib
```

```text
ext/lib: pulled from ../lib.git (main)
```

The pull is one new commit. Its message lists the upstream commits it
brings in:

```bash
git log --oneline
```

```text
6659552 git nested pull
04fd4cf git nested push
2d5a867 lib: add bye
e08d501 git nested clone
b2dfdc7 Start app
```

```bash
git nested status --short
```

```text
ext/lib 0 0 same
```

Your project and the library are in step again.

## 8. Share your project

Push your project as usual. Others clone it with plain `git clone` and get
`ext/lib/` with it. They only need git-nested to pull or push the library.

## What next?

- [Everyday tasks](everyday.md): the commands you need most days.
- [How it works](../concepts/how-it-works.md): what happened in each step.
- [Command reference](../cli/index.md): all commands and options.
