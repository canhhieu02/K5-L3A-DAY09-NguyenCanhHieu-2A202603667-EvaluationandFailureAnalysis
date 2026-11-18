"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    import math

    problems: list[str] = []

    # 1. Any metric value in pr["metrics"] that is NaN or inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric '{k}' is {v}")

    # 2. len(pr["rows"]) != manifest items x len(manifest seeds)
    manifest = pr.get("manifest", {})
    expected_rows = manifest.get("items", 0) * len(manifest.get("seeds", []))
    if len(pr.get("rows", [])) != expected_rows:
        problems.append(
            f"row count {len(pr.get('rows', []))} != manifest items ({manifest.get('items')}) x seeds ({len(manifest.get('seeds', []))})"
        )

    # 3. (item_id, seed) set differs from baseline
    pr_pairs = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])}
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append(f"(item_id, seed) set differs from baseline: {len(pr_pairs)} vs {len(base_pairs)}")

    # 4. evaluator_failures non-empty, or a row whose value for a graded spec metric is None
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty ({len(pr['evaluator_failures'])})")

    spec_metric_ids = {m["id"] for m in spec.get("metrics", []) if m.get("level") in ("trajectory", "step", "outcome")}
    for r in pr.get("rows", []):
        for mid in spec_metric_ids:
            if mid in r and r[mid] is None:
                problems.append(f"graded metric '{mid}' is None in row item={r.get('item_id')} seed={r.get('seed')}")
                break
        else:
            continue
        break

    # 5. base_spec ratchet check
    if base_spec:
        if spec.get("eval_set_version") == base_spec.get("eval_set_version"):
            base_metrics = {m["id"]: m for m in base_spec.get("metrics", [])}
            cur_metrics = {m["id"]: m for m in spec.get("metrics", [])}
            for mid, bm in base_metrics.items():
                if mid not in cur_metrics:
                    problems.append(f"metric '{mid}' disappeared from spec")
                    continue
                cm = cur_metrics[mid]
                if bm.get("blocking") and not cm.get("blocking"):
                    problems.append(f"metric '{mid}' blocking loosened: True -> False")
                b_th = bm.get("threshold", {})
                c_th = cm.get("threshold", {})
                if "min" in b_th:
                    if "min" not in c_th or c_th["min"] < b_th["min"]:
                        problems.append(f"metric '{mid}' min loosened: {c_th.get('min')} < {b_th['min']}")
                if "max" in b_th:
                    if "max" not in c_th or c_th["max"] > b_th["max"]:
                        problems.append(f"metric '{mid}' max loosened: {c_th.get('max')} > {b_th['max']}")
                if "max_increase" in b_th:
                    if "max_increase" not in c_th or c_th["max_increase"] > b_th["max_increase"]:
                        problems.append(f"metric '{mid}' max_increase loosened")
                if b_th.get("no_significant_drop") and not c_th.get("no_significant_drop"):
                    problems.append(f"metric '{mid}' no_significant_drop dropped")

            base_slices = {s["name"]: s for s in base_spec.get("slices", [])}
            cur_slices = {s["name"]: s for s in spec.get("slices", [])}
            for sname, bs in base_slices.items():
                if sname not in cur_slices:
                    problems.append(f"slice '{sname}' disappeared from spec")
                    continue
                cs = cur_slices[sname]
                if bs.get("blocking") and not cs.get("blocking"):
                    problems.append(f"slice '{sname}' blocking loosened: True -> False")
                if "min" in bs:
                    if "min" not in cs or cs["min"] < bs["min"]:
                        problems.append(f"slice '{sname}' min loosened: {cs.get('min')} < {bs['min']}")
                if "max" in bs:
                    if "max" not in cs or cs["max"] > bs["max"]:
                        problems.append(f"slice '{sname}' max loosened: {cs.get('max')} > {bs['max']}")
                if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
                    problems.append(f"slice '{sname}' no_significant_drop dropped")

    # 6. Check if an item's slice tags in PR rows differ from baseline's
    pr_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in pr.get("rows", [])}
    base_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    for item_id, base_s in base_slices.items():
        if item_id in pr_slices and pr_slices[item_id] != base_s:
            problems.append(f"item '{item_id}' slice tags differ from baseline: {pr_slices[item_id]} vs {base_s}")
            break

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        name = s["name"]
        metric = s["metric"]
        blocking = s.get("blocking", False)
        th = {k: v for k, v in s.items() if k not in ("name", "metric", "blocking")}

        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        val = sum(a.values()) / len(a) if a else None

        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        elif "max" in s and val > s["max"]:
            verdict = "fail"

        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{metric}"
        if verdict != "ok" and blocking:
            blocked.append(slice_id)

        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if blocking else "warn")
        val_str = f"{val:.4f}" if isinstance(val, (int, float)) else str(val)
        lines.append(f"  {slice_id:<22} {val_str:<8} {json.dumps(th):<40} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
