function __fish_git_nested_subdirs
    git nested status -q
end

complete -c git-nested -f
complete -c git-nested -n '__fish_use_subcommand' -a 'branch clean clone commit config fetch init pull push status version'
complete -c git-nested -s h -d 'Show the command summary'
complete -c git-nested -l version -d 'Print the git-nested version number'
complete -c git-nested -l all -s a -d 'Perform command on all current nesteds'
complete -c git-nested -l ALL -s A -d 'Perform command on all nesteds and subnesteds'
complete -c git-nested -l branch -s b -d 'Specify the upstream branch to push/pull/fetch' -r
complete -c git-nested -l edit -s e -d 'Edit commit message'
complete -c git-nested -l filter -d 'Only consider specified folders of the nested repository'
complete -c git-nested -l force -s f -d 'Force certain operations'
complete -c git-nested -l fetch -s F -d 'Fetch the upstream content first'
complete -c git-nested -l method -s M -d 'Join method: '"'"'merge'"'"' (default) or '"'"'rebase'"'"'' -r
complete -c git-nested -l message -s m -d 'Specify a commit message' -r
complete -c git-nested -l file -d 'Specify a commit message file' -r
complete -c git-nested -l remote -s r -d 'Specify the upstream remote to push/pull/fetch' -r
complete -c git-nested -l squash -s s -d 'Squash commits on push'
complete -c git-nested -l update -s u -d 'Add the --branch and/or --remote overrides to .gitrepo'
complete -c git-nested -l quiet -s q -d 'Show minimal output'
complete -c git-nested -l verbose -s v -d 'Show verbose output'
complete -c git-nested -l debug -s d -d 'Show the actual commands used'
complete -c git-nested -l DEBUG -s x -d 'Turn on -x Bash debugging'
complete -c git-nested -n '__fish_seen_subcommand_from branch' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from clean' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from commit' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from config' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from fetch' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from pull' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from push' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -n '__fish_seen_subcommand_from status' -a '(__fish_git_nested_subdirs)'
complete -c git-nested -F -n '__fish_seen_subcommand_from clone'
