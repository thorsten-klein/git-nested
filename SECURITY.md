# Security Policy

## Supported versions

The latest release is the supported one. Fixes go into a new release rather
than into patches for older ones.

## Reporting a vulnerability

Report privately, not as a public issue:

- Use [GitHub's private advisory form](https://github.com/thorsten-klein/git-nested/security/advisories/new).

Please include what an attacker can do, the steps to reproduce it, and the
git-nested and git versions you saw it on.

You will get an acknowledgement within a week. Once there is a fix, the
advisory is published with credit to you, unless you would rather not be
named.

## Scope

git-nested runs git on your behalf, in your repository, with your
permissions. Things worth reporting:

- a crafted `.gitnested` file, remote URL, branch or ref name that makes
  git-nested run a command it was not asked to run;
- a path in a nested repository that lets a write escape the subdirectory
  it belongs to;
- a temporary file or worktree left somewhere another user can tamper with it.

Out of scope: anything you can already do by running git yourself, and
anything requiring you to run git-nested against a repository you already
distrust while also having told git to trust it.
