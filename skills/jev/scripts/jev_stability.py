#!/usr/bin/env python3
"""Repeatability test: run a calibration set N times and measure how much Jev's answers move.

One run's "0.76" only means something if the next run on identical input says about the
same. This asks every question N times and reports, by confidence band:

  flip      the answer itself changed between runs
  crossing  confidence landed above the review threshold in some runs and below in others
  spread    max − min confidence across runs

plus per-run accuracy (how much the headline number wobbles), whether a majority vote over
runs beats a single run, and how much safety margin above the threshold keeps an item from
ever dropping under it.

  python3 jev_stability.py household --runs 5 --yes [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev  # noqa: E402

BANDS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.0001)]


def load_set(name: str, spec_arg: str | None) -> tuple[list[dict], dict]:
    bundled = jev.SKILL_DIR / "calibration" / f"{name}.jsonl"
    data_p = bundled if bundled.exists() else Path(name)
    spec_p = Path(spec_arg.lstrip("@")) if spec_arg else data_p.with_name(data_p.name.replace(".jsonl", ".spec.json"))
    rows = [json.loads(l) for l in data_p.read_text().splitlines() if l.strip()]
    return rows, json.loads(spec_p.read_text())


def analyse(runs: list[dict], thr: float) -> dict:
    qs = list(runs[0]["questions"])
    by_item: dict[tuple[str, str], list[dict]] = {}
    for r in runs:
        for it in r["items"]:
            for k, a in it.get("answers", {}).items():
                by_item.setdefault((it["id"], k), []).append(a)
    out: dict = {"threshold": thr, "runs": len(runs), "questions": {}}
    for k in qs:
        cells = {iid: v for (iid, q), v in by_item.items() if q == k and len(v) == len(runs)}
        rows = []
        for iid, v in cells.items():
            sures = [a["sure"] for a in v]
            preds = [json.dumps(a["pred"]) for a in v]
            majority, votes = Counter(preds).most_common(1)[0]
            rows.append({"id": iid, "mean": sum(sures) / len(sures), "spread": max(sures) - min(sures),
                         "flip": len(set(preds)) > 1,
                         "crossing": min(sures) < thr <= max(sures),
                         "majority_correct": next(a["correct"] for a in v if json.dumps(a["pred"]) == majority),
                         "single_correct": [a["correct"] for a in v], "sures": sures})
        bands = []
        for lo, hi in BANDS:
            b = [x for x in rows if lo <= x["mean"] < hi]
            if b:
                bands.append({"band": f"{lo:.2f}–{min(hi, 1):.2f}", "n": len(b),
                              "flip": sum(x["flip"] for x in b) / len(b),
                              "crossing": sum(x["crossing"] for x in b) / len(b),
                              "mean_spread": sum(x["spread"] for x in b) / len(b)})
        per_run_acc = [sum(x["single_correct"][i] for x in rows) / len(rows) for i in range(len(runs))]
        margins = {}
        for m in (0.0, 0.05, 0.10):
            # a single observation at ≥ thr+m: how often did another run of the same item fall below thr?
            obs = [(x, s) for x in rows for s in x["sures"] if s >= thr + m]
            margins[f"+{m:.2f}"] = (sum(1 for x, _ in obs if min(x["sures"]) < thr) / len(obs)) if obs else None
        out["questions"][k] = {
            "items": len(rows), "flip_rate": sum(x["flip"] for x in rows) / len(rows),
            "crossing_rate": sum(x["crossing"] for x in rows) / len(rows),
            "per_run_accuracy": per_run_acc, "majority_accuracy": sum(x["majority_correct"] for x in rows) / len(rows),
            "bands": bands, "margin_drop_risk": margins,
            "most_unstable": sorted(({"id": x["id"], "sures": [round(s, 2) for s in x["sures"]], "flip": x["flip"]}
                                     for x in rows if x["crossing"] or x["flip"]), key=lambda x: -max(x["sures"]) + min(x["sures"]))[:8],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="repeatability test for a calibration set")
    ap.add_argument("dataset")
    ap.add_argument("--spec")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    rows, spec = load_set(a.dataset, a.spec)
    thr = float(jev.load_state().get("threshold", jev.REVIEW_THRESHOLD))
    est = (sum(len(r["text"]) for r in rows) // 4 + len(rows) * (len(json.dumps(spec["questions"])) // 4 + 150)) * a.runs
    if not a.yes:
        print(f"dry run: {len(rows)} items × {a.runs} runs · ~{est:,} input tokens · ~${est * jev.PRICE_PER_INPUT_TOKEN:.4f}. "
              f"Same data as calibrate. Re-run with --yes.")
        return 2
    runs = [jev.calibrate(rows, spec, workers=a.workers) for _ in range(a.runs)]
    res = analyse(runs, thr)
    res["cost_usd"] = round(sum(r["meta"]["cost_usd"] for r in runs), 5)
    print(f"{spec.get('name', a.dataset)}: {len(rows)} items × {a.runs} runs · ${res['cost_usd']:.4f} · threshold {thr}")
    for k, q in res["questions"].items():
        accs = ", ".join(f"{x:.0%}" for x in q["per_run_accuracy"])
        print(f"  {k}: answer flips on {q['flip_rate']:.0%} of items · crosses the {thr} line on {q['crossing_rate']:.0%} · "
              f"per-run accuracy {accs} · majority of {a.runs} {q['majority_accuracy']:.0%}")
        for b in q["bands"]:
            print(f"    mean sure {b['band']:10} n={b['n']:3}  flip {b['flip']:.0%}  cross {b['crossing']:.0%}  spread {b['mean_spread']:.2f}")
        print("    one answer at ≥ line+margin, yet another run fell below the line: "
              + ", ".join(f"{m} {v:.0%}" if v is not None else f"{m} n/a" for m, v in q["margin_drop_risk"].items()))
        if q["most_unstable"]:
            print("    least stable: " + "; ".join(f"{x['id']} {x['sures']}{' FLIP' if x['flip'] else ''}" for x in q["most_unstable"][:5]))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
