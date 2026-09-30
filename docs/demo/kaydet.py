"""Runs the demo commands for real in a throwaway git repository and records
what `ratchet` printed (text, exit code) into demo.json next to this file.

`ratchet` must be on PATH (pip install .). Optional argv[1]: also write a plain
transcript (komutlar.txt style) to that path.
    python docs/demo/kaydet.py [transcript.txt]
"""
import datetime, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

env = dict(os.environ, PYTHONIOENCODING="utf-8", GIT_AUTHOR_NAME="demo", GIT_AUTHOR_EMAIL="d@e.x",
           GIT_COMMITTER_NAME="demo", GIT_COMMITTER_EMAIL="d@e.x")
HERE = Path(__file__).parent
work = Path(tempfile.mkdtemp(prefix="demo-"))
os.chdir(work)


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, encoding="utf-8")


log = []


def step(cmd, shown=None):
    r = run(cmd)
    log.append((shown or cmd, (r.stdout + r.stderr).rstrip(), r.returncode))


run("git init -q -b main")
Path("check.py").write_text("assert sum(range(4)) == 6\nprint('ok')\n")
Path("ratchet.toml").write_text('check = ["python3 check.py"]\n')
Path("app.py").write_text("def add(a, b):\n    return a + b\n")
run("git add -A && git commit -qm first")
H0 = run("git rev-parse HEAD").stdout.strip()
step("ratchet --version")
step('ratchet record demo --round 1 --outcome advanced --summary "tidied up" --before %s --after %s' % (H0, H0),
     'ratchet record demo --round 1 --outcome advanced --summary "tidied up" --before $BEFORE --after $BEFORE')
step("ratchet record demo --round 1 --outcome no-change")
Path("app.py").write_text('def add(a, b):\n    """Sum of two numbers."""\n    return a + b\n')
run("git commit -qam docstring")
H1 = run("git rev-parse HEAD").stdout.strip()
step("ratchet check . --out v.json")
step('ratchet --records rec record demo --round 1 --outcome advanced --summary "documented add()" '
     '--before %s --after %s --verifications v.json' % (H0, H1),
     'ratchet --records rec record demo --round 1 --outcome advanced --summary "documented add()" '
     '--before $BEFORE --after $AFTER --verifications v.json')
step("ratchet --records rec report")
step("ratchet check . --command \"bash -c 'rm -rf /'\"")
(HERE / "demo.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write("# repo-ratchet - real command output, %s, clean venv (pip install .), throwaway git repo\n"
                "# $BEFORE/$AFTER = the two commit shas (40 hex) of that repo\n\n" % datetime.date.today())
        for c, o, rc in log:
            f.write("$ %s\n%s\n[exit %d]\n\n" % (c, o, rc))
os.chdir(HERE)
shutil.rmtree(work, ignore_errors=True)
