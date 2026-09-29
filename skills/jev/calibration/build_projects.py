#!/usr/bin/env python3
"""Build the `projects` calibration set from ~/Projects plus a hand-checked inventory.

Truth comes from the inventory's Kind column (projects-inventory.md, 2026-09-25):
  plain  Jev was ≥75% sure and a reviewer agreed  (tag: agreed — partly Jev's own label,
         so accuracy on these rows is optimistic)
  †      Jev was <75% sure; the reviewer decided      (tag: reviewer-call)
  ‡      Jev was confident and wrong; corrected      (tags: corrected, tricky)

Each item's text is what a folder-sorting call would reasonably see: the folder name, its
package description (package.json / Cargo.toml / pyproject.toml), up to 450 characters of
README with URLs and local paths stripped, and how many top-level entries it has (a number
only — no file names), so an empty folder is visibly empty instead of judged by its name.

  python3 build_projects.py [--inventory ~/Projects/projects-inventory.md] [--root ~/Projects]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = ["app", "tool", "library", "docs", "container", "empty"]
README_CHARS = 450


def parse_inventory(path: Path) -> dict[str, tuple[str, str]]:
    """{folder: (kind, mark)} from the markdown tables; mark is '', '†' or '‡'."""
    out = {}
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Project", "---") or set(cells[0]) <= {"-"}:
            continue
        m = re.match(r"^([a-z]+)\s*([†‡]?)$", cells[1])
        if m and m.group(1) in KINDS:
            out[cells[0]] = (m.group(1), m.group(2))
    return out


sys.path.insert(0, str(HERE.parent / "scripts"))
from project_facts import folder_text  # noqa: E402  (same text the projects preset sends)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default=str(Path.home() / "Projects" / "projects-inventory.md"))
    ap.add_argument("--root", default=str(Path.home() / "Projects"))
    a = ap.parse_args()
    truth = parse_inventory(Path(a.inventory).expanduser())
    root = Path(a.root).expanduser()
    rows, missing = [], []
    for name, (kind, mark) in sorted(truth.items(), key=lambda kv: kv[0].lower()):
        d = root / name
        if not d.is_dir():
            missing.append(name)
            continue
        tags = {"": ["agreed"], "†": ["reviewer-call"], "‡": ["corrected", "tricky"]}[mark]
        rows.append({"id": name, "text": folder_text(name, d), "truth": {"kind": kind}, "tags": tags})
    (HERE / "projects.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    spec = {
        "name": "Code projects",
        "unit": "folders",
        "description": ("Every folder in ~/Projects, labelled by kind in a reviewed inventory "
                        "(2026-09-25). Rows marked agreed were Jev-confident and reviewer-confirmed, "
                        "so they flatter the score; reviewer-call and corrected rows are the "
                        "independent test."),
        "context": "Folders in one developer's ~/Projects directory: their own apps and tools, "
                   "research, docs, downloaded code and holding folders.",
        "questions": {
            "kind": {
                "type": "choice",
                "instructions": "What kind of folder is described in `item`?",
                "criteria": {
                    "app": "An end-user application, website, game or interactive demo with a UI",
                    "tool": "A CLI, server, service, pipeline, runtime or utility that does work for "
                            "its operator or for other software",
                    "library": "A reusable package, framework or SDK meant to be imported by other code",
                    "docs": "Writing rather than working code: documentation, specs, research papers, "
                            "strategy or reference material",
                    "container": "A holding folder for several separate projects, worktrees, assets, "
                                 "exports or archives rather than one project",
                    "empty": "Nothing meaningful inside: no entries, or only placeholders or config",
                },
            }
        },
    }
    (HERE / "projects.spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    by = {}
    for r in rows:
        by[r["tags"][0]] = by.get(r["tags"][0], 0) + 1
    print(f"wrote {len(rows)} rows ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))})"
          + (f"; missing folders skipped: {', '.join(missing)}" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
