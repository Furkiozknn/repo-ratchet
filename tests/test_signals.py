"""Each measurement has to be right about a repository it has never seen.

The fixtures here are small on purpose: a signal that needs a realistic
repository to be testable is a signal that is doing too much.
"""

from pathlib import Path

from ratchet import signals


def test_languages_ranks_by_bytes(make_repo):
    root = make_repo("a", {
        "src/main.py": "x = 1\n" * 100,
        "src/tiny.rs": "fn main() {}\n",
    })
    s = signals.languages(root)
    assert list(s.value)[0] == "python"
    assert s.value["rust"] < s.value["python"]


def test_languages_none_when_there_is_no_source(make_repo):
    root = make_repo("b", {"README.md": "hello"})
    assert signals.languages(root).value is None


def test_skipped_directories_are_not_the_repository(make_repo):
    root = make_repo("c", {
        "src/a.py": "x = 1\n",
        "node_modules/big/index.js": "y\n" * 5000,
        "target/debug/out.rs": "fn x() {}\n" * 500,
    })
    s = signals.languages(root)
    assert set(s.value) == {"python"}


def test_a_dotted_directory_is_not_part_of_the_repository(make_repo):
    """Tooling and state live in dotted directories - including this tool's
    own clone directory, which once made one repository measure as twenty-eight."""
    root = make_repo("c2", {
        "src/a.py": "x = 1\n",
        ".ratchet-work/other-project/big.py": "y = 2\n" * 5000,
        ".venv/lib/thing.py": "z = 3\n" * 5000,
    })
    s = signals.languages(root)
    assert s.value["python"] < 100, s.value


def test_a_dotfile_at_the_root_is_still_part_of_the_repository(make_repo):
    """Only dotted *directories* are skipped; a dotted file is not a tree."""
    root = make_repo("c3", {".hidden.py": "x = 1\n"})
    assert signals.languages(root).value is not None


def test_test_mass_counts_tests_separately(make_repo):
    root = make_repo("d", {
        "src/lib.py": "a = 1\n" * 200,
        "tests/test_lib.py": "def test_a():\n    assert True\n",
    })
    s = signals.test_mass(root)
    assert 0 < s.value < 1
    assert "tests/test_lib.py" in s.evidence


def test_test_mass_headroom_is_full_without_tests(make_repo):
    root = make_repo("e", {"src/lib.py": "a = 1\n" * 50})
    assert signals.test_mass(root).headroom == 1.0


def test_test_count_python(make_repo):
    root = make_repo("f", {
        "tests/test_x.py": "def test_one():\n    pass\n\nasync def test_two():\n    pass\n",
    })
    assert signals.test_count(root).value == 2


def test_test_count_rust_counts_inline_test_attributes(make_repo):
    root = make_repo("g", {
        "src/lib.rs": "pub fn a() {}\n\n#[cfg(test)]\nmod t {\n    #[test]\n    fn one() {}\n    #[test]\n    fn two() {}\n}\n",
    })
    assert signals.test_count(root).value == 2


def test_test_count_gdscript_hand_rolled_cases(make_repo):
    """GDScript has no test framework, so projects write `func _test_x()`."""
    root = make_repo("f2", {
        "tests/testler.gd": (
            "extends SceneTree\n"
            "func _calistir() -> void:\n\tawait _test_a()\n\n"
            "func _test_a() -> void:\n\tpass\n\n"
            "func _test_b() -> void:\n\tpass\n\n"
            "func yardimci() -> void:\n\tpass\n"
        ),
    })
    assert signals.test_count(root).value == 2


def test_test_count_gdscript_outside_a_test_path_is_not_counted(make_repo):
    root = make_repo("f3", {"scripts/oyun.gd": "func test_mode() -> void:\n\tpass\n"})
    assert signals.test_count(root).value == 0


def test_test_count_gdscript_assertion_helper_found_by_shape(make_repo):
    """The helper's name is the author's choice; its first bool parameter is not."""
    root = make_repo("f3b", {
        "tests/test_denge.gd": (
            "extends SceneTree\n"
            "func dogru(kosul: bool, ad: String) -> void:\n\tpass\n\n"
            "func _initialize() -> void:\n"
            "\tdogru(1 == 1, 'bir')\n"
            "\tdogru(2 == 2, 'iki')\n"
            "\tdogru(3 == 3, 'uc')\n"
        ),
    })
    assert signals.test_count(root).value == 3


def test_a_gdscript_file_with_no_assertion_helper_counts_nothing(make_repo):
    root = make_repo("f3c", {"tests/yardimci.gd": "func kur() -> void:\n\tpass\n"})
    assert signals.test_count(root).value == 0


def test_test_count_hand_rolled_javascript_runner(make_repo):
    """A `*-test.js` script with its own assert helper still has cases."""
    root = make_repo("f4", {
        "tests/kontrol-test.js": (
            'ol("bir", true);\n'
            'ol("iki", 1 === 1);\n'
            'console.log("bitti");\n'
        ),
    })
    assert signals.test_count(root).value == 2


def test_a_framework_beats_the_hand_rolled_fallback(make_repo):
    """When `it(` is present the fallback must not double-count."""
    root = make_repo("f5", {
        "tests/a.test.js": 'it("x", () => { assert(true); assert(1); });\nit("y", () => {});\n',
    })
    assert signals.test_count(root).value == 2


def test_test_count_zero_has_full_headroom(make_repo):
    root = make_repo("h", {"src/a.py": "x = 1\n"})
    s = signals.test_count(root)
    assert s.value == 0 and s.headroom == 1.0


def test_undocumented_surface_python(make_repo):
    root = make_repo("i", {
        "m.py": (
            'def documented():\n    """Yes."""\n    pass\n\n'
            "def bare():\n    pass\n\n"
            "def _private():\n    pass\n"
        ),
    })
    s = signals.undocumented_surface(root)
    assert s.value == 1
    assert any("bare" in e for e in s.evidence)


def test_undocumented_surface_sees_a_docstring_after_a_long_signature(make_repo):
    """A four-line signature used to push its docstring out of the window."""
    root = make_repo("i2", {
        "m.py": (
            "def uzun(\n"
            "    a: int,\n"
            "    b: str = 'x',\n"
            "    *, c: bool = False,\n"
            ") -> dict:\n"
            '    """Belgeli."""\n'
            "    return {}\n"
        ),
    })
    assert signals.undocumented_surface(root).value == 0


def test_undocumented_surface_ignores_nested_definitions(make_repo):
    """A helper inside a function is not public surface."""
    root = make_repo("i3", {
        "m.py": 'def dis():\n    """Doc."""\n    def ic():\n        pass\n    return ic\n',
    })
    assert signals.undocumented_surface(root).value == 0


def test_undocumented_surface_counts_async_functions(make_repo):
    root = make_repo("i4", {"m.py": "async def f():\n    return 1\n"})
    assert signals.undocumented_surface(root).value == 1


def test_a_python_file_that_does_not_parse_is_skipped_not_guessed(make_repo):
    root = make_repo("i5", {
        "bozuk.py": "def (((:\n",
        "iyi.py": 'def f():\n    """Doc."""\n    return 1\n',
    })
    s = signals.undocumented_surface(root)
    assert s.value == 0
    assert "1 of 1" in s.detail or s.detail.startswith("0 of 1")


def test_undocumented_surface_rust(make_repo):
    root = make_repo("j", {
        "src/l.rs": "/// Documented.\npub fn a() {}\n\npub struct B;\n",
    })
    s = signals.undocumented_surface(root)
    assert s.value == 1


def test_undocumented_surface_is_none_for_other_languages(make_repo):
    root = make_repo("k", {"a.gd": "func x():\n\tpass\n"})
    assert signals.undocumented_surface(root).value is None


def test_undocumented_surface_ignores_tests(make_repo):
    root = make_repo("k2", {"tests/test_a.py": "def helper():\n    pass\n"})
    assert signals.undocumented_surface(root).value is None


def test_ci_breadth_counts_distinct_runners(make_repo):
    root = make_repo("l", {
        ".github/workflows/ci.yml": (
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n  b:\n    runs-on: macos-latest\n"
        ),
    })
    s = signals.ci_breadth(root)
    assert s.value == 2


def test_ci_breadth_reads_a_matrix_list(make_repo):
    root = make_repo("m", {
        ".github/workflows/ci.yml": "jobs:\n  a:\n    strategy:\n      matrix:\n        os: [ubuntu-latest, windows-latest, macos-latest]\n",
    })
    assert signals.ci_breadth(root).value == 3


def test_ci_breadth_none_without_workflows(make_repo):
    root = make_repo("n", {"README.md": "x"})
    assert signals.ci_breadth(root).value is None


def test_readme_commands_extracts_shell_blocks(make_repo):
    root = make_repo("o", {
        "README.md": "# t\n\n```sh\n$ pip install x\n# a comment\npytest -q\n```\n",
    })
    s = signals.readme_commands(root)
    assert s.value == 2
    assert "pip install x" in s.evidence


def test_readme_depth_headroom_falls_as_the_readme_grows(make_repo):
    thin = make_repo("p", {"README.md": "# t\n"})
    thick = make_repo("q", {"README.md": "# t\n" + ("word " * 1000)})
    assert signals.readme_depth(thin).headroom > signals.readme_depth(thick).headroom


def test_readme_missing_is_full_headroom(make_repo):
    root = make_repo("r", {"a.py": "x = 1\n"})
    assert signals.readme_depth(root).headroom == 1.0


def test_todo_density_finds_markers_with_locations(make_repo):
    root = make_repo("s", {"a.py": "x = 1  # TODO fix\ny = 2\n# FIXME later\n"})
    s = signals.todo_density(root)
    assert s.value == 2
    assert s.evidence[0].startswith("a.py:1")


def test_todo_density_ignores_the_word_outside_a_comment(make_repo):
    # A tool that greps for TODO finds its own pattern, and every string that
    # happens to contain the word. Only comment markers are debt.
    root = make_repo("s2", {
        "a.py": 'PATTERN = "TODO|FIXME"\nmsg = "no TODO here"\nx = 1  # TODO really\n',
    })
    s = signals.todo_density(root)
    assert s.value == 1
    assert s.evidence == ["a.py:3 x = 1  # TODO really"]


def test_todo_density_ignores_test_files(make_repo):
    root = make_repo("s3", {"tests/test_a.py": "# TODO fixture marker\n"})
    assert signals.todo_density(root).value == 0


def test_todo_density_reads_slash_comments_too(make_repo):
    root = make_repo("s4", {"a.rs": "// FIXME: unwrap\nfn x() {}\n", "b.js": "/* HACK */\n"})
    assert signals.todo_density(root).value == 2


def test_todo_density_zero_has_no_headroom(make_repo):
    root = make_repo("t", {"a.py": "x = 1\n"})
    assert signals.todo_density(root).headroom == 0.0


def test_largest_source_file_ignores_tests(make_repo):
    root = make_repo("u", {
        "src/small.py": "x\n" * 10,
        "tests/test_huge.py": "y\n" * 5000,
    })
    s = signals.largest_source_file(root)
    assert s.evidence == ["src/small.py"]


def test_declared_dependencies_reads_each_manifest(make_repo):
    root = make_repo("v", {
        "pyproject.toml": 'dependencies = ["httpx", "rich"]\n',
        "package.json": '{"dependencies": {"left-pad": "1.0.0"}}\n',
    })
    s = signals.declared_dependencies(root)
    assert s.value == 3


def test_declared_dependencies_none_without_a_manifest(make_repo):
    root = make_repo("w", {"a.py": "x = 1\n"})
    assert signals.declared_dependencies(root).value is None


def test_release_lag_counts_commits_since_the_tag(make_repo):
    root = make_repo("x", {"a.py": "x = 1\n"}, git=True, tag="v0.1.0", extra_commits=3)
    s = signals.release_lag(root)
    assert s.value == 3
    assert s.evidence == ["v0.1.0"]


def test_release_lag_says_never_tagged(make_repo):
    root = make_repo("y", {"a.py": "x = 1\n"}, git=True)
    s = signals.release_lag(root)
    assert s.value is None
    assert "never tagged" in s.detail


def test_release_lag_none_outside_git(make_repo):
    root = make_repo("z", {"a.py": "x = 1\n"})
    assert signals.release_lag(root).value is None


def test_metadata_present_reports_null_fields(make_repo):
    root = make_repo("aa", {"project-meta.json": '{"id": "x", "version": null}'})
    s = signals.metadata_present(root)
    assert s.value is True
    assert s.evidence == ["version"]


def test_metadata_absent_is_full_headroom(make_repo):
    root = make_repo("ab", {"a.py": "x = 1\n"})
    assert signals.metadata_present(root).headroom == 1.0


def test_broken_metadata_is_not_reported_as_present(make_repo):
    root = make_repo("ac", {"project-meta.json": "{not json"})
    assert signals.metadata_present(root).value is False


def test_every_signal_runs_on_an_empty_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    for fn in signals.ALL:
        s = fn(empty)
        assert s.name, fn.__name__
