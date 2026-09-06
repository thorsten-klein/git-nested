"""The shell scripts `git nested completion <shell>` prints.

Each is a shim: it collects the words typed so far and shells back out to
the hidden `__complete` subcommand, which does the real work in Python
(see this package's `__init__`). Nothing about the command set is baked
into the script, so a script printed once keeps up with the parser.

Every statement in every script ends in ';' and the trailing comment line
is last. That is what lets `eval $(git-nested completion bash)` -- unquoted,
which word-splits the whole script onto one line -- still parse: without
the ';' the statements would run together, and a '#' anywhere but the end
would comment out everything after it once the newlines are gone.
"""

from __future__ import annotations

import os
import shlex
import sys
from collections.abc import Callable
from pathlib import Path

from ..constants import COMPLETION_SHELLS


def bind_names() -> list[str]:
    """Every command word the printed script should wire completion up for.

    Always `git-nested`, the on-PATH name `git nested` itself dispatches to,
    plus however this git-nested was actually invoked and the resolved path
    behind it -- so a checkout's launcher completes the same as an installed
    console script. Order preserved, duplicates dropped.
    """
    names = ['git-nested']
    for candidate in _argv0_names():
        if candidate not in names:
            names.append(candidate)
    return names


def _argv0_names() -> list[str]:
    """How this git-nested was invoked, and the path behind it -- if that is a real file.

    sys.argv[0] is not always something a shell could have typed: under
    `python -c` it is '-c'. Anything that is not an existing file would only
    produce a `complete` line for a command word that cannot exist.
    """
    argv0 = sys.argv[0]
    if not argv0 or not Path(argv0).is_file():
        return []
    return [argv0, str(Path(argv0).resolve())]


def detect_shell() -> str:
    """Best-effort guess at the shell that invoked us, for a bare `completion`.

    The parent process is the shell itself for the two documented wirings
    (`eval "$(git-nested completion bash)"` and `git-nested completion fish |
    source`); $SHELL covers the platforms with no /proc to read. bash is the
    last resort, being the one every other shell is most likely to tolerate.
    """
    for name in (_parent_process_name(), Path(os.environ.get('SHELL', '')).name):
        if name in COMPLETION_SHELLS:
            return name
    return 'bash'


def _parent_process_name() -> str | None:
    """The command name of this process's parent, or None where that cannot be read."""
    try:
        return Path(f'/proc/{os.getppid()}/comm').read_text().strip()
    except OSError:
        return None


def _script_bash(names: list[str]) -> str:
    """The bash script: a COMPREPLY function bound to every name, plus git's own hook."""
    # `_git_nested` is the name git's own bash completion looks up for
    # `git nested <TAB>`; it shares the body, because the body reads
    # COMP_WORDS, which git's completion leaves alone.
    #
    # COMP_WORDS[0] is whatever was typed -- `git` when going through git,
    # in which case the thing to re-invoke is `git-nested` on PATH (which
    # is the only reason `git nested` resolved in the first place).
    #
    # `args` is built before IFS is touched: bash 3.2 (still macOS's system
    # bash) IFS-joins a quoted *sliced* array expansion into one word once
    # IFS has no space in it, which would hand __complete one mangled
    # argument instead of several.
    quoted = ' '.join(shlex.quote(name) for name in names)
    return (
        "_git_nested_complete() {"
        " local cmd=${COMP_WORDS[0]};"
        ' [ "${cmd##*/}" = git ] && cmd=git-nested;'
        ' local -a args=("${COMP_WORDS[@]:0:COMP_CWORD+1}");'
        " local out;"
        ' out=$("$cmd" __complete "${args[@]}" 2>/dev/null);'
        " local IFS=$'\\n';"
        " COMPREPLY=($out);"
        " };\n"
        "_git_nested() { _git_nested_complete; };\n"
        f"complete -F _git_nested_complete -o default -o bashdefault {quoted};\n"
        '# git-nested bash completion -- wire up with: eval "$(git-nested completion bash)"\n'
    )


def _script_zsh(names: list[str]) -> str:
    """The zsh script: a compadd widget bound to every name, plus git's own hook."""
    # zsh's own git completion dispatches `git nested` to a function named
    # `_git-nested`, so that one shares the body too.
    #
    # `${(@)words[1,CURRENT]}` needs the (@) flag to survive the quotes as a
    # real array -- without it zsh joins the slice into a single word and
    # __complete sees one mangled argument.
    #
    # `--describe` asks for 'candidate\tdescription' lines, which compadd -d
    # can show natively. Per compadd(1) a display string *replaces* the
    # candidate rather than annotating it, so each one is built as
    # 'value -- description' (the separator zsh's own _describe uses) and
    # left empty when there is nothing to say. `tab=$'\t'` is spelled out
    # rather than written as a literal tab byte: a real tab is an IFS
    # character, so it would not survive an unquoted `eval`.
    quoted = ' '.join(shlex.quote(name) for name in names)
    lines = [
        "_git_nested_complete() {",
        "  local cmd=${words[1]};",
        "  [[ ${cmd:t} == (git|nested) ]] && cmd=git-nested;",
        "  local -a raw values helps descriptions;",
        '  raw=("${(@f)$("$cmd" __complete --describe "${(@)words[1,CURRENT]}" 2>/dev/null)}");',
        "  local line tab=$'\\t';",
        '  for line in "${raw[@]}"; do',
        "    if [[ $line == *${tab}* ]]; then",
        '      values+=("${line%%${tab}*}");',
        '      helps+=("${line#*${tab}}");',
        "    else",
        '      values+=("$line");',
        '      helps+=("");',
        "    fi;",
        "  done;",
        "  local width=0 v;",
        '  for v in "${values[@]}"; do (( ${#v} > width )) && width=${#v}; done;',
        "  local i;",
        "  for (( i = 1; i <= $#values; i++ )); do",
        "    if [[ -n ${helps[i]} ]]; then",
        '      descriptions+=("${(r:$width:)values[i]} -- ${helps[i]}");',
        "    else",
        '      descriptions+=("");',
        "    fi;",
        "  done;",
        '  compadd -d descriptions -- "${values[@]}";',
        "};",
        "_git-nested() { _git_nested_complete; };",
        # compdef only exists once compinit has run. A user who sources
        # this from a profile that never turned the completion system on
        # should get no completion, not a "command not found".
        f"(( $+functions[compdef] )) && compdef _git_nested_complete {quoted};",
        "true;",
        '# git-nested zsh completion -- wire up with: eval "$(git-nested completion zsh)"',
    ]
    return "\n".join(lines) + "\n"


def _script_fish(names: list[str]) -> str:
    """The fish script: one `complete` entry per name, plus one for `git nested`."""
    # `-c NAME` only matches a bare command word, so a name with a '/' in it
    # (a checkout's launcher) needs `-p PATH` instead or it silently never
    # fires. `-f` keeps every file in the cwd out of git-nested's own
    # candidates; the second entry per name puts them back for `--file`,
    # whose value is a path __complete cannot enumerate.
    #
    # The current word is passed as one quoted argument: a command
    # substitution drops an empty line, so appending an unquoted
    # `(commandline -ct)` to $tokens contributes nothing at all when the
    # cursor sits after a space -- and __complete would then complete the
    # previous word a second time instead of offering what comes after it.
    # Quoting a fish variable always yields exactly one argument, empty or
    # not, which is what keeps the last word of the list the current one.
    lines = [
        "function __git_nested_complete;",
        "    set -l tokens (commandline -opc);",
        "    set -l cmd $tokens[1];",
        "    string match -qr '(^|/)git$' -- $cmd; and set cmd git-nested;",
        "    set -l cur (commandline -ct);",
        '    $cmd __complete --describe $tokens "$cur" 2>/dev/null;',
        "end;",
        "function __git_nested_expects_file;",
        "    set -l prev (commandline -opc)[-1];",
        "    contains -- $prev --file;",
        "end;",
    ]
    entries = [("-c", "git", " -n '__fish_seen_subcommand_from nested'")]
    entries += [("-p" if "/" in name else "-c", name, "") for name in names]
    for flag, name, condition in entries:
        quoted = shlex.quote(name)
        lines.append(f"complete {flag} {quoted}{condition} -f -a '(__git_nested_complete)';")
        lines.append(f"complete {flag} {quoted}{condition} -n __git_nested_expects_file -F;")
    lines.append("# git-nested fish completion -- wire up with: git-nested completion fish | source")
    return "\n".join(lines) + "\n"


_EMITTERS: dict[str, Callable[[list[str]], str]] = {
    'bash': _script_bash,
    'zsh': _script_zsh,
    'fish': _script_fish,
}


def script(shell: str, names: list[str]) -> str:
    """The completion script for `shell`, wired to every command word in `names`."""
    return _EMITTERS[shell](names)
