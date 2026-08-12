#!/usr/bin/env python3
"""Bump the project VERSION file (M.m.f) based on git commit history.

Rules:
- Every change since the last version bump = a "fix" (patch bump).
- A commit whose subject starts with `feat:` (new feature) = a "minor" bump.
- The "major" component is never changed automatically; bump it manually.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
FEATURE_RE = re.compile(r"^feat(\([^)]*\))?:", re.IGNORECASE)


def resolve_root() -> Path:
    env = os.environ.get("BUMP_VERSION_ROOT")
    if env:
        return Path(env)
    cwd = Path.cwd()
    if (cwd / "VERSION").is_file():
        return cwd
    return Path(__file__).resolve().parent.parent


def run_git(root: Path, *args: str) -> list[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=root)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.splitlines()


def read_version(root: Path) -> tuple[int, int, int]:
    content = (root / "VERSION").read_text().strip()
    match = VERSION_RE.match(content)
    if not match:
        raise ValueError(f"VERSION must match M.m.f, got: {content!r}")
    return tuple(int(part) for part in match.groups())


def write_version(root: Path, version: tuple[int, int, int]) -> None:
    (root / "VERSION").write_text(f"{version[0]}.{version[1]}.{version[2]}\n")


def last_version_commit(root: Path) -> str | None:
    lines = run_git(root, "log", "-1", "--format=%H", "--", "VERSION")
    return lines[0] if lines else None


def new_subjects(root: Path) -> list[str]:
    base = last_version_commit(root)
    if base:
        lines = run_git(root, "log", "--format=%s", f"{base}..HEAD")
    else:
        lines = run_git(root, "log", "--format=%s")
    return [line for line in lines if line.strip()]


def next_version(current: tuple[int, int, int], subjects: list[str]) -> tuple[int, int, int]:
    major, minor, fix = current
    if not subjects:
        return current
    if any(FEATURE_RE.match(s) for s in subjects):
        return major, minor + 1, 0
    return major, minor, fix + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the bumped version back to the VERSION file",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: cwd if it contains VERSION, else script parent)",
    )
    args = parser.parse_args()

    root = args.root or resolve_root()

    subjects = new_subjects(root)
    current = read_version(root)
    new = next_version(current, subjects)

    if new != current:
        if args.write:
            write_version(root, new)
    print(f"{new[0]}.{new[1]}.{new[2]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
