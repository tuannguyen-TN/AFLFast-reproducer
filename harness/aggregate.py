"""Statistical aggregation. [implements FR-9 / ticket AFL-012; PRD section 8]

Offline: reads a results directory, runs no fuzzing. Per (target x metric) it compares UNIFORM
vs FAST with a two-sided Mann-Whitney U test (pinned scipy call), the Vargha-Delaney effect
size A12(FAST, UNIFORM), medians and IQRs. Holm-Bonferroni corrects across the fixed primary
family only; every other row is exploratory and uncorrected. Time-to-first-crash of a bug a
trial never found is right-censored at the budget (never dropped, never clamped). Crash counts
use the honest crash-site dedup of dedup.py.

    python harness/aggregate.py results/        # writes results/summary.csv, summary.md
"""
import csv
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dedup

ALPHA = 0.05
LOW_N = 10
SENTINEL_NAMES = ("no_stack", "unsymbolized", "no_target_frame")
EDGE_METRICS = ("final_edges", "edges_auc", "unique_crashes")
# Primary family (PRD section 8, AFL-012), fixed order, never derived from data: (target, metric).
PRIMARY_FAMILY: tuple[tuple[str, str], ...] = (
    ("toy_parser", "final_edges"),
    ("tlv_parser", "final_edges"),
    ("mini_format", "final_edges"),
    ("toy_parser", "ttfc:toy-1"),
    ("tlv_parser", "ttfc:tlv-2"),
    ("mini_format", "ttfc:mfp-1"),
)
# Which direction is better, per metric kind.
HALF_CENSORED = "not determinable (>= half not reached)"
STRADDLE = "not determinable (interpolates a not-reached trial)"
BETTER = {"final_edges": "larger", "edges_auc": "larger", "unique_crashes": "larger"}


def _campaign(trial_dir: Path, results_dir: Path) -> dict:
    """Parsed nearest `campaign.json` above the trial, within `results_dir`; {} if none."""
    top = results_dir.resolve()
    for d in [trial_dir.resolve(), *trial_dir.resolve().parents]:
        c = d / "campaign.json"
        if c.is_file():
            return json.loads(c.read_text())
        if d == top:
            break
    return {}


def _aborted(trial_dir: Path, camp: dict) -> bool:
    """True if campaign.json marks this trial aborted: an "aborted" marker on its per-trial
    record, or an entry in the campaign's "aborted" list. Keys are matched on the trailing
    `<target>/<schedule>/s<seed>` path parts, so absolute or relative recorded paths both work."""
    tail = trial_dir.parts[-3:]
    recs = [k for k, v in camp.get("trials", {}).items() if v.get("aborted")]
    recs += [e["trial"] for e in camp.get("aborted", []) if e.get("trial") is not None]
    return any(Path(k).parts[-3:] == tail for k in recs)


def trial_dirs(results_dir: Path) -> list[tuple[Path, dict]]:
    """Every analysable trial directory under `results_dir` (it holds a `run.json`) with that
    file parsed, sorted by path. Skips any trial under a `smoke` path component of
    `results_dir` and any whose campaign.json says `excluded_from_analysis` or marks the trial aborted. Pilot and probe
    trials are still returned; `is_main_trial` keeps analysis to the main campaign.
    [AFL-012; reused by AFL-014]
    """
    out = []
    for p in sorted(results_dir.glob("**/run.json")):
        if "smoke" in p.parent.relative_to(results_dir).parts:
            continue
        camp = _campaign(p.parent, results_dir)
        if camp.get("excluded_from_analysis") or _aborted(p.parent, camp):
            continue
        out.append((p.parent, json.loads(p.read_text())))
    return out


def is_main_trial(trial_dir: Path, results_dir: Path) -> bool:
    """True iff the nearest `campaign.json` above the trial (within `results_dir`) says
    `"kind": "main"`. AFL-011 records the run kind there only, not in `run.json`; a trial with no
    campaign.json (a bare `fuzzer.cli` run) is not analysed. Pilot, probe and smoke are excluded.
    """
    camp = _campaign(trial_dir, results_dir)
    return camp.get("kind") == "main" and not _aborted(trial_dir, camp)


def _main_campaigns(results_dir: Path) -> list[tuple[Path, dict]]:
    """(directory, campaign.json) of every non-smoke, non-excluded main campaign."""
    mains = []
    for p in sorted(results_dir.glob("**/campaign.json")):
        c = json.loads(p.read_text())
        if ("smoke" not in p.parent.relative_to(results_dir).parts and c.get("kind") == "main"
                and not c.get("excluded_from_analysis")):
            mains.append((p.parent, c))
    return mains


def main_campaign(results_dir: Path) -> dict:
    """campaign.json of the one main campaign under `results_dir` ({} if there is none).
    Smoke and excluded campaigns are ignored. Raises ValueError if the main campaign recorded
    any abort (a per-trial `aborted` marker or a non-empty `aborted` list): an aborted campaign
    is unbalanced and is not analysed (default pending lead ruling, Q11), or if several exist."""
    mains = _main_campaigns(results_dir)
    for d, c in mains:
        if c.get("aborted") or any(v.get("aborted") for v in c.get("trials", {}).values()):
            raise ValueError(f"main campaign {d} recorded aborts; it is not analysed")
    if len(mains) > 1:
        raise ValueError(f"several main campaigns under {results_dir}: {[str(d) for d, _ in mains]}")
    return mains[0][1] if mains else {}


def check_complete(results_dir: Path) -> dict:
    """main_campaign(results_dir), refusing an unfinished or truncated main campaign (ValueError
    naming the directory): (a) its campaign.json has no `finished_at`; (b) a main trial's last
    metrics.csv `elapsed_s` is below its budget (`run.json` config.seconds), since a time-stopped
    trial always writes a final row at or past the deadline. Shared by aggregate and plots.
    [AFL-033 AC 1, AC 6]"""
    camp = main_campaign(results_dir)
    for d, c in _main_campaigns(results_dir):
        if "finished_at" not in c:
            raise ValueError(f"main campaign {d} has no finished_at in campaign.json: "
                             "unfinished or killed; it is not analysed")
    for d, rj in trial_dirs(results_dir):
        if not is_main_trial(d, results_dir):
            continue
        with (d / "metrics.csv").open(newline="") as f:
            last = [float(r["elapsed_s"]) for r in csv.DictReader(f)][-1:]
        budget = float(rj["config"]["seconds"])
        if not last or last[0] < budget:
            raise ValueError(f"trial {d} is truncated: last metrics row at "
                             f"{last[0] if last else 'none'} s of a {budget:g} s budget")
    return camp


def counted_buckets(buckets: Sequence[dedup.Bucket], budget: float) -> list[dedup.Bucket]:
    """Buckets that count as unique crashes: key not a sentinel and first seen by `budget`
    (Q4 sentinel exclusion, Q10 end-of-budget cutoff). Shared by aggregate's `unique_crashes`
    and plots' unique-crashes curve. [AFL-033 AC 3, 5, 7]"""
    return [b for b in buckets if b.key not in SENTINEL_NAMES and b.first_elapsed_s <= budget]


# ---- statistics (pure) ---------------------------------------------------------------------

def a12(x: Sequence[float], y: Sequence[float]) -> float:
    """Vargha-Delaney A12 = P(X > Y) + 0.5 P(X = Y); > 0.5 means X tends larger."""
    a, b = np.asarray(x, float)[:, None], np.asarray(y, float)[None, :]
    return float(((a > b).sum() + 0.5 * (a == b).sum()) / (a.size * b.size))


def holm(pvals: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values in input order; ties broken by input order."""
    m = len(pvals)
    adj = [0.0] * m
    run = 0.0
    for k, i in enumerate(sorted(range(m), key=lambda j: (pvals[j], j))):
        run = max(run, min(1.0, (m - k) * pvals[i]))
        adj[i] = run
    return adj


def quartiles(v: Sequence[float]) -> tuple[float, float, float]:
    """(q1, median, q3), linear interpolation."""
    q1, med, q3 = np.percentile(np.asarray(v, float), [25, 50, 75])
    return float(q1), float(med), float(q3)


def compare(fast: Sequence[float], uniform: Sequence[float]) -> dict[str, Any]:
    """FAST vs UNIFORM: U (of FAST), two-sided asymptotic p with continuity correction, A12."""
    if not len(fast) or not len(uniform):
        raise ValueError("compare needs at least one value per arm")
    out: dict[str, Any] = {"n_fast": len(fast), "n_uniform": len(uniform)}
    if len(set(fast) | set(uniform)) == 1:  # zero variance: scipy's p is undefined
        out.update(U=len(fast) * len(uniform) / 2, p=1.0, a12=0.5)
    else:
        r = mannwhitneyu(fast, uniform, alternative="two-sided", method="asymptotic",
                         use_continuity=True)
        out.update(U=float(r.statistic), p=float(r.pvalue), a12=a12(fast, uniform))
    return out


def censored_quantiles(values: Sequence[float | None], budget: float) -> list[Any]:
    """(q1, median, q3) of a TTFC sample, `None` = censored at `budget`. A quantile whose
    interpolation lies wholly in the censored tail is "> budget"; one that interpolates between an
    observed and a censored time is "not determinable" (HALF_CENSORED for the median at exactly
    half censored, STRADDLE for a quartile) and reports the lower bound ">= t", t the arm's
    largest observed time x(k) (Q3, AFL-033 AC 4); neither is a point estimate."""
    obs = sorted(v for v in values if v is not None)
    n, k = len(values), len(obs)
    full = obs + [budget + 1.0] * (n - k)
    res: list[Any] = []
    for q in (0.25, 0.5, 0.75):
        h = (n - 1) * q
        if math.floor(h) < k <= math.ceil(h) and math.floor(h) != math.ceil(h):
            # interpolates between an observed and a censored time: not determinable
            res.append(f">= {_fmt(obs[-1])} " + (HALF_CENSORED if q == 0.5 else STRADDLE))
        else:
            res.append("> budget" if math.ceil(h) >= k else float(np.percentile(full, q * 100)))
    return res


# ---- loading -------------------------------------------------------------------------------

def edges_auc(rows: list[tuple[float, float]], budget: float) -> float:
    """Area under the edges step function on [0, budget]; 0 before the first row."""
    auc = 0.0
    for i, (t, e) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else budget
        auc += e * max(0.0, min(end, budget) - min(t, budget))
    return auc


def _bugs(target: str) -> list[str]:
    truth = json.loads(dedup.GROUND_TRUTH.read_text())
    return [b for b, e in truth.items() if e["target"] == target]


def load_trials(results_dir: Path) -> pd.DataFrame:
    """One row per main-campaign trial: target, schedule, seed, budget, final_edges, edges_auc,
    unique_crashes (dedup buckets whose key is not a sentinel and first seen by the budget),
    `ttfc:<bug>` (NaN = bug not found,
    i.e. censored; only the trial's own target's bugs are real columns for that row) and the
    three `sentinel:<name>` crash-event counts (every crash_events row, past the budget too).
    Every endpoint is cut at the budget (Q10, AFL-033): `final_edges` is the last metrics row
    with elapsed_s <= budget, and buckets and crash events after it count for nothing.
    Target, schedule and seed come from run.json."""
    main_campaign(results_dir)  # refuses an aborted main campaign
    recs: list[dict[str, Any]] = []
    for d, rj in trial_dirs(results_dir):
        if not is_main_trial(d, results_dir):
            continue
        cfg = rj["config"]
        target, budget = Path(cfg["target"]).name, float(cfg["seconds"])
        with (d / "metrics.csv").open(newline="") as f:
            rows = [(float(r["elapsed_s"]), float(r["edges"])) for r in csv.DictReader(f)]
        if not rows:
            raise ValueError(f"{d}/metrics.csv has no data rows")
        buckets = dedup.bucket_trial(d, target)
        counted = counted_buckets(buckets, budget)
        in_budget = [r for r in rows if r[0] <= budget]
        if not in_budget:
            raise ValueError(f"{d}/metrics.csv has no row within the {budget:g} s budget")
        rec: dict[str, Any] = {
            "target": target, "schedule": cfg["schedule"], "seed": cfg["seed"], "budget": budget,
            "final_edges": in_budget[-1][1], "edges_auc": edges_auc(rows, budget),
            "unique_crashes": len(counted)}
        for bug in _bugs(target):
            rec[f"ttfc:{bug}"] = next((b.first_elapsed_s for b in counted if b.bug_id == bug), None)
        for s in SENTINEL_NAMES:
            rec[f"sentinel:{s}"] = sum(b.count for b in buckets if b.key == s)
        recs.append(rec)
    return pd.DataFrame(recs)


# ---- table ---------------------------------------------------------------------------------

CENSORED = math.inf  # one common value above every observed time: censored trials tie on top


def _compare(target: str, metric: str, fast: Sequence[float], uniform: Sequence[float]
             ) -> dict[str, Any]:
    try:
        return compare(fast, uniform)
    except ValueError as e:
        raise ValueError(f"{target} {metric}: {e} (fast n={len(fast)}, uniform n={len(uniform)})"
                         ) from e


def _row(target: str, metric: str, g: pd.DataFrame) -> dict[str, Any]:
    fast, uni = (g[g.schedule == s] for s in ("fast", "uniform"))
    row: dict[str, Any] = {"target": target, "metric": metric}
    arms: dict[str, Any]
    if metric.startswith("ttfc:"):
        budget = float(g.budget.iloc[0])
        # a first crash after the budget is censored (default pending lead ruling, Q10)
        arms = {s: [None if pd.isna(v) or v > budget else float(v) for v in a[metric]]
                for s, a in (("fast", fast), ("uniform", uni))}
        comp = _compare(target, metric, [CENSORED if v is None else v for v in arms["fast"]],
                        [CENSORED if v is None else v for v in arms["uniform"]])
        qs = {s: censored_quantiles(v, budget) for s, v in arms.items()}
        for s, v in arms.items():
            row[f"find_rate_{s}"] = f"{sum(x is not None for x in v)}/{len(v)}"
        row["better"] = "smaller"
    else:
        arms = {"fast": list(fast[metric]), "uniform": list(uni[metric])}
        comp = _compare(target, metric, arms["fast"], arms["uniform"])
        qs = {s: list(quartiles(v)) for s, v in arms.items()}
        row["better"] = BETTER[metric]
    for s in ("uniform", "fast"):
        row[f"n_{s}"] = comp[f"n_{s}"]
        row[f"q1_{s}"], row[f"median_{s}"], row[f"q3_{s}"] = qs[s]
    row.update(U=comp["U"], p=comp["p"], a12=comp["a12"])
    a = comp["a12"]
    row["a12_favours"] = "neither" if a == 0.5 else (
        "FAST" if (a > 0.5) == (row["better"] == "larger") else "UNIFORM")
    row["low_n"] = min(comp["n_fast"], comp["n_uniform"]) < LOW_N
    return row


def build_summary(df: pd.DataFrame, campaign: dict | None = None
                  ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Comparison rows plus the primary members removed. A member is removed only when
    `campaign` (the main campaign.json) has a non-empty `allow_fewer_targets` and the member's
    target is not in its `targets`; any other family target without data raises."""
    campaign = campaign or {}
    rows: list[dict[str, Any]] = []
    for target in sorted(df.target.unique()):
        g = df[df.target == target]
        if g.budget.nunique() != 1:
            raise ValueError(f"{target}: trials have different budgets {sorted(g.budget.unique())}")
        metrics = list(EDGE_METRICS) + [f"ttfc:{b}" for b in _bugs(target)]
        rows += [_row(target, m, g) for m in metrics]
    present = set(df.target.unique())
    allowed = bool(str(campaign.get("allow_fewer_targets") or "").strip())
    ran = set(campaign.get("targets", []))
    removed = [(t, m) for t, m in PRIMARY_FAMILY if t not in present]
    bad = sorted({t for t, _ in removed if not allowed or t in ran})
    if bad:
        raise ValueError(f"primary-family target(s) {bad} have no analysable trials and the "
                         "campaign was not run with --allow-fewer-targets without them")
    members = [(t, m) for t, m in PRIMARY_FAMILY if t in present]
    idx = {(r["target"], r["metric"]): r for r in rows}
    missing = [x for x in members if x not in idx]
    if missing:
        raise ValueError(f"primary family members without a row: {missing}")
    for (t, m), padj in zip(members, holm([idx[x]["p"] for x in members]), strict=True):
        idx[(t, m)].update(family="primary", p_holm=padj, significant=padj < ALPHA)
    for r in rows:
        if "family" not in r:
            r.update(family="exploratory", p_holm="", significant="")
    sent = _sentinel_flags(df)
    for r in rows:
        r["sentinel_flags"] = "; ".join(sent.get(r["target"], []))
    return rows, removed


def _sentinel_flags(df: pd.DataFrame) -> dict[str, list[str]]:
    flags: dict[str, list[str]] = {}
    for _, t in df.iterrows():
        for s in SENTINEL_NAMES:
            if t[f"sentinel:{s}"]:
                flags.setdefault(t.target, []).append(
                    f"{t.target}/{t.schedule}/seed {t.seed}: {s}={int(t[f'sentinel:{s}'])}")
    return flags


COLUMNS = ["target", "metric", "family", "n_uniform", "n_fast", "low_n",
           "median_uniform", "q1_uniform", "q3_uniform", "median_fast", "q1_fast", "q3_fast",
           "find_rate_uniform", "find_rate_fast", "U", "p", "p_holm", "significant",
           "a12", "better", "a12_favours", "sentinel_flags"]


def _fmt(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def write_outputs(rows: list[dict[str, Any]], removed: list[tuple[str, str]], df: pd.DataFrame,
                  out_dir: Path, reason: str = "") -> None:
    """trials.csv (one row per analysed trial, incl. sentinel counts), summary.csv (all columns)
    and summary.md (exploratory p-values labelled uncorrected)."""
    df.sort_values(["target", "schedule", "seed"]).to_csv(out_dir / "trials.csv", index=False)
    with (out_dir / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)
    m = len(PRIMARY_FAMILY) - len(removed)
    lines = ["# UNIFORM vs FAST summary", "",
             ("Two-sided Mann-Whitney U (alpha 0.05); A12 is A12(FAST, UNIFORM): > 0.5 means "
              "FAST's values tend to be larger, so smaller is better for TTFC. TTFC is "
              "right-censored at the budget (a first crash after it counts as not found); "
              "'> budget' is a quantile not reached; '" + HALF_CENSORED + "' means exactly half "
              "of an even-sized arm is censored; '" + STRADDLE + "' marks a quartile that falls "
              "between an observed time and a not-reached one. A cell starting '>= t' is a lower "
              "bound (t = the arm's largest observed time), not an estimate."), "",
             f"Primary family: m = {m} of {len(PRIMARY_FAMILY)}, Holm-Bonferroni."]
    if removed:
        lines.append("Removed members (target not run, --allow-fewer-targets, recorded reason: "
                     f"{reason!r}): " + ", ".join(f"{t}/{x}" for t, x in removed))
    lines += ["", ("| target | metric | family | n (U/F) | median U [q1,q3] | median F [q1,q3] "
                   "| find rate U / F | U | p | p_holm | significant | A12 | better | favours "
                   "| low n |"),
              "|" + "---|" * 15]
    for r in rows:
        p = _fmt(r["p"]) + (" exploratory (uncorrected)" if r["family"] == "exploratory" else "")
        cell = (lambda s, r=r: f"{_fmt(r[f'median_{s}'])} [{_fmt(r[f'q1_{s}'])}, "
                f"{_fmt(r[f'q3_{s}'])}]")
        rate = f"{r['find_rate_uniform']} / {r['find_rate_fast']}" if "find_rate_fast" in r else ""
        lines.append(" | ".join(["", r["target"], r["metric"], r["family"],
                                 f"{r['n_uniform']}/{r['n_fast']}", cell("uniform"), cell("fast"),
                                 rate, _fmt(r["U"]), p, _fmt(r["p_holm"]), str(r["significant"]),
                                 _fmt(r["a12"]), r["better"], r["a12_favours"],
                                 "LOW N (< 10)" if r["low_n"] else "", ""]).strip())
    flags = sorted({s for r in rows for s in r["sentinel_flags"].split("; ") if s})
    lines += ["", "## Crash-site sentinel flags (main campaign)", ""]
    lines += [f"- {s}" for s in flags] or ["none"]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not Path(args[0]).is_dir():
        print("usage: aggregate.py <results_dir>", file=sys.stderr)
        return 2
    out = Path(args[0])
    try:
        check_complete(out)
        df = load_trials(out)
        if df.empty:
            raise ValueError(f"no main-campaign trials under {out}")
        camp = main_campaign(out)
        rows, removed = build_summary(df, camp)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    write_outputs(rows, removed, df, out, str(camp.get("allow_fewer_targets") or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
