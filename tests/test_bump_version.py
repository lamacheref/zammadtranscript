import subprocess
import sys
from pathlib import Path

import pytest

import scripts.bump_version as bv


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path,
                   check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

    (tmp_path / "VERSION").write_text("1.2.3\n")
    commit(tmp_path, "feat: initial commit")
    return tmp_path


def commit(repo_path: Path, message: str, filename: str = "file.txt") -> None:
    (repo_path / filename).write_text(message)
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True,
                   capture_output=True)


def test_read_version_valid(git_repo):
    assert bv.read_version(git_repo) == (1, 2, 3)


def test_read_version_invalid(tmp_path):
    (tmp_path / "VERSION").write_text("abc\n")
    with pytest.raises(ValueError):
        bv.read_version(tmp_path)


def test_no_changes_no_bump(git_repo):
    assert bv.new_subjects(git_repo) == []
    assert bv.next_version((1, 2, 3), []) == (1, 2, 3)


def test_fix_bumps_patch(git_repo):
    commit(git_repo, "fix: correct bug")
    subjects = bv.new_subjects(git_repo)
    assert bv.next_version((1, 2, 3), subjects) == (1, 2, 4)


def test_docs_bump_patch(git_repo):
    commit(git_repo, "docs: update readme")
    subjects = bv.new_subjects(git_repo)
    assert bv.next_version((1, 2, 3), subjects) == (1, 2, 4)


def test_feature_bumps_minor(git_repo):
    commit(git_repo, "feat: add cool feature")
    subjects = bv.new_subjects(git_repo)
    assert bv.next_version((1, 2, 3), subjects) == (1, 3, 0)


def test_feature_with_scope(git_repo):
    commit(git_repo, "feat(api): new endpoint")
    subjects = bv.new_subjects(git_repo)
    assert bv.next_version((1, 2, 3), subjects) == (1, 3, 0)


def test_major_never_automatic(git_repo):
    for i, msg in enumerate(("feat: one", "fix: two", "feat: three")):
        commit(git_repo, msg, filename=f"f{i}.txt")
    subjects = bv.new_subjects(git_repo)
    new = bv.next_version((1, 2, 3), subjects)
    assert new[0] == 1
    assert new == (1, 3, 0)


def test_write_updates_file(git_repo):
    commit(git_repo, "fix: bug")
    bv.write_version(git_repo, (1, 2, 4))
    assert (git_repo / "VERSION").read_text().strip() == "1.2.4"


def test_cli_prints_new_version(git_repo):
    commit(git_repo, "fix: another bug", filename="f2.txt")
    result = subprocess.run(
        [sys.executable, "scripts/bump_version.py", "--root", str(git_repo)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "1.2.4"


def test_cli_write_flag(git_repo):
    commit(git_repo, "feat: shiny", filename="f2.txt")
    result = subprocess.run(
        [sys.executable, "scripts/bump_version.py", "--root", str(git_repo), "--write"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert (git_repo / "VERSION").read_text().strip() == "1.3.0"