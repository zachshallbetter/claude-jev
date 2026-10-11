#!/usr/bin/env python3
"""Facts about every folder in a projects directory, from git and the filesystem, not Jev.

The split the /jev skill asks for: facts in code, decisions for Jev, writing for Claude.
This script is the facts half of a projects inventory:

  is_git, remote, owner           git remote (whose work it is: settle this from here, not README text)
  last_commit, last_hand_commit   newest commit, and newest one that isn't an automated sweep
  commits, top_level_entries      size signals (0 entries = empty; don't ask Jev)
  contents                        file-type summary: extension counts, standard project markers
                                  (package.json, Cargo.toml, src/…) and sub-project count. Types
                                  and well-known manifest names only, never the folder's own file names
  package_description, readme     text for Jev, markdown-stripped and redacted
  text                            ready-to-send item for `jev.py sort --text-field text`

  python3 project_facts.py [~/Projects] --out /tmp/projects.jsonl [--owners me,my-org]
  python3 jev.py sort /tmp/projects.jsonl --text-field text --questions preset:projects \
          --redact --max-chars 600 --keep-fields --out /tmp/kinds.jsonl        # dry run first
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev import redact  # noqa: E402

README_CHARS = 450
# Commit subjects of automated sweeps that touched every repo; they hide when real work happened.
AUTOMATED = ["Add Antigravity indexer ignores", "preserve uncommitted WIP", "preserve detached-HEAD work"]
SWEEP_MIN_REPOS = 4   # a normalized commit subject found in this many repos is an automated sweep


def normalize_subject(subject: str) -> str:
    s = re.sub(r"\s*\(#\d+\)\s*$", "", subject)      # trailing "(#NN)"
    return re.sub(r"\d+", "", s).strip().lower()
README_NAMES = ("README.md", "README.MD", "Readme.md", "readme.md", "README", "README.txt", "README.rst")


def strip_markdown(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)          # images / badges
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)       # links → their text
    text = re.sub(r"<[^>]+>", " ", text)                       # html
    return re.sub(r"\s+", " ", text).strip()


def package_description(d: Path) -> str:
    try:
        pj = d / "package.json"
        if pj.is_file():
            desc = json.loads(pj.read_text(errors="replace")).get("description") or ""
            if desc:
                return str(desc)
    except Exception:
        pass
    for f in ("Cargo.toml", "pyproject.toml"):
        p = d / f
        if p.is_file():
            m = re.search(r'^\s*description\s*=\s*"([^"]+)"', p.read_text(errors="replace"), re.M)
            if m:
                return m.group(1)
    return ""


def readme_excerpt(d: Path, chars: int = README_CHARS) -> str:
    for name in README_NAMES:
        p = d / name
        if p.is_file():
            return redact(strip_markdown(p.read_text(errors="replace")))[:chars]
    return ""


SKIP_DIRS = {".git", "node_modules", "target", ".venv", "venv", "env", "__pycache__", "dist", "build", ".next",
             "vendor", "Pods", "DerivedData", ".turbo", ".cache", "coverage", ".idea", ".vscode", "out"}
MANIFESTS = ["package.json", "Cargo.toml", "pyproject.toml", "requirements.txt", "go.mod", "Package.swift",
             "Gemfile", "pom.xml", "build.gradle", "Dockerfile", "docker-compose.yml", "index.html", "Makefile"]
MARKER_DIRS = ["src", "app", "apps", "packages", "lib", "docs", "public", "tests", "scripts"]
MARKER_PREFIXES = ["vite.config", "next.config", "tsconfig", "astro.config", "tailwind.config"]


def contents_summary(d: Path, depth: int = 3, max_files: int = 5000) -> dict:
    """Extension counts (dependency/build dirs skipped), standard project markers at the top
    level, and how many immediate subfolders are projects of their own."""
    import os
    exts: dict[str, int] = {}
    n = 0
    base = len(d.parts)
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        if len(Path(root).parts) - base >= depth:
            dirs[:] = []
        for f in files:
            if f.startswith("."):
                continue
            ext = Path(f).suffix.lower() or (f if f in ("Dockerfile", "Makefile") else "(no ext)")
            exts[ext] = exts.get(ext, 0) + 1
            n += 1
        if n >= max_files:
            break
    try:
        top = {p.name: p for p in d.iterdir() if not p.name.startswith(".")}
    except Exception:
        top = {}
    markers = [m for m in MANIFESTS if m in top]
    markers += [m + "/" for m in MARKER_DIRS if m in top and top[m].is_dir()]
    markers += sorted({f"{pre}.*" for name in top for pre in MARKER_PREFIXES if name.startswith(pre + ".")})
    markers += [".xcodeproj"] if any(k.endswith(".xcodeproj") for k in top) else []
    subprojects = sum(1 for p in top.values() if p.is_dir() and any((p / m).exists() for m in
                      ("package.json", "Cargo.toml", "pyproject.toml", ".git", "go.mod", "Package.swift")))
    return {"files": n, "extensions": dict(sorted(exts.items(), key=lambda kv: -kv[1])[:8]),
            "markers": markers, "subprojects": subprojects}


def contents_line(c: dict) -> str:
    if not c["files"] and not c["markers"]:
        return "Contents: none"
    exts = ", ".join(f"{v} {k}" for k, v in c["extensions"].items())
    parts = [f"{c['files']}{'+' if c['files'] >= 5000 else ''} files ({exts})" if c["files"] else "no files"]
    if c["markers"]:
        parts.append("markers: " + ", ".join(c["markers"]))
    if c["subprojects"]:
        parts.append(f"{c['subprojects']} sub-project folder(s)")
    return "Contents: " + " · ".join(parts)


def top_level_entries(d: Path) -> int:
    try:
        return sum(1 for p in d.iterdir() if not p.name.startswith("."))
    except Exception:
        return 0


def _git(d: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def fork_parent(remote: str) -> str | None:
    """'owner/repo' this GitHub repo was forked from, or None (uses the gh CLI; network)."""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
    if not m:
        return None
    try:
        out = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "isFork,parent"],
                             capture_output=True, text=True, timeout=20).stdout
        info = json.loads(out or "{}")
        par = info.get("parent") or {}
        return f"{(par.get('owner') or {}).get('login', '?')}/{par.get('name', '?')}" if info.get("isFork") else None
    except Exception:
        return None


_SWEEPS: set[str] = set()   # filled by collect() from subjects shared across repos


def _is_sweep(subject: str) -> bool:
    return (normalize_subject(subject) in _SWEEPS
            or any(a.lower() in subject.lower() for a in AUTOMATED))


def git_facts(d: Path, owners: list[str], forks: bool = False) -> dict:
    if not (d / ".git").exists():
        return {"is_git": False}
    remote = _git(d, "remote", "get-url", "origin")
    m = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?$", remote)
    owner = m.group(1) if m else ""
    # Author date (%as), not committer date: a rebase rewrites committer dates to "today" and
    # would make old or automated commits look like fresh work.
    log = _git(d, "log", "--format=%as%x09%s", "-n", "400")
    commits = [ln.split("\t", 1) for ln in log.splitlines() if "\t" in ln]
    hand = [c for c in commits if not _is_sweep(c[1])]
    parent = fork_parent(remote) if (forks and owner in owners) else None
    return {"is_git": True, "remote": remote, "remote_owner": owner, "fork_of": parent,
            "own_work": (owner in owners and not parent) if owner else None,
            "commits": int(_git(d, "rev-list", "--count", "HEAD") or 0),
            # max, not first: a rebase can reorder the log
            "last_commit": max((c[0] for c in commits), default=None),
            "last_hand_commit": max((c[0] for c in hand), default=None),
            "_subjects": sorted({normalize_subject(c[1]) for c in commits})}


def folder_text(name: str, d: Path) -> str:
    """What Jev sees: name, package description, entry count (a number, no file names), README."""
    parts = [f"Folder: {name}"]
    desc = package_description(d)
    if desc:
        parts.append(f"Package description: {redact(strip_markdown(desc))[:200]}")
    parts.append(f"Top-level entries (excluding hidden): {top_level_entries(d)}")
    parts.append(contents_line(contents_summary(d)))
    rd = readme_excerpt(d)
    parts.append(f"README excerpt: {rd}" if rd else "README: none")
    return "\n".join(parts)


def github_owners() -> list[str]:
    """Your GitHub login plus every org you belong to (gh CLI); [] if gh is unavailable."""
    try:
        me = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=20).stdout.split()
        orgs = subprocess.run(["gh", "api", "user/memberships/orgs", "--jq", ".[].organization.login"],
                              capture_output=True, text=True, timeout=20).stdout.split()
        return me + orgs
    except Exception:
        return []


def detect_sweeps(repos: list[Path]) -> set[str]:
    """Normalized subjects that appear in SWEEP_MIN_REPOS+ repos: automated sweeps, not work."""
    seen: dict[str, int] = {}
    for d in repos:
        for subj in {normalize_subject(ln) for ln in _git(d, "log", "--format=%s", "-n", "400").splitlines()}:
            seen[subj] = seen.get(subj, 0) + 1
    return {s for s, n in seen.items() if n >= SWEEP_MIN_REPOS and s}


def collect(root: Path, owners: list[str], forks: bool = False) -> list[dict]:
    folders = sorted((p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.name.lower())
    _SWEEPS.clear()
    _SWEEPS.update(detect_sweeps([d for d in folders if (d / ".git").exists()]))
    rows = []
    for d in folders:
        rows.append({"id": d.name, "top_level_entries": top_level_entries(d), "contents": contents_summary(d),
                     "package_description": package_description(d), **git_facts(d, owners, forks),
                     "text": folder_text(d.name, d)})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="facts about project folders (git + filesystem), no Jev")
    ap.add_argument("root", nargs="?", default=str(Path.home() / "Projects"))
    ap.add_argument("--out", help="write jsonl here (default: stdout)")
    ap.add_argument("--owners", default="auto",
                    help="comma-separated accounts/orgs that count as your own work; 'auto' = your GitHub "
                         "login + orgs (gh); pass --owners if gh isn't signed in")
    ap.add_argument("--forks", action="store_true", help="ask GitHub (gh CLI) which of your repos are forks")
    a = ap.parse_args()
    owners = [o.strip() for o in a.owners.split(",") if o.strip()] if a.owners != "auto" else \
        github_owners()
    rows = collect(Path(a.root).expanduser(), owners, a.forks)
    for r in rows:
        r.pop("_subjects", None)
    if _SWEEPS:
        print("automated sweeps skipped (subject in %d+ repos): %s" % (SWEEP_MIN_REPOS, "; ".join(sorted(_SWEEPS))),
              file=sys.stderr)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    if a.out:
        Path(a.out).write_text(body)
        git = sum(r["is_git"] for r in rows)
        print(f"{len(rows)} folders ({git} git repos) → {a.out} · empty: "
              + ", ".join(r["id"] for r in rows if r["top_level_entries"] == 0))
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
