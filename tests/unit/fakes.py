"""Shared test doubles for unit-level tests.

Deliberately not named conftest.py. pytest registers every conftest under the
bare module name ``conftest``, so a second one here would collide in
sys.modules with tests/conftest.py -- which the whole e2e suite imports from
by that name. The full run only ever worked by collection order; naming a
unit test file first was enough to break it:

    $ pytest tests/unit tests/e2e/test_clone.py
    ImportError: cannot import name 'VERSION' from 'conftest'
"""

from __future__ import annotations

from dataclasses import dataclass

from git_nested import GitNestedError, GitRunner


@dataclass
class FakeResult:
    returncode: int = 0
    stdout: str = ''
    stderr: str = ''


class FakeGit(GitRunner):
    """A minimal GitRunner double driven by canned responses.

    Register a response for a command with `.respond(*prefix, stdout=..., ...)`; any call whose
    args start with that prefix returns it (first registered match wins). Unmatched calls raise
    AssertionError so a test with a gap fails loudly instead of falling through to real git.

    Subclasses GitRunner and overrides only `run`, so `is_tracked`, `rev_exists`,
    `branch_exists` and `commit_in_rev_list` are the *real* implementations
    driven by canned output. They used to be copies, and one had already
    drifted: is_tracked answered on the exit code, but `git ls-files` exits 0
    whether or not it matched anything, so the double called every path
    tracked while the real one asks whether there was any output.

    GitRunner.__init__ is deliberately not called -- it shells out to
    `git --version` -- so `version` is set here instead.
    """

    def __init__(self):
        self._responses: list[tuple[tuple[str, ...], FakeResult]] = []
        self.calls: list[tuple[str, ...]] = []
        self.version = '99.0.0'

    def respond(self, *prefix, stdout='', stderr='', returncode=0):
        self._responses.append((tuple(str(p) for p in prefix), FakeResult(returncode, stdout, stderr)))
        return self

    def _find_response(self, args_t: tuple[str, ...]) -> FakeResult:
        for prefix, result in self._responses:
            if args_t[: len(prefix)] == prefix:
                return result
        raise AssertionError(f"FakeGit: no response registered for: git {' '.join(args_t)}")

    def run(self, args, may_fail=False, print_error=True, **kwargs):
        args_t = tuple(str(a) for a in args)
        self.calls.append(args_t)
        result = self._find_response(args_t)
        if result.returncode != 0 and not may_fail:
            raise GitNestedError(
                f"Command failed: 'git {' '.join(args_t)}'.\n{result.stderr}", print_to_stderr=print_error
            )
        return result

    def check_output(self, args, may_fail=False, **kwargs):
        return self.run(args, may_fail=may_fail, **kwargs).stdout.strip()
