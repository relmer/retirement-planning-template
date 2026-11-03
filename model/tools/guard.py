"""guard.py: privacy checks run by the git hooks in .githooks (installed by setup_clone.py).

    guard.py check-private <url>   pre-push to any non-template remote: block PUBLIC GitHub repos
    guard.py template-push         pre-push to the template (maintainers): sample data only
    guard.py staged                pre-commit (maintainers): sample data only

"Sample data only" means: no files under private/ (except private/README.md) or
output/, Inputs.xlsx identical in content to the build_inputs.py sample, and no
string from the local, untracked .git/info/forbidden-strings list (one per line;
for example real names, account numbers, employer).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or ".")
sys.path.insert(0, str(ROOT / "model"))
ZERO = "0" * 40


def git(*args, binary=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def fail(msg):
    print(f"BLOCKED: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- public check
def github_slug(url):
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return (m[1], m[2]) if m else None


def visibility(owner, repo):
    """'public', 'private', or None if unknown."""
    try:
        r = subprocess.run(["gh", "repo", "view", f"{owner}/{repo}", "--json", "visibility"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return json.loads(r.stdout)["visibility"].lower()
    except Exception:
        pass
    try:
        with urllib.request.urlopen(f"https://api.github.com/repos/{owner}/{repo}", timeout=10) as resp:
            return "private" if json.load(resp).get("private") else "public"
    except urllib.error.HTTPError as e:
        return "private" if e.code == 404 else None   # unauthenticated 404 = private (or missing)
    except Exception:
        return None


def check_private(url):
    slug = github_slug(url)
    if slug is None:
        print(f"guard: '{url}' is not a GitHub URL; make sure it is private.", file=sys.stderr)
        return
    v = visibility(*slug)
    if v == "public":
        fail(f"{slug[0]}/{slug[1]} is PUBLIC. Your financial data must only go to a private repo.")
    if v is None:
        fail(f"could not verify that {slug[0]}/{slug[1]} is private (offline?). "
             "Retry, or set GUARD_ALLOW_UNVERIFIED_REMOTE=1 for this push.")


# ---------------------------------------------------------------- sample-only check
def forbidden_strings():
    p = ROOT / ".git" / "info" / "forbidden-strings"
    if not p.exists():
        return []
    return [s.strip() for s in p.read_text(encoding="utf-8").splitlines() if s.strip() and not s.startswith("#")]


def is_sample_workbook(data: bytes):
    import build_inputs as B
    from inputs_io import load_inputs
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "Inputs.xlsx")
        Path(p).write_bytes(data)
        inp = load_inputs(p)
    if inp.params.get("household") != B.SAMPLE_MARKER:
        return False, "Params.household is not the sample marker"
    got = [(a["account"], a["owner"], a["tax_type"], a["balance"]) for a in inp.accounts]
    want = [(a, o, t, float(b)) for a, o, t, b, *_ in B.ACCOUNTS]
    if got != want:
        return False, "Accounts differ from the sample"
    want_ss = [(p, a, float(m)) for p, a, m, *_ in B.SOCIAL_SECURITY]
    if [(p, a, m) for p, a, m, _ in inp.social_security] != want_ss:
        return False, "SocialSecurity differs from the sample"
    if inp.husband_name != B.PARAMS[1][1] or inp.wife_name != B.PARAMS[2][1]:
        return False, "names differ from the sample"
    return True, ""


def check_files(paths, read):
    """paths: repo-relative paths; read(path) -> bytes."""
    bad = [p for p in paths if (p.startswith("private/") and p != "private/README.md") or p.startswith("output/")]
    if bad:
        fail("personal-data paths in a template commit: " + ", ".join(bad[:10]))
    words = forbidden_strings()
    for p in paths:
        data = read(p)
        if data is None:
            continue
        if p == "Inputs.xlsx":
            ok, why = is_sample_workbook(data)
            if not ok:
                fail(f"Inputs.xlsx is not the sample workbook ({why}). Restore it: python model/build_inputs.py --force")
            continue
        if words:
            text = data.decode("utf-8", "ignore")
            for w in words:
                if re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, re.I):
                    fail(f"forbidden string '{w}' found in {p} (list: .git/info/forbidden-strings)")


def staged():
    names = (git("diff", "--cached", "--name-only", "--diff-filter=ACMR") or "").split()
    check_files(names, lambda p: git("show", f":{p}", binary=True))


def template_push():
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _lref, lsha, _rref, rsha = parts
        if lsha == ZERO:
            continue   # branch deletion
        rng = [lsha] if rsha == ZERO else [f"{rsha}..{lsha}"]
        names = sorted(set((git("log", "--name-only", "--pretty=format:", *rng) or "").split()))
        tree = set((git("ls-tree", "-r", "--name-only", lsha) or "").split())
        names = [n for n in names if n in tree]
        check_files(names, lambda p, s=lsha: git("show", f"{s}:{p}", binary=True))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "check-private" and len(sys.argv) > 2:
        check_private(sys.argv[2])
    elif mode == "template-push":
        template_push()
    elif mode == "staged":
        staged()
    else:
        raise SystemExit(__doc__)
