# git-nested

<img src="https://raw.githubusercontent.com/thorsten-klein/git-nested/main/doc/_static/logo.svg" alt="git-nested logo" width="500"/>

Put another repository into a folder of yours. Pull its new changes. Push
your changes back.

> [!NOTE]
> This site is also published as **plain Markdown**, one file per page.
> It is meant for AI tools. Start at
> <a href="markdown/index.md">markdown/index.md</a>.

## Introduction

Start here if you are new to git-nested.

- [About git-nested](introduction/index.md)
- [Install git-nested](introduction/install.md)

## Quickstart

Try it out in a few minutes.

- [git-nested in 5 minutes](quickstart/05-minutes.md)
- [Everyday tasks](quickstart/everyday.md)

## Concepts

The words git-nested uses, and how it works inside.

- [Glossary](concepts/glossary.md)
- [How it works](concepts/how-it-works.md)
- [Compared to submodule and subtree](concepts/comparison.md)

## `git nested` command

The full reference of the command line. There is one page per command.

- [Overview and common options](cli/index.md)

| Command                           | What it does                                    |
|-----------------------------------|-------------------------------------------------|
| [`clone`](cli/clone.md)           | Copy an upstream repository into a folder       |
| [`init`](cli/init.md)             | Turn a folder you have into a nested repository |
| [`pull`](cli/pull.md)             | Get the new upstream changes                    |
| [`push`](cli/push.md)             | Send your changes upstream                      |
| [`fetch`](cli/fetch.md)           | Download upstream changes, change no file       |
| [`status`](cli/status.md)         | Show all nested repositories                    |
| [`diff`](cli/diff.md)             | Compare a nested repository with upstream       |
| [`branch`](cli/branch.md)         | Build a branch with the nested history          |
| [`run`](cli/run.md)               | Run git in that branch’s worktree               |
| [`commit`](cli/commit.md)         | Add that branch back as one commit              |
| [`repair`](cli/repair.md)         | Fix the sync point after a squash merge         |
| [`clean`](cli/clean.md)           | Remove what git-nested left behind              |
| [`config`](cli/config.md)         | Read or change `.gitnested`                     |
| [`completion`](cli/completion.md) | Print the shell completion script               |
| [`version`](cli/version.md)       | Print the version                               |
- [Environment variables](cli/environment-variables.md)

## Configuration

What git-nested stores, and where.

- [The `.gitnested` file](configuration/gitnested-file.md)
- [`.gitnested` examples](configuration/examples.md)
- [git config settings](configuration/git-config.md)

## Guides

Step by step help for one task each.

- [Resolve conflicts](guides/conflicts.md)
- [Nest only a part of upstream](guides/partial.md)
- [Pin a release](guides/pin.md)
- [Upstream submodules](guides/submodules.md)
- [Adopt an existing folder](guides/adopt.md)
- [Many nested repositories at once](guides/many.md)
- [Squash merges and rebases](guides/squash-merges.md)
- [Nested repositories inside nested repositories](guides/nested-in-nested.md)
- [Hooks and signing](guides/hooks-and-signing.md)

## Architecture

How the code is built, and which git commands each command runs.

- [Architecture](architecture/index.md)
- [Git call diagrams](architecture/diagrams.md)

## Contributing

- [Development](contributing/development.md)
- [Documentation](contributing/documentation.md)
