# Environment variables

git-nested reads these environment variables.

| Variable | Effect |
|---|---|
| `NO_COLOR` | Any value turns colored output off. |
| `FORCE_COLOR` | Any value turns colored output on, also in a pipe. `NO_COLOR` wins. |
| `SHELL` | [`completion`](completion.md) uses it to guess the shell, if the parent program does not tell. |

git-nested runs git. So git's own variables apply too, for example
`GIT_SSH_COMMAND` or `GIT_TRACE`. See
[git(1)](https://git-scm.com/docs/git#_environment_variables).

## For development

| Variable | Effect |
|---|---|
| `GIT_NESTED_EXE` | The tests run this executable instead of the Python module. See [Development](../contributing/development.md#the-standalone-executable). |
