import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.fixture
def make_repo(tmp_path):
    """Build a throwaway repository on disk, optionally a real git one."""

    def _make(name: str, files: dict[str, str], git: bool = False, tag: str | None = None,
              extra_commits: int = 0) -> Path:
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        for rel, body in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        if git:
            _git(root, "init", "-q", "-b", "main") if (root / ".git").exists() is False else None
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], capture_output=True)
            _git(root, "config", "user.email", "t@example.com")
            _git(root, "config", "user.name", "t")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "first")
            if tag:
                _git(root, "tag", tag)
            for i in range(extra_commits):
                (root / ("extra%d.txt" % i)).write_text(str(i), encoding="utf-8")
                _git(root, "add", "-A")
                _git(root, "commit", "-q", "-m", "extra %d" % i)
        return root

    return _make


@pytest.fixture
def head_of():
    def _head(root: Path) -> str:
        return _git(root, "rev-parse", "HEAD")

    return _head
