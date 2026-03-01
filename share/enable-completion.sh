#!/bin/bash

# Enable git-nested completion facilities
if [[ -n ${BASH_VERSION-} ]]; then

  # Try to load git completion if available
  if [[ $(type -t __load_completion 2> /dev/null) == function ]]; then
    __load_completion git
  fi

  # Bash
  if [[ $(type -t __gitcomp 2> /dev/null) == function ]]; then
    # The standard Git completion script for Bash seems to be
    # loaded. This is required because its shell function `__gitcomp`,
    # is used in this Bash completion script.

    # We can load our Bash completion facilities.
    source "$GIT_NESTED_ROOT/share/completion.bash"
  fi

elif [[ -n ${ZSH_VERSION-} ]]; then
  # Zsh
  #
  # Prepend to `fpath` the path of the directory containing our zsh
  # completion script, so that our completion script will be hooked into the
  # zsh completion system.
  fpath=("$GIT_NESTED_ROOT/share/zsh-completion" "${fpath[@]}")

  # Load the completion function and register it
  # Only if compdef is available (completion system is loaded)
  autoload -Uz _git-nested
  if (( $+functions[compdef] )); then
    compdef _git-nested git-nested
  fi
fi
