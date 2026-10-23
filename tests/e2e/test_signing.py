"""Tests for --signoff and --gpg-sign"""

import sys

import pytest
from conftest import cmd_git_nested

# git asks gpg.program for a signature; this one makes a fake one. Like gpg, it
# prints another status line before SIG_CREATED: older git (e.g. 2.34) only finds
# SIG_CREATED after a newline.
FAKE_GPG = """#!/bin/sh
cat > /dev/null
echo '[GNUPG:] BEGIN_SIGNING H8' >&2
echo '[GNUPG:] SIG_CREATED D 1 8 00 0 FAKE' >&2
printf -- '-----BEGIN PGP SIGNATURE-----\\nfake\\n-----END PGP SIGNATURE-----\\n'
"""


def test_signoff_adds_the_trailer(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'

    cmd_git_nested(['clone', '--signoff', (env.upstream / 'bar').as_posix()], foo)

    message = env.run(['git', 'log', '-1', '--format=%B'], cwd=foo).output
    assert "Signed-off-by: FooUser <foo@foo>" in message


@pytest.mark.skipif(sys.platform == 'win32', reason="git can't run a shell script as gpg.program here")
def test_gpg_sign_signs_the_commit_and_the_nested_commits(foo_bar_cloned_and_nested, tmp_path):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    gpg = tmp_path / 'fake-gpg'
    gpg.write_text(FAKE_GPG)
    gpg.chmod(0o755)
    env.run(['git', 'config', 'gpg.program', gpg.as_posix()], cwd=foo)
    env.run(['git', 'config', 'user.signingKey', 'FAKE'], cwd=foo)
    env.add_new_files('bar/from-foo', cwd=foo)

    cmd_git_nested('branch -S bar', cwd=foo)

    nested_tip = env.run(['git', 'cat-file', '-p', 'nested/bar'], cwd=foo).output
    assert 'gpgsig -----BEGIN PGP SIGNATURE-----' in nested_tip
    cmd_git_nested(['clone', '-S', (env.upstream / 'bar').as_posix(), 'bar2'], foo)
    assert 'gpgsig ' in env.run(['git', 'cat-file', '-p', 'HEAD'], cwd=foo).output
