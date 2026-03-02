# git-nested — Subcommand Git Call Diagrams

Each diagram below shows the sequence of underlying `git` commands executed by a `git nested` subcommand.

---

## clone

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested clone <subdir> <remote>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD
    git-nested->>Git: rev-list HEAD -1
    Note over git-nested: Validate HEAD exists

    opt No branch specified
        git-nested->>Git: ls-remote --symref <remote>
        Note over git-nested: Determine upstream default branch
    end

    rect rgb(230, 245, 255)
        Note over git-nested,Git: do_fetch
        git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
        git-nested->>Git: rev-parse FETCH_HEAD^0
        git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
    end

    Note over git-nested: mkdir <subdir>/

    rect rgb(230, 255, 230)
        Note over git-nested,Git: commit_nested_branch
        git-nested->>Git: rev-list <upstream_commit> -1
        git-nested->>Git: merge-base --is-ancestor <upstream> <nested_ref>
        git-nested->>Git: ls-files -- <subdir>
        git-nested->>Git: read-tree --prefix=<subdir> -u <nested_commit_ref>
        Note over git-nested: Write .gitnested YAML
        git-nested->>Git: rev-parse <nested_commit_ref>
        git-nested->>Git: add -f -- <subdir>/.gitnested
        git-nested->>Git: diff --cached --quiet
        git-nested->>Git: commit -m <message>
        git-nested->>Git: update-ref refs/nested/<subref>/commit <nested_commit_ref>
    end
```

---

## init

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested init <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD
    git-nested->>Git: ls-files -- <subdir>
    Note over git-nested: Validate subdir is tracked

    opt No branch specified
        git-nested->>Git: config --get init.defaultbranch
    end

    rect rgb(230, 245, 255)
        Note over git-nested,Git: update_gitrepo_file
        Note over git-nested: Write .gitnested YAML
        git-nested->>Git: rev-parse <nested_commit_ref>
        git-nested->>Git: add -f -- <subdir>/.gitnested
    end

    git-nested->>Git: add -f -- <subdir>/.gitnested
    git-nested->>Git: commit -m <message>
    git-nested->>Git: update-ref refs/nested/<subref>/commit <head_commit>
```

---

## fetch

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested fetch <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    Note over git-nested: Read .gitnested config

    rect rgb(230, 245, 255)
        Note over git-nested,Git: do_fetch
        git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
        git-nested->>Git: rev-parse FETCH_HEAD^0
        git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
    end
```

---

## pull

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested pull <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD

    rect rgb(230, 245, 255)
        Note over git-nested,Git: do_fetch
        git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
        git-nested->>Git: rev-parse FETCH_HEAD^0
        git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
    end

    alt Up to date
        Note over git-nested: Return early (no changes)
    else Has changes
        rect rgb(255, 245, 230)
            Note over git-nested,Git: delete_branch (cleanup old)
            git-nested->>Git: worktree prune
            git-nested->>Git: branch -D nested/<subref>
        end

        rect rgb(230, 245, 255)
            Note over git-nested,Git: create_nested_branch
            git-nested->>Git: rev-list nested/<subref> -1
            Note over git-nested: Check branch existence

            alt Has parent commit (incremental)
                git-nested->>Git: merge-base --is-ancestor <parent> HEAD
                git-nested->>Git: rev-list --reverse --ancestry-path --topo-order <parent>..HEAD
                loop For each commit touching subdir
                    git-nested->>Git: cat-file -p <commit>:<subdir>/.gitnested
                    git-nested->>Git: show -s --pretty=format:%P <commit>
                    git-nested->>Git: cat-file -e <commit>:<subdir>
                    git-nested->>Git: log -1 --format=%ad,%ae,%an,%cd,%ce,%cn,%B <commit>
                    git-nested->>Git: commit-tree -p <parents> <commit>:<subdir>
                end
                git-nested->>Git: branch nested/<subref> <last_commit>
            else No parent (first time)
                git-nested->>Git: branch nested/<subref> HEAD
                git-nested->>Git: filter-branch -f --subdirectory-filter <subref> nested/<subref>
            end

            git-nested->>Git: filter-branch -f --prune-empty --tree-filter 'rm -f .gitnested' -- <range>
            git-nested->>Git: worktree add <worktree_path> nested/<subref>
            git-nested->>Git: update-ref refs/nested/<subref>/branch nested/<subref>
        end

        alt method = merge
            git-nested->>Git: merge refs/nested/<subref>/fetch
            Note over git-nested: (in worktree)
        else method = rebase
            git-nested->>Git: rebase refs/nested/<subref>/fetch nested/<subref>
            Note over git-nested: (in worktree)
        end

        git-nested->>Git: update-ref refs/nested/<subref>/branch nested/<subref>

        rect rgb(230, 255, 230)
            Note over git-nested,Git: commit_nested_branch
            git-nested->>Git: rev-parse refs/nested/<subref>/fetch
            git-nested->>Git: ls-files -- <subdir>
            git-nested->>Git: rm -r -- <subdir>
            git-nested->>Git: read-tree --prefix=<subdir> -u <nested_commit_ref>
            Note over git-nested: Write .gitnested YAML
            git-nested->>Git: add -f -- <subdir>/.gitnested
            git-nested->>Git: diff --cached --quiet
            git-nested->>Git: commit -m <message>
            git-nested->>Git: worktree prune
            git-nested->>Git: update-ref refs/nested/<subref>/commit <nested_commit_ref>
        end
    end
```

---

## push

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested push <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD

    git-nested->>Git: rev-parse --show-toplevel
    Note over git-nested: Derive push branch name

    rect rgb(255, 245, 230)
        Note over git-nested,Git: Fetch target branch
        git-nested->>Git: fetch --no-tags --quiet <remote> <branch_name>
        alt Branch exists upstream
            git-nested->>Git: rev-parse FETCH_HEAD^0
            Note over git-nested: Verify no new upstream changes
        else Branch does not exist
            Note over git-nested: Mark as new upstream
        end
    end

    rect rgb(255, 245, 230)
        Note over git-nested,Git: delete_branch (cleanup)
        git-nested->>Git: worktree prune
        git-nested->>Git: branch -D nested/<subref>
    end

    rect rgb(230, 245, 255)
        Note over git-nested,Git: create_nested_branch
        git-nested->>Git: rev-list nested/<subref> -1
        Note over git-nested: (Same branch creation as in pull — see pull diagram)
        git-nested->>Git: branch nested/<subref> <commit>
        git-nested->>Git: filter-branch -f --prune-empty --tree-filter 'rm -f .gitnested' -- <range>
        git-nested->>Git: worktree add <worktree_path> nested/<subref>
        git-nested->>Git: update-ref refs/nested/<subref>/branch nested/<subref>
    end

    opt method = rebase
        git-nested->>Git: rebase refs/nested/<subref>/fetch nested/<subref>
        Note over git-nested: (in worktree)
    end

    git-nested->>Git: rev-parse nested/<subref>
    Note over git-nested: Verify new commits exist

    opt Not force & not new upstream
        git-nested->>Git: merge-base --is-ancestor <upstream_head> nested/<subref>
    end

    git-nested->>Git: push [--force] <remote> nested/<subref>:<branch_name>
    git-nested->>Git: update-ref refs/nested/<subref>/push nested/<subref>

    rect rgb(255, 245, 230)
        Note over git-nested,Git: Cleanup
        git-nested->>Git: worktree prune
        git-nested->>Git: branch -D nested/<subref>
    end

    opt --commit flag
        Note over git-nested: Update .gitnested YAML
        git-nested->>Git: add -f -- <subdir>/.gitnested
        git-nested->>Git: commit -m <message>
    end
```

---

## branch

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested branch <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD

    opt --fetch flag
        rect rgb(230, 245, 255)
            Note over git-nested,Git: do_fetch
            git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
            git-nested->>Git: rev-parse FETCH_HEAD^0
            git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
        end
    end

    opt --force flag
        git-nested->>Git: worktree prune
        git-nested->>Git: branch -D nested/<subref>
    end

    git-nested->>Git: rev-list nested/<subref> -1
    Note over git-nested: Check branch existence

    rect rgb(230, 245, 255)
        Note over git-nested,Git: create_nested_branch
        alt Has parent commit
            git-nested->>Git: merge-base --is-ancestor <parent> HEAD
            git-nested->>Git: rev-list --reverse --ancestry-path --topo-order <parent>..HEAD
            loop For each commit touching subdir
                git-nested->>Git: cat-file -p <commit>:<subdir>/.gitnested
                git-nested->>Git: show -s --pretty=format:%P <commit>
                git-nested->>Git: cat-file -e <commit>:<subdir>
                git-nested->>Git: log -1 --format=... <commit>
                git-nested->>Git: commit-tree -p <parents> <commit>:<subdir>
            end
            git-nested->>Git: branch nested/<subref> <last_commit>
        else No parent
            git-nested->>Git: branch nested/<subref> HEAD
            git-nested->>Git: filter-branch -f --subdirectory-filter <subref> nested/<subref>
        end

        git-nested->>Git: filter-branch -f --prune-empty --tree-filter 'rm -f .gitnested' -- <range>
        git-nested->>Git: worktree add <worktree_path> nested/<subref>
        git-nested->>Git: update-ref refs/nested/<subref>/branch nested/<subref>
    end
```

---

## commit

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested commit <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree
    git-nested->>Git: update-index -q --ignore-submodules --refresh
    git-nested->>Git: diff-files --quiet --ignore-submodules
    git-nested->>Git: rev-parse --verify HEAD
    git-nested->>Git: diff-index --quiet --ignore-submodules HEAD
    git-nested->>Git: diff-index --quiet --cached --ignore-submodules HEAD

    opt --fetch flag
        rect rgb(230, 245, 255)
            Note over git-nested,Git: do_fetch
            git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
            git-nested->>Git: rev-parse FETCH_HEAD^0
            git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
        end
    end

    git-nested->>Git: rev-list refs/nested/<subref>/fetch -1
    git-nested->>Git: rev-parse refs/nested/<subref>/fetch

    rect rgb(230, 255, 230)
        Note over git-nested,Git: commit_nested_branch
        git-nested->>Git: rev-list <nested_commit_ref> -1
        git-nested->>Git: merge-base --is-ancestor <upstream_head> <nested_commit_ref>
        git-nested->>Git: ls-files -- <subdir>
        git-nested->>Git: rm -r -- <subdir>
        git-nested->>Git: read-tree --prefix=<subdir> -u <nested_commit_ref>
        Note over git-nested: Write .gitnested YAML
        git-nested->>Git: rev-parse <nested_commit_ref>
        git-nested->>Git: add -f -- <subdir>/.gitnested
        git-nested->>Git: diff --cached --quiet
        git-nested->>Git: commit -m <message>
        git-nested->>Git: worktree prune
        git-nested->>Git: update-ref refs/nested/<subref>/commit <nested_commit_ref>
    end
```

---

## status

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested status
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree

    git-nested->>Git: ls-files
    Note over git-nested: Find all .gitnested files

    loop For each nested repository
        git-nested->>Git: rev-parse --short refs/nested/<subref>/fetch
        Note over git-nested: Read .gitnested config

        opt --fetch flag
            git-nested->>Git: fetch --no-tags --quiet <remote> <branch>
            git-nested->>Git: rev-parse FETCH_HEAD^0
            git-nested->>Git: update-ref refs/nested/<subref>/fetch FETCH_HEAD^0
        end

        git-nested->>Git: rev-list refs/heads/nested/<subref> -1
        Note over git-nested: Check if branch exists

        git-nested->>Git: config remote.nested/<subref>.url
        Note over git-nested: Check for remote

        git-nested->>Git: rev-parse --short <config.commit>
        git-nested->>Git: rev-parse --short <config.parent>
        git-nested->>Git: worktree list

        opt --verbose flag
            git-nested->>Git: show-ref
            git-nested->>Git: rev-parse --short <sha>
            Note over git-nested: Display all refs/nested/<subref>/*
        end
    end
```

---

## clean

```mermaid
sequenceDiagram
    participant User
    participant git-nested
    participant Git

    User->>git-nested: git nested clean <subdir>
    git-nested->>Git: rev-parse --git-dir
    git-nested->>Git: symbolic-ref --short --quiet HEAD
    git-nested->>Git: rev-parse --is-inside-work-tree

    Note over git-nested: Remove worktree (if exists)
    git-nested->>Git: worktree prune

    git-nested->>Git: rev-list refs/heads/nested/<subref> -1
    alt Branch exists
        git-nested->>Git: update-ref -d refs/heads/nested/<subref>
    end

    opt --force flag
        git-nested->>Git: show-ref
        loop For each matching ref
            git-nested->>Git: update-ref -d refs/nested/<subref>/*
            git-nested->>Git: update-ref -d refs/original/refs/heads/nested/<subref>/*
        end
    end
```
