#!/bin/bash

_git_nested() {
    local _opts=" -h --help --version -a --all -A --ALL -b= --branch= -e --edit -f --force -F --fetch -M= --method= -m= --message= --file= --filter= -r= --remote= -s --squash -u --update -q --quiet -v --verbose -d --debug -x --DEBUG"
    local subcommands="branch clean clone commit config fetch init pull push status version"
    local subdircommands="branch clean commit config fetch pull push status"
    local subcommand
    subcommand="$(__git_find_on_cmdline "$subcommands")"

    if [ -z "$subcommand" ]; then
        # no subcommand yet
        # shellcheck disable=SC2154
        case "$cur" in
        -*)
            __gitcomp "$_opts"
        ;;
        *)
            __gitcomp "$subcommands"
        esac

    else

        case "$cur" in
        -*)
            __gitcomp "$_opts"
            return
        ;;
        esac

        if [[ "$subcommand" == "help" ]]; then
            __gitcomp "$subcommands"
            return
        fi

        local subdircommand
        subdircommand="$(__git_find_on_cmdline "$subdircommands")"
        if [ -n "$subdircommand" ]; then
            local git_nesteds
            git_nesteds=$(git nested status -q)
            __gitcomp "$git_nesteds"
        fi

    fi
}
