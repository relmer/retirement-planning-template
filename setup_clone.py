"""setup_clone.py: one-time setup of a personal copy of the retirement template.

    python setup_clone.py                     # the recommended setup (local only)
    python setup_clone.py --no-venv           # skip the Python environment
    python setup_clone.py --remote <url> --accept-risks
                                              # NOT recommended: also allow pushing to a remote

The recommended setup keeps the plan in THIS folder only, with every document
and result committed to the local git history, and this folder inside OneDrive
so it is backed up. What it does:
  1. Checks that this folder is inside OneDrive (warns if not).
  2. Installs the git hooks in .githooks/ (core.hooksPath): every push is
     blocked unless a remote was explicitly accepted with --accept-risks; the
     shared template and public GitHub repos are always blocked.
  3. Makes the remote that points at the template fetch-only, renamed 'template'
     (template updates: git pull template main).
  4. Creates the Python environment (outside OneDrive when the repo is inside
     it) and installs requirements.txt.
  5. Creates the private/ folder layout for source documents.
Safe to run more than once.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE_DIRS = ["accounts", "social_security", "income", "benefits", "spending", "taxes",
                "insurance", "property", "estate"]

REMOTE_RISKS = """\
A copy of this plan on GitHub (or any server) is NOT recommended. The repo holds
the household's complete financial picture: every account, balance and income
source, tax returns, and statements that often contain full account numbers.
Risks of putting it there:
  - Anyone who gets into that GitHub account (stolen password, phished 2FA,
    leaked access token) gets all of it at once.
  - Apps and integrations granted access to the account's repos (CI services,
    AI tools, editors) can access it.
  - One wrong click makes a private repo public, and forks or collaborators
    can spread copies that are hard to recall.
  - The data is then stored on another company's servers under its retention terms.
OneDrive already backs up this folder, so a remote adds risk without adding
much safety. If you want one anyway: use a PRIVATE repo, turn on two-factor
authentication, review the apps with repo access, and black out account
numbers and SSNs in the documents under private/ first."""


def git(*args, check=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else None


def template_patterns():
    p = ROOT / ".template-upstream"
    return [s.strip().lower() for s in p.read_text().splitlines() if s.strip() and not s.startswith("#")] if p.exists() else []


def onedrive_roots():
    roots = [os.environ.get(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
    cloud = Path.home() / "Library" / "CloudStorage"
    if cloud.exists():
        roots += [str(p) for p in cloud.glob("OneDrive*")]
    return [Path(r).resolve() for r in roots if r]


def in_onedrive():
    return any(ROOT == r or r in ROOT.parents for r in onedrive_roots())


def venv_dir():
    """Inside OneDrive the environment goes elsewhere: thousands of package files
    should not sync. Otherwise .venv/ in the repo."""
    if in_onedrive():
        # Under the home folder, not AppData: packaged Windows apps (for example an AI
        # assistant's desktop app) silently redirect AppData writes into private storage
        # that a normal terminal cannot see.
        tag = hashlib.sha1(str(ROOT).lower().encode()).hexdigest()[:8]
        return Path.home() / ".retirement-plan-venvs" / f"{ROOT.name.replace(' ', '_')}-{tag}"
    return ROOT / ".venv"


def venv_python(d):
    win = d / "Scripts" / "python.exe"
    return win if win.exists() else d / "bin" / "python"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-venv", action="store_true")
    ap.add_argument("--remote", help="NOT recommended: allow pushing the plan to this URL (requires --accept-risks)")
    ap.add_argument("--accept-risks", action="store_true")
    ap.add_argument("--maintainer", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if git("rev-parse", "--show-toplevel") is None:
        raise SystemExit("Not a git repository. Clone the template with git first.")
    maintainer = args.maintainer or git("config", "--bool", "template.maintainer") == "true"

    # 1. location
    if not maintainer:
        if in_onedrive():
            print(f"Location: {ROOT} (inside OneDrive: backed up).")
            print("  Tip: right-click the folder in File Explorer -> 'Always keep on this device',")
            print("  so git never finds files that exist only in the cloud.")
        else:
            roots = onedrive_roots()
            print(f"WARNING: {ROOT} is not inside OneDrive, so nothing backs it up.")
            if roots:
                print(f"  Recommended: move this folder to {roots[0] / 'Documents'} before adding any documents,")
                print("  then run setup_clone.py again from the new location.")
            else:
                print("  Recommended: install OneDrive (or another backup) and keep this folder inside it.")

    # 2. hooks (first, so the copy is guarded even if a later step fails)
    git("config", "core.hooksPath", ".githooks", check=True)
    for h in (ROOT / ".githooks").iterdir():
        try:
            os.chmod(h, 0o755)
        except OSError:
            pass
    print("Privacy guard installed: pushes are blocked unless a remote is explicitly accepted.")

    if args.maintainer:
        git("config", "template.maintainer", "true", check=True)
        exclude = ROOT / ".git" / "info" / "exclude"
        text = exclude.read_text() if exclude.exists() else ""
        if "output/" not in text:
            exclude.write_text(text + "\n# template maintainer: personal data never enters this clone's history\n"
                               "private/*\n!private/README.md\noutput/\n")
        print("Maintainer mode: commits/pushes to the template must contain sample data only.")

    # 3. template remote: fetch-only
    pats = template_patterns()
    if not maintainer:
        for line in (git("remote", "-v") or "").splitlines():
            name, url, kind = line.split()
            if kind == "(fetch)" and any(p in url.lower() for p in pats):
                if name != "template":
                    git("remote", "rename", name, "template", check=True)
                    print(f"Renamed remote '{name}' -> 'template'.")
                git("remote", "set-url", "--push", "template", "PUSH-DISABLED-template-is-read-only", check=True)
                print("Pushing to the template is disabled. Template updates: git pull template main")
                break

    # 4. Python environment (from the base interpreter, even if setup runs inside another venv)
    if not args.no_venv:
        d = venv_dir()
        if not venv_python(d).exists():
            print(f"Creating Python environment in {d} ...")
            d.parent.mkdir(parents=True, exist_ok=True)
            base = getattr(sys, "_base_executable", None) or sys.executable
            subprocess.run([base, "-m", "venv", str(d)], check=True)
        print("Installing packages ...")
        subprocess.run([str(venv_python(d)), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                       check=True)
        git("config", "plan.python", str(venv_python(d)).replace("\\", "/"), check=True)

    # optional remote (not recommended)
    if args.remote:
        url = args.remote
        if any(p in url.lower() for p in pats):
            raise SystemExit("That is the shared template repo. Your plan must never go there.")
        print("\n" + REMOTE_RISKS + "\n")
        if not args.accept_risks:
            raise SystemExit("Not configured. Re-run with --accept-risks to add the remote anyway.")
        guard = ROOT / "model" / "tools" / "guard.py"
        py = git("config", "plan.python") or sys.executable
        if subprocess.run([py, str(guard), "check-private", url]).returncode != 0:
            raise SystemExit("Not configured: the remote must be PRIVATE.")
        name = "backup"
        if git("remote", "get-url", name) is None:
            git("remote", "add", name, url, check=True)
        else:
            git("remote", "set-url", name, url, check=True)
        git("config", "plan.acceptedRemote", url, check=True)
        print(f"Remote '{name}' = {url} accepted. Push with: git push {name} main")

    # 5. folder layout for source documents
    if not maintainer:
        for d in PRIVATE_DIRS:
            (ROOT / "private" / d).mkdir(parents=True, exist_ok=True)
        print("private/ folders ready (see private/README.md for naming).")

    py = git("config", "plan.python") or sys.executable
    print(f"\nPython for this plan: {py}")
    print(f"Next: \"{py}\" model/run.py --quick")


if __name__ == "__main__":
    main()
