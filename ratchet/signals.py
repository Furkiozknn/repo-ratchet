"""Measurements of what a repository currently is.

Every function here answers a question with a number and the evidence behind
it. None of them answers "is this good?" - that judgement belongs to whoever
reads the survey, because the right next step for a linter is not the right
next step for a game.

A signal that cannot be measured returns ``None`` rather than a guess. A
``None`` value is carried through the whole pipeline and is never rendered as
a zero, because "there is no test directory" and "there are zero tests in the
test directory" are different facts.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

# Directories that are never part of what a repository "is": build output,
# vendored dependencies, version control internals.
SKIP_DIRS = {
    ".git", ".github", "node_modules", "target", "dist", "build", "__pycache__",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor",
    ".godot", ".import", "site-packages", ".idea", ".vscode",
}

SOURCE_SUFFIXES = {
    ".py": "python", ".rs": "rust", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".gd": "gdscript",
    ".go": "go", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".java": "java", ".rb": "ruby", ".sh": "shell", ".cs": "csharp",
}

DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}


@dataclass
class Signal:
    """One measurement, with the evidence that produced it.

    ``value`` is ``None`` when the measurement does not apply to this
    repository. ``headroom`` is a number in 0..1 saying how much room the
    measurement suggests there is - it is a ranking hint, never a verdict,
    and a signal is free to leave it at ``None``.
    """

    name: str
    value: Any
    unit: str = ""
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    headroom: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _walk(root: Path) -> Iterable[Path]:
    """Every file in the repository that is part of the repository itself."""
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def _is_test_path(p: Path, root: Path) -> bool:
    rel = p.relative_to(root).as_posix().lower()
    name = p.name.lower()
    if rel.startswith("tests/") or "/tests/" in rel or rel.startswith("test/"):
        return True
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.js")
        or name.endswith("_test.go")
        or name.endswith("_test.rs")
    )


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------
# individual measurements
# --------------------------------------------------------------------------


def languages(root: Path) -> Signal:
    """Which languages the repository is actually written in, by source bytes."""
    by_lang: dict[str, int] = {}
    for p in _walk(root):
        lang = SOURCE_SUFFIXES.get(p.suffix.lower())
        if not lang:
            continue
        try:
            by_lang[lang] = by_lang.get(lang, 0) + p.stat().st_size
        except OSError:
            continue
    if not by_lang:
        return Signal("languages", None, detail="no recognised source files")
    ordered = sorted(by_lang.items(), key=lambda kv: -kv[1])
    return Signal(
        "languages",
        {k: v for k, v in ordered},
        unit="bytes",
        detail="primary: %s" % ordered[0][0],
        evidence=["%s %d bytes" % (k, v) for k, v in ordered[:4]],
    )


def test_mass(root: Path) -> Signal:
    """Source bytes against test bytes.

    This is deliberately a ratio rather than coverage: coverage needs the
    suite to run, and this has to work on a repository in any language
    without executing anything in it.
    """
    src = tst = 0
    test_files: list[str] = []
    for p in _walk(root):
        if p.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if _is_test_path(p, root):
            tst += size
            test_files.append(p.relative_to(root).as_posix())
        else:
            src += size
    if src == 0 and tst == 0:
        return Signal("test_mass", None, detail="no source files to weigh")
    ratio = (tst / src) if src else None
    head = None
    if ratio is not None:
        # A repository with no tests has all the headroom; past roughly
        # 1 test byte per 2 source bytes the ratio stops being informative.
        head = max(0.0, min(1.0, 1.0 - (ratio / 0.5)))
    return Signal(
        "test_mass",
        None if ratio is None else round(ratio, 3),
        unit="test bytes per source byte",
        detail="%d source bytes, %d test bytes in %d files" % (src, tst, len(test_files)),
        evidence=sorted(test_files)[:6],
        headroom=head,
    )


TEST_PATTERNS = {
    "python": re.compile(r"^\s*(?:async\s+)?def\s+test_\w+", re.M),
    "rust": re.compile(r"^\s*#\[test\]", re.M),
    "javascript": re.compile(r"^\s*(?:it|test)\s*\(", re.M),
    "typescript": re.compile(r"^\s*(?:it|test)\s*\(", re.M),
    "go": re.compile(r"^\s*func\s+Test\w+\s*\(", re.M),
    # GDScript has no test framework in the engine, so projects hand-roll a
    # SceneTree script full of `func _test_something()`. Counting only
    # `it(`/`test(` reported those repositories as having no tests at all,
    # which is how four shipped games looked like untested ones.
    "gdscript": re.compile(r"^\s*func\s+_?test_\w+\s*\(", re.M),
}

#: A hand-rolled runner: a file that is clearly a test but declares its cases
#: as plain assertions rather than through a framework. Counting the file as
#: one case is wrong in the other direction, so these are counted by the
#: assertion helper they call.
HANDROLLED = re.compile(r"^\s*(?:ol|assert|check|expect)\s*\(", re.M)

#: `func dogru(kosul: bool, ad: String) -> void:` - a hand-written assertion
#: helper. Its name is whatever the author chose, and in these repositories it
#: is Turkish, so the name cannot be hardcoded. What is stable is the shape:
#: the first parameter is a bool. Finding the helper by shape and then counting
#: its call sites works whatever it is called.
GD_ASSERT_DEF = re.compile(r"^\s*func\s+(\w+)\s*\(\s*\w+\s*:\s*bool\b", re.M)


def _gdscript_assertions(text: str) -> int:
    """Count calls to a test file's own assertion helper.

    Returns 0 when the file declares no helper of that shape, so a GDScript
    file that is not really a test contributes nothing.
    """
    names = set(GD_ASSERT_DEF.findall(text))
    if not names:
        return 0
    total = 0
    for name in names:
        # The definition line itself is `func name(`, a call site is not.
        total += len(re.findall(r"(?<!func )\b%s\s*\(" % re.escape(name), text))
    return total


def test_count(root: Path) -> Signal:
    """How many test cases the repository declares, counted in the source.

    The count is of *declarations*, not of a run: this has to work on a
    repository in any language without executing anything in it. Where a
    language has no test framework, the convention the project actually uses
    is counted instead - a game with 853 hand-rolled cases is not a game
    without tests.
    """
    total = 0
    per_file: list[str] = []
    for p in _walk(root):
        lang = SOURCE_SUFFIXES.get(p.suffix.lower())
        pat = TEST_PATTERNS.get(lang or "")
        if not pat:
            continue
        if not _is_test_path(p, root) and lang not in ("rust",):
            continue
        text = _read(p)
        n = len(pat.findall(text))
        if not n and _is_test_path(p, root):
            if lang in ("javascript", "typescript"):
                n = len(HANDROLLED.findall(text))
            elif lang == "gdscript":
                n = _gdscript_assertions(text)
        if n:
            total += n
            per_file.append("%s: %d" % (p.relative_to(root).as_posix(), n))
    if not per_file:
        return Signal("test_count", 0, unit="cases", detail="no test cases found", headroom=1.0)
    return Signal(
        "test_count", total, unit="cases",
        detail="%d cases across %d files" % (total, len(per_file)),
        evidence=sorted(per_file)[:8],
    )


PY_PUBLIC = re.compile(r"^(?:class|def)\s+([A-Za-z]\w*)", re.M)
RS_PUBLIC = re.compile(r"^\s*pub\s+(?:fn|struct|enum|trait)\s+(\w+)", re.M)


def undocumented_surface(root: Path) -> Signal:
    """Top-level public things with nothing written about them.

    Only Python and Rust are measured, because those are the two languages
    where "has a docstring / has a /// comment" is unambiguous.
    """
    checked = missing = 0
    examples: list[str] = []
    for p in _walk(root):
        if _is_test_path(p, root):
            continue
        text = _read(p)
        rel = p.relative_to(root).as_posix()
        if p.suffix == ".py":
            lines = text.splitlines()
            for m in PY_PUBLIC.finditer(text):
                name = m.group(1)
                if name.startswith("_"):
                    continue
                checked += 1
                line_no = text[: m.start()].count("\n")
                nxt = "".join(lines[line_no + 1 : line_no + 3])
                if '"""' not in nxt and "'''" not in nxt:
                    missing += 1
                    if len(examples) < 8:
                        examples.append("%s:%d %s" % (rel, line_no + 1, name))
        elif p.suffix == ".rs":
            lines = text.splitlines()
            for m in RS_PUBLIC.finditer(text):
                checked += 1
                line_no = text[: m.start()].count("\n")
                prev = lines[line_no - 1].strip() if line_no else ""
                if not prev.startswith("///") and not prev.startswith("*/"):
                    missing += 1
                    if len(examples) < 8:
                        examples.append("%s:%d %s" % (rel, line_no + 1, m.group(1)))
    if checked == 0:
        return Signal("undocumented_surface", None, detail="no Python or Rust public surface")
    return Signal(
        "undocumented_surface", missing, unit="symbols",
        detail="%d of %d public symbols carry no doc comment" % (missing, checked),
        evidence=examples,
        headroom=round(missing / checked, 3),
    )


def ci_breadth(root: Path) -> Signal:
    """How many independent jobs and platforms the CI actually runs."""
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return Signal("ci_breadth", None, detail="no .github/workflows")
    files = sorted(p for p in wf_dir.glob("*.y*ml") if p.is_file())
    if not files:
        return Signal("ci_breadth", None, detail=".github/workflows is empty")
    runners: set[str] = set()
    jobs = 0
    for p in files:
        text = _read(p)
        jobs += len(re.findall(r"^\s{2}[A-Za-z_][\w-]*:\s*$", text, re.M))
        runners.update(re.findall(r"runs-on:\s*([A-Za-z0-9._-]+)", text))
        runners.update(re.findall(r"os:\s*\[([^\]]+)\]", text))
    flat: set[str] = set()
    for r in runners:
        for part in r.split(","):
            part = part.strip().strip("'\"")
            if part and not part.startswith("$"):
                flat.add(part)
    return Signal(
        "ci_breadth", len(flat), unit="distinct runners",
        detail="%d workflow files, ~%d jobs, runners: %s"
               % (len(files), jobs, ", ".join(sorted(flat)) or "none named literally"),
        evidence=[p.name for p in files],
        headroom=None if not flat else max(0.0, min(1.0, (3 - len(flat)) / 3)),
    )


def readme_commands(root: Path) -> Signal:
    """Shell commands the README tells a reader to run.

    The point is not the count; it is that these are the commands a first
    time visitor will paste, so they are the ones worth actually running.
    """
    readme = None
    for name in ("README.md", "readme.md", "README.rst"):
        if (root / name).is_file():
            readme = root / name
            break
    if readme is None:
        return Signal("readme_commands", None, detail="no README", headroom=1.0)
    text = _read(readme)
    blocks = re.findall(r"```(?:sh|bash|shell|console)\n(.*?)```", text, re.S)
    cmds: list[str] = []
    for b in blocks:
        for line in b.splitlines():
            line = line.strip().lstrip("$ ").strip()
            if line and not line.startswith("#"):
                cmds.append(line)
    return Signal(
        "readme_commands", len(cmds), unit="commands",
        detail="%d runnable-looking commands in %d shell blocks" % (len(cmds), len(blocks)),
        evidence=cmds[:8],
    )


def readme_depth(root: Path) -> Signal:
    """How much a first time visitor is actually told."""
    for name in ("README.md", "readme.md"):
        p = root / name
        if p.is_file():
            text = _read(p)
            heads = re.findall(r"^##+\s+(.+)$", text, re.M)
            imgs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text) + re.findall(r"<img[^>]+src=\"([^\"]+)\"", text)
            return Signal(
                "readme_depth", len(text), unit="bytes",
                detail="%d bytes, %d sections, %d images" % (len(text), len(heads), len(imgs)),
                evidence=heads[:10],
                headroom=max(0.0, min(1.0, (2500 - len(text)) / 2500)),
            )
    return Signal("readme_depth", None, detail="no README", headroom=1.0)


#: A marker only counts when it is inside a comment. Without this, a tool that
#: searches for TODO finds the pattern it searches with, and every project that
#: mentions the word in prose or in a test fixture looks like it has debt.
TODO_IN_COMMENT = re.compile(
    r"(?:#|//|/\*|\*|--|<!--)\s*\**\s*\b(TODO|FIXME|XXX|HACK)\b"
)


def todo_density(root: Path) -> Signal:
    """Unfinished business the code itself admits to, in its own comments."""
    hits: list[str] = []
    for p in _walk(root):
        if p.suffix.lower() not in SOURCE_SUFFIXES or _is_test_path(p, root):
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if TODO_IN_COMMENT.search(line):
                hits.append("%s:%d %s" % (p.relative_to(root).as_posix(), i, line.strip()[:90]))
    return Signal(
        "todo_density", len(hits), unit="markers",
        detail="%d TODO/FIXME/XXX/HACK markers in source" % len(hits),
        evidence=hits[:8],
        headroom=min(1.0, len(hits) / 20.0) if hits else 0.0,
    )


def largest_source_file(root: Path) -> Signal:
    """The biggest single source file - where an architecture usually strains first."""
    biggest: tuple[int, str] | None = None
    for p in _walk(root):
        if p.suffix.lower() not in SOURCE_SUFFIXES or _is_test_path(p, root):
            continue
        try:
            n = len(_read(p).splitlines())
        except OSError:
            continue
        if biggest is None or n > biggest[0]:
            biggest = (n, p.relative_to(root).as_posix())
    if biggest is None:
        return Signal("largest_source_file", None, detail="no source files")
    return Signal(
        "largest_source_file", biggest[0], unit="lines",
        detail="%s is the longest source file" % biggest[1],
        evidence=[biggest[1]],
        headroom=max(0.0, min(1.0, (biggest[0] - 400) / 1200.0)),
    )


def declared_dependencies(root: Path) -> Signal:
    """How much the project asks the world to install for it."""
    counts: dict[str, int] = {}
    ev: list[str] = []
    py = root / "pyproject.toml"
    if py.is_file():
        text = _read(py)
        m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
        items = [x for x in re.findall(r'"([^"]+)"', m.group(1))] if m else []
        counts["python"] = len(items)
        ev += items[:6]
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        text = _read(cargo)
        m = re.search(r"^\[dependencies\](.*?)(?:^\[|\Z)", text, re.S | re.M)
        items = re.findall(r"^\s*([A-Za-z0-9_-]+)\s*=", m.group(1), re.M) if m else []
        counts["rust"] = len(items)
        ev += items[:6]
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            d = json.loads(_read(pkg))
            items = sorted((d.get("dependencies") or {}).keys())
            counts["node"] = len(items)
            ev += items[:6]
        except (ValueError, TypeError):
            pass
    if not counts:
        return Signal("declared_dependencies", None, detail="no manifest found")
    total = sum(counts.values())
    return Signal(
        "declared_dependencies", total, unit="runtime dependencies",
        detail=", ".join("%s: %d" % kv for kv in sorted(counts.items())),
        evidence=ev,
    )


def release_lag(root: Path) -> Signal:
    """How far the default branch has moved since the last tag."""
    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    if not (root / ".git").exists():
        return Signal("release_lag", None, detail="not a git working tree")
    tag = git("describe", "--tags", "--abbrev=0")
    if not tag:
        total = git("rev-list", "--count", "HEAD")
        return Signal(
            "release_lag", None, unit="commits since last tag",
            detail="never tagged (%s commits on HEAD)" % (total or "?"),
            headroom=0.5,
        )
    n = git("rev-list", "--count", "%s..HEAD" % tag)
    try:
        count = int(n or "")
    except ValueError:
        return Signal("release_lag", None, detail="could not count commits since %s" % tag)
    return Signal(
        "release_lag", count, unit="commits since last tag",
        detail="last tag %s, %d commits since" % (tag, count),
        evidence=[tag],
        headroom=min(1.0, count / 25.0),
    )


def metadata_present(root: Path) -> Signal:
    """Whether the repository carries the ecosystem's own metadata file."""
    p = root / "project-meta.json"
    if not p.is_file():
        return Signal("metadata_present", False, detail="no project-meta.json", headroom=1.0)
    try:
        d = json.loads(_read(p))
    except ValueError as ex:
        return Signal("metadata_present", False, detail="project-meta.json is not valid JSON: %s" % ex, headroom=1.0)
    nulls = sorted(k for k, v in d.items() if v is None)
    return Signal(
        "metadata_present", True, unit="",
        detail="present; %d top-level fields, %d left null" % (len(d), len(nulls)),
        evidence=nulls[:8],
    )


ALL = (
    languages,
    test_mass,
    test_count,
    undocumented_surface,
    ci_breadth,
    readme_commands,
    readme_depth,
    todo_density,
    largest_source_file,
    declared_dependencies,
    release_lag,
    metadata_present,
)
