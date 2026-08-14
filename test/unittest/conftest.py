"""Shared test doubles for unit-level tests."""

from __future__ import annotations

from dataclasses import dataclass

from git_nested import GitNestedError


@dataclass
class FakeResult:
    returncode: int = 0
    stdout: str = ''
    stderr: str = ''


class FakeGit:
    """A minimal GitRunner double driven by canned responses.

    Register a response for a command with `.respond(*prefix, stdout=..., ...)`; any call whose
    args start with that prefix returns it (first registered match wins). Unmatched calls raise
    AssertionError so a test with a gap fails loudly instead of falling through to real git.
    """

    def __init__(self):
        self._responses: list[tuple[tuple[str, ...], FakeResult]] = []
        self.calls: list[tuple[str, ...]] = []

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

    def is_tracked(self, path):
        return self.run(['ls-files', '--', path], may_fail=True).returncode == 0

    def rev_exists(self, rev):
        return self.run(['rev-list', rev, '-1'], may_fail=True).returncode == 0

    def branch_exists(self, branch):
        return self.rev_exists(f'refs/heads/{branch}')

    def commit_in_rev_list(self, commit, list_head):
        return self.run(['merge-base', '--is-ancestor', commit, list_head], may_fail=True).returncode == 0
