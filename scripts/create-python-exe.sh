#!/usr/bin/env bash
#
# Build the single-file 'git-nested' executable: the git_nested module, PyYAML
# and a CPython interpreter, all in one file. The result needs nothing
# preinstalled on the target machine -- not even python -- which is what makes
# it the "just download and run it" answer next to `pip install git-nested`.
#
#   scripts/create-python-exe.sh [--output DIR] [--python PYTHON] [--no-archive]
#
# Output (default dist/): the executable 'git-nested' plus a
# git-nested-<version>-x64-linux.tar.xz holding it, which is what the release
# workflow attaches to the release. The executable has to keep that exact
# name on the target machine: `git nested ...` works by git looking up a
# 'git-nested' on PATH.
#
# PORTABILITY: a PyInstaller binary bundles the interpreter but still links
# the *build machine's* glibc, and glibc is only backward compatible -- so the
# binary runs on every distro whose glibc is at least as new as the one it was
# built against, and on none older. Building it on a modern Ubuntu would
# therefore quietly exclude every LTS/enterprise distro older than that
# runner. .github/workflows/build-binary.yml builds inside almalinux:8
# (glibc 2.28) for that reason; run this script there too (or in any
# comparably old glibc) if you want a binary as portable as the released one.
# The floor that build actually gives is printed at the end of this script.
set -euo pipefail

# Pinned rather than floating: the bootloader PyInstaller prepends is shipped
# prebuilt in its wheel, so its version is part of what the produced binary
# *is* -- an unannounced upgrade is an unannounced change to every released
# executable.
PYINSTALLER_VERSION="6.16.0"

# The asset name the release workflow uploads follows
# git-nested-<version>-x64-linux.tar.xz; x64/Linux is not a guess but what
# this build is -- PyInstaller freezes for the running platform only. The
# version is filled in once it's known, after freezing (see below).

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/dist"
PYTHON="${PYTHON:-python3}"
ARCHIVE=1

while [ $# -gt 0 ]; do
    case "$1" in
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --python) PYTHON="$2"; shift 2 ;;
        --no-archive) ARCHIVE=0; shift ;;
        -h|--help) sed -n '2,23p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

command -v "$PYTHON" >/dev/null || { echo "ERROR: no '$PYTHON' on PATH (pass --python)" >&2; exit 1; }

# git-nested's version is derived from the checkout's git tags by setuptools-scm
# at install time and then read back out of the installed metadata at runtime
# (see git_nested.py's VERSION) -- there is no git and no checkout left inside
# the frozen binary to ask later. A tagless checkout (a shallow CI clone, a
# source tarball) silently falls back to pyproject.toml's fallback_version, so
# the binary would ship claiming a version that isn't the one it was built
# from. Warn rather than fail: a local `--version`-doesn't-matter build is
# legitimate, an unnoticed one in a release is not.
if ! git -C "$REPO_ROOT" describe --tags --match '*.*.*' >/dev/null 2>&1; then
    echo "WARNING: no git tags found in $REPO_ROOT -- the executable will report" >&2
    echo "WARNING: pyproject.toml's setuptools-scm fallback_version, not the real one." >&2
fi

# pip builds a local source directory *in place*, so installing the repo below
# drops a build/ and an egg-info into the checkout (exactly what `poe clean`
# removes). Cleared before, so a stale one cannot poison this build, and again
# afterwards, so this script leaves the tree as it found it. Failing to remove
# them is worth stopping for rather than hitting setuptools' unhelpful
# "Operation not permitted" mid-build: it means they belong to another user --
# typically root, from a build run inside a container with the checkout
# mounted, which is precisely how the portable binary is built.
clean_in_tree_build_artifacts() {
    rm -rf "$REPO_ROOT/build" "$REPO_ROOT"/*.egg-info "$REPO_ROOT"/src/*.egg-info
}
if ! clean_in_tree_build_artifacts; then
    echo "ERROR: cannot remove $REPO_ROOT/build (or src/*.egg-info) -- left by a build" >&2
    echo "ERROR: that ran as a different user, e.g. as root inside a container." >&2
    echo "ERROR: Remove them with the same user, e.g.:" >&2
    echo "ERROR:   docker run --rm -v \"$REPO_ROOT\":/src alpine rm -rf /src/build /src/src/git_nested.egg-info" >&2
    exit 1
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"; clean_in_tree_build_artifacts || true' EXIT

echo ">>> creating build venv with $("$PYTHON" -V)"
"$PYTHON" -m venv "$BUILD_DIR/venv"
VENV_PY="$BUILD_DIR/venv/bin/python"

# A real (non-editable) install on purpose: it is what puts git_nested's
# dist-info metadata and PyYAML in one place for PyInstaller to collect. An
# editable install would leave both behind a path hook that the frozen binary
# has no way to follow.
echo ">>> installing git-nested + pyinstaller==$PYINSTALLER_VERSION"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet "$REPO_ROOT" "pyinstaller==$PYINSTALLER_VERSION"

# lib/git-nested, the launcher used from a checkout, is not usable here: it has
# no .py suffix (PyInstaller wants a python source file) and it prepends the
# checkout's src/ to sys.path, which inside a frozen binary points at a
# directory that does not exist. The three lines below are the same entry
# point without either problem -- git_nested is imported from the archive,
# exactly as installed.
cat > "$BUILD_DIR/git-nested-entry.py" <<'EOF'
import sys
from git_nested import main

if __name__ == '__main__':
    sys.exit(main())
EOF

# --copy-metadata git-nested: the frozen binary is not a checkout and not an
#   installed distribution, so importlib.metadata finds no package and
#   `git nested version` would report the "not installed" fallback 0.99.99
#   instead of the version it was built from (see git_nested.py's VERSION).
# --name git-nested: git resolves the subcommand `git nested` to a 'git-nested'
#   on PATH, so the file name is part of the interface, not cosmetics.
echo ">>> freezing"
"$BUILD_DIR/venv/bin/pyinstaller" \
    --onefile \
    --name git-nested \
    --clean \
    --noconfirm \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR/work" \
    --copy-metadata git-nested \
    "$BUILD_DIR/git-nested-entry.py"

EXE="$BUILD_DIR/dist/git-nested"

# Smoke test before packaging: --version proves the bundled metadata is
# readable, and the init below is a real end-to-end run -- it drives git,
# writes a .gitnested and reads it back through PyYAML, which is what actually
# catches an import that did not make it into the archive. Run against a
# throwaway repo with its own HOME so a developer's git config (hooks,
# templates, a signing key) cannot decide whether this passes.
echo ">>> smoke-testing $EXE"
VERSION_OUTPUT="$("$EXE" --version | head -1)"
echo "$VERSION_OUTPUT"
"$EXE" --help >/dev/null
SMOKE_DIR="$BUILD_DIR/smoke"
mkdir -p "$SMOKE_DIR/repo/doc"
(
    export HOME="$SMOKE_DIR" GIT_CONFIG_GLOBAL="$SMOKE_DIR/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
    git -C "$SMOKE_DIR/repo" init --quiet --initial-branch=master
    git -C "$SMOKE_DIR/repo" config user.email smoke@example.com
    git -C "$SMOKE_DIR/repo" config user.name Smoke
    touch "$SMOKE_DIR/repo/doc/README.md"
    git -C "$SMOKE_DIR/repo" add -A
    git -C "$SMOKE_DIR/repo" commit --quiet -m "smoke test"
    cd "$SMOKE_DIR/repo" && "$EXE" init doc >/dev/null
    test -f "$SMOKE_DIR/repo/doc/.gitnested" || { echo "ERROR: 'git-nested init doc' wrote no .gitnested" >&2; exit 1; }
)

# 'git-nested Version: X.Y.Z' -> X.Y.Z; see git_nested.py's cmd_version for
# what it prints.
VERSION="${VERSION_OUTPUT#git-nested Version: }"
ARCHIVE_NAME="git-nested-${VERSION}-x64-linux.tar.xz"

mkdir -p "$OUTPUT_DIR"
cp "$EXE" "$OUTPUT_DIR/git-nested"

if [ "$ARCHIVE" = 1 ]; then
    # The tarball holds the versioned binary plus a 'git-nested' symlink to
    # it, so it can be dropped anywhere on PATH under a name that doesn't
    # change release to release, while the file itself still names the
    # version it is -- e.g. for side-by-side installs of more than one
    # release.
    cp "$EXE" "$BUILD_DIR/dist/git-nested-$VERSION"
    ln -sf "git-nested-$VERSION" "$BUILD_DIR/dist/git-nested"
    # LICENSE rides along: the tarball is a redistribution of git-nested in
    # binary form, so MIT asks for the notice to travel with it. Completion
    # needs nothing here -- the binary prints its own script, so
    # `eval "$(git-nested completion bash)"` works from the tarball too.
    cp "$REPO_ROOT/LICENSE" "$BUILD_DIR/dist/LICENSE"
    XZ_OPT=-9 tar -C "$BUILD_DIR/dist" -caf "$OUTPUT_DIR/$ARCHIVE_NAME" "git-nested-$VERSION" git-nested LICENSE
fi

echo
echo ">>> $VERSION_OUTPUT -> $OUTPUT_DIR/git-nested ($(du -h "$OUTPUT_DIR/git-nested" | cut -f1))"
if [ "$ARCHIVE" = 1 ]; then
    echo ">>> $OUTPUT_DIR/$ARCHIVE_NAME ($(du -h "$OUTPUT_DIR/$ARCHIVE_NAME" | cut -f1))"
fi
echo ">>> built against $(getconf GNU_LIBC_VERSION 2>/dev/null || echo 'glibc (unknown version)'): runs on any x86_64 Linux with at least that glibc"
