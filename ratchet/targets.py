"""Which repositories are in range, and which are deliberately not.

Discovery is done against the live GitHub API rather than a list kept in this
repository, because a list in a repository is a list that goes stale. What is
kept here is the opposite: the things that must *never* be touched, which is
exactly the kind of rule that should not be discovered at runtime.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

API = "https://api.github.com/users/{owner}/repos?per_page=100&type=owner&page={page}"

#: Repositories the engine will not clone, survey, run or change, whatever a
#: survey says about them. Private work and anything explicitly fenced off by
#: the owner belongs here.
DENYLIST = {"kor"}

#: Reasons a repository is skipped without being on the denylist.
SKIP_ARCHIVED = "archived: the repository is read-only, so no round can change it"
SKIP_FORK = "fork: upstream owns the direction of this code"
SKIP_EMPTY = "empty: nothing has been pushed to it yet"


@dataclass(frozen=True)
class Target:
    """One repository the engine may open."""

    name: str
    default_branch: str
    clone_url: str
    archived: bool
    size_kb: int
    description: str = ""

    @property
    def in_range(self) -> bool:
        return not self.archived and self.name not in DENYLIST and self.size_kb > 0

    @property
    def skip_reason(self) -> str | None:
        if self.name in DENYLIST:
            return "denylisted: this repository is out of the engine's reach by rule"
        if self.archived:
            return SKIP_ARCHIVED
        if self.size_kb <= 0:
            return SKIP_EMPTY
        return None


def _fetch(url: str, token: str | None) -> list[dict]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "repo-ratchet",
        "Accept": "application/vnd.github+json",
    })
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def discover(owner: str, token: str | None = None) -> list[Target]:
    """Every public, non-fork repository on the account, straight from GitHub."""
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    out: list[Target] = []
    page = 1
    while True:
        try:
            data = _fetch(API.format(owner=owner, page=page), token)
        except urllib.error.HTTPError as ex:
            raise RuntimeError("GitHub said %s while listing %s's repositories" % (ex.code, owner)) from ex
        if not data:
            break
        for r in data:
            if r.get("fork") or r.get("private"):
                continue
            out.append(Target(
                name=r["name"],
                default_branch=r.get("default_branch") or "main",
                clone_url=r["clone_url"],
                archived=bool(r.get("archived")),
                size_kb=int(r.get("size") or 0),
                description=(r.get("description") or "").strip(),
            ))
        if len(data) < 100:
            break
        page += 1
    return sorted(out, key=lambda t: t.name)


def load_offline(path: str) -> list[Target]:
    """Read a discovery result saved earlier, for running without the network."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("targets", data)
    return sorted(
        (Target(
            name=r["name"],
            default_branch=r.get("default_branch", "main"),
            clone_url=r.get("clone_url", ""),
            archived=bool(r.get("archived")),
            size_kb=int(r.get("size_kb", r.get("size", 1))),
            description=r.get("description", ""),
        ) for r in rows),
        key=lambda t: t.name,
    )
