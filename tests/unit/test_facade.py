"""Guard tests for the GitNestedRepo back-compat facade.

GitNestedRepo is no longer where the logic lives -- every method became a
module-level function. These tests protect the two properties that make the
dynamic facade safe: the modules it scans export disjoint names, and
production code does not route through it.
"""

import ast
from pathlib import Path
from types import ModuleType

import pytest

from git_nested import GitNestedError, GitNestedRepo
from git_nested.repo import _MODULES

SRC = Path(__file__).resolve().parent.parent.parent / "src" / "git_nested"


def _defined_names(module: ModuleType) -> set[str]:
    """Callables `module` defines itself -- imports into it don't count."""
    return {
        name
        for name, value in vars(module).items()
        if callable(value) and getattr(value, "__module__", None) == module.__name__
    }


def test_module_scan_order_is_unambiguous():
    """No two scanned modules define the same name.

    __getattr__ returns the first match, so a duplicate would silently
    shadow one of the two definitions depending on the tuple's order.
    """
    seen: set[str] = set()
    collisions: set[str] = set()
    for module in _MODULES:
        names = _defined_names(module)
        collisions |= names & seen
        seen |= names
    assert not collisions


def test_facade_resolves_a_function_from_each_module():
    repo = GitNestedRepo()
    for module in _MODULES:
        name = min(_defined_names(module))
        assert getattr(repo, name) is getattr(module, name)


def test_facade_raises_attribute_error_for_unknown_name():
    repo = GitNestedRepo()
    with pytest.raises(AttributeError, match="no attribute 'no_such_helper'"):
        repo.no_such_helper  # noqa: B018


def test_facade_miss_is_an_attribute_error_not_a_git_nested_error():
    repo = GitNestedRepo()
    with pytest.raises(AttributeError), pytest.raises(GitNestedError):
        repo.definitely_not_here  # noqa: B018


def _is_self_repo(node: ast.expr) -> bool:
    """True for the expression `self.repo`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "repo"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _facade_call_sites(path: Path) -> list[tuple[str, str]]:
    """Every `self.repo.<name>` access in one file, as (location, name)."""
    tree = ast.parse(path.read_text())
    return [
        (f"{path.name}:{n.lineno}", n.attr)
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and _is_self_repo(n.value)
    ]


def test_no_call_site_resolves_through_the_facade():
    """Every `self.repo.<name>` must name an attribute the class really has.

    A name only __getattr__ can resolve is invisible to mypy and pyright,
    which is the whole reason the split was worth doing. The facade exists
    for downstream callers, not for us.
    """
    offenders = [
        f"{where} self.repo.{name}"
        for path in sorted(SRC.rglob("*.py"))
        for where, name in _facade_call_sites(path)
        if not hasattr(type(GitNestedRepo()), name)
    ]
    assert not offenders
