"""AFL-012: aggregation and pre-registered statistics (harness/aggregate.py). Synthetic trials only."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import aggregate as ag

BUDGET = 600.0


def trial(root: Path, target: str, schedule: str, seed: int, metrics: list[tuple[float, int]],
          crashes: list[tuple[float, str]] = (), kind: str = "main",  # type: ignore[assignment]
          budget: float = BUDGET, finish: bool = True) -> Path:
    """Synthetic trial. `finish` appends the final row at the budget a time-stopped trial always
    writes (fuzzer.py), unless the rows already reach it, and marks the campaign finished."""
    if finish and metrics and metrics[-1][0] < budget:
        metrics = [*metrics, (budget, metrics[-1][1])]
    run = root / kind
    run.mkdir(parents=True, exist_ok=True)
    cj = run / "campaign.json"
    prev = json.loads(cj.read_text()) if cj.exists() else {"targets": []}
    cj.write_text(json.dumps({"kind": kind, "allow_fewer_targets": "test: only some targets",
                              "targets": sorted({*prev["targets"], target}),
                              **({"finished_at": "2026-11-16T00:00:00"} if finish else {})}))
    d = run / target / schedule / f"s{seed}"
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"config": {
        "target": f"targets/bin/{target}", "schedule": schedule, "seconds": budget, "seed": seed}}))
    with (d / "metrics.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["elapsed_s", "execs", "edges"])
        w.writerows((t, 0, e) for t, e in metrics)
    with (d / "crash_events.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["elapsed_s", "execs", "signal", "crash_site", "path_id", "saved"])
        w.writerows((t, i, 11, site, 1, "") for i, (t, site) in enumerate(crashes))
    return d


def camp(root: Path) -> dict:
    return json.loads((root / "main" / "campaign.json").read_text())


def test_trial_dirs_and_main_filter(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    trial(tmp_path, "toy_parser", "fast", 2, [(0, 5)], kind="pilot")
    got = ag.trial_dirs(tmp_path)
    assert len(got) == 2 and all(isinstance(rj, dict) and "config" in rj for _, rj in got)
    df = ag.load_trials(tmp_path)
    assert list(df.seed) == [1]  # pilot excluded by campaign.json kind


def test_bare_run_without_campaign_json_excluded(tmp_path: Path) -> None:
    d = trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    (d.parent.parent.parent / "campaign.json").unlink()
    assert ag.load_trials(tmp_path).empty


def test_final_edges_and_auc(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 10), (100, 20)])
    r = ag.load_trials(tmp_path).iloc[0]
    assert r.final_edges == 20 and r.edges_auc == 11000


def test_auc_zero_before_first_row() -> None:
    assert ag.edges_auc([(100, 20)], 600) == 10000


def test_a12_and_compare() -> None:
    assert ag.a12([1, 2, 3], [1, 2, 3]) == 0.5
    assert ag.a12([4, 5], [1, 2]) == 1.0 and ag.a12([1, 2], [4, 5]) == 0.0
    c = ag.compare([4, 5, 6, 7], [1, 2, 3, 3.5])
    assert c["a12"] == 1.0 and c["U"] == 16 and 0 < c["p"] < 0.05


def test_compare_all_tied() -> None:
    c = ag.compare([7.0] * 5, [7.0] * 5)
    assert c["p"] == 1.0 and c["a12"] == 0.5


def test_holm_example() -> None:
    adj = ag.holm([0.001, 0.011, 0.012, 0.04, 0.3, 0.6])
    assert adj == pytest.approx([0.006, 0.055, 0.055, 0.12, 0.6, 0.6])
    assert [a < 0.05 for a in adj] == [True] + [False] * 5


def test_holm_input_order_and_ties() -> None:
    adj = ag.holm([0.04, 0.01, 0.01])
    assert adj == pytest.approx([0.04, 0.03, 0.03])


def test_primary_family_constant() -> None:
    assert ag.PRIMARY_FAMILY == (
        ("toy_parser", "final_edges"), ("tlv_parser", "final_edges"),
        ("mini_format", "final_edges"), ("toy_parser", "ttfc:toy-1"),
        ("tlv_parser", "ttfc:tlv-2"), ("mini_format", "ttfc:mfp-1"))


def test_deep_bug_ids_in_real_ground_truth() -> None:
    truth = json.loads((ROOT / "targets" / "ground_truth.json").read_text())
    for target, metric in ag.PRIMARY_FAMILY:
        if metric.startswith("ttfc:"):
            bug = metric.split(":")[1]
            assert truth[bug]["target"] == target


def many(root: Path, target: str, n: int, fast_edges: int, uni_edges: int,
         fast_crash: float | None = None, uni_crash: float | None = None) -> None:
    for i in range(n):
        for sched, edges, crash in (("fast", fast_edges, fast_crash),
                                    ("uniform", uni_edges, uni_crash)):
            trial(root, target, sched, i, [(0, edges + i)],
                  [(crash + i, "check")] if crash is not None else [])


def test_summary_rows_and_labels(tmp_path: Path) -> None:
    many(tmp_path, "toy_parser", 10, 100, 50, 10.0, None)
    df = ag.load_trials(tmp_path)
    rows, removed = ag.build_summary(df, camp(tmp_path))
    by = {r["metric"]: r for r in rows}
    assert by["final_edges"]["family"] == "primary" and by["final_edges"]["significant"] is True
    assert by["final_edges"]["a12"] == 1.0 and by["final_edges"]["a12_favours"] == "FAST"
    assert by["edges_auc"]["family"] == "exploratory"
    assert by["edges_auc"]["p_holm"] == "" and by["edges_auc"]["significant"] == ""
    assert by["ttfc:toy-2"]["family"] == "exploratory"  # shallow/other bug, never found
    # only the toy_parser members exist: 4 removed, so m = 2
    assert len(removed) == 4
    ttfc = by["ttfc:toy-1"]
    assert ttfc["family"] == "primary" and ttfc["better"] == "smaller"
    assert ttfc["find_rate_fast"] == "10/10" and ttfc["find_rate_uniform"] == "0/10"
    assert ttfc["median_uniform"] == "> budget" and ttfc["a12"] == 0.0
    assert ttfc["a12_favours"] == "FAST" and not ttfc["low_n"]


def test_low_n_flag(tmp_path: Path) -> None:
    many(tmp_path, "toy_parser", 3, 100, 50)
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    assert all(r["low_n"] and r["n_fast"] == 3 for r in rows)


def test_exploratory_row_label_in_markdown(tmp_path: Path) -> None:
    many(tmp_path, "toy_parser", 10, 100, 50)
    assert ag.main([str(tmp_path)]) == 0
    md = (tmp_path / "summary.md").read_text()
    line = next(ln for ln in md.splitlines() if "edges_auc" in ln)
    assert "exploratory (uncorrected)" in line
    primary = next(ln for ln in md.splitlines() if "| final_edges |" in ln)
    assert "exploratory" not in primary
    assert "family" in (tmp_path / "summary.csv").read_text().splitlines()[0]


def test_censored_quantiles() -> None:
    six_cens = [1.0, 2.0, 3.0, 4.0] + [None] * 6
    assert ag.censored_quantiles(six_cens, BUDGET)[1] == "> budget"
    assert ag.censored_quantiles([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, None, None],
                                 BUDGET)[1] == 5.5


def test_censored_kept_in_test_input_and_all_censored(tmp_path: Path) -> None:
    for i in range(10):
        for s in ("fast", "uniform"):
            trial(tmp_path, "toy_parser", s, i, [(0, 5)])
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    t = next(r for r in rows if r["metric"] == "ttfc:toy-1")
    assert t["n_fast"] == t["n_uniform"] == 10  # censored trials not dropped
    assert t["p"] == 1.0 and t["a12"] == 0.5 and t["family"] == "primary"
    assert t["find_rate_fast"] == "0/10" and t["median_fast"] == "> budget"


def test_six_of_ten_censored_find_rate(tmp_path: Path) -> None:
    for i in range(10):
        trial(tmp_path, "toy_parser", "uniform", i, [(0, 5)], [(1.0 + i, "check")] if i < 4 else [])
        trial(tmp_path, "toy_parser", "fast", i, [(0, 5)], [(1.0 + i, "check")])
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    t = next(r for r in rows if r["metric"] == "ttfc:toy-1")
    assert t["find_rate_uniform"] == "4/10" and t["median_uniform"] == "> budget"
    assert t["n_uniform"] == 10


def test_half_censored_median_not_determinable() -> None:
    assert ag.censored_quantiles([1.0] * 5 + [None] * 5, BUDGET)[1] == ">= 1 " + ag.HALF_CENSORED


def test_late_find_after_budget_is_censored(tmp_path: Path) -> None:
    for i in range(10):
        trial(tmp_path, "toy_parser", "uniform", i, [(0, 5)])
        trial(tmp_path, "toy_parser", "fast", i, [(0, 5)], [(BUDGET + 3.0, "check")])
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    t = next(r for r in rows if r["metric"] == "ttfc:toy-1")
    assert t["find_rate_fast"] == "0/10" and t["p"] == 1.0


def test_censored_ranks_above_observed_beyond_budget() -> None:
    fast = [10.0, 20.0, BUDGET + 3.0] + [ag.CENSORED] * 7
    c = ag.compare(fast, [ag.CENSORED] * 10)
    assert c["U"] == 35 and c["p"] == pytest.approx(0.078, abs=0.001)


def test_sentinel_counts_and_flag(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)], [(1.0, "unsymbolized")])
    trial(tmp_path, "toy_parser", "fast", 2, [(0, 5)], [(1.0, "no_stack")])
    trial(tmp_path, "toy_parser", "uniform", 3, [(0, 5)], [(1.0, "check")])
    df = ag.load_trials(tmp_path).set_index("seed")
    assert df.loc[1, "sentinel:unsymbolized"] == 1 and df.loc[1, "sentinel:no_stack"] == 0
    assert df.loc[2, "sentinel:no_stack"] == 1 and df.loc[2, "sentinel:no_target_frame"] == 0
    assert all(df.loc[3, f"sentinel:{s}"] == 0 for s in ag.SENTINEL_NAMES)
    assert ag.main([str(tmp_path)]) == 0
    for name in ("summary.csv", "summary.md"):
        text = (tmp_path / name).read_text()
        assert "toy_parser/fast/seed 1: unsymbolized=1" in text
        assert "toy_parser/fast/seed 2: no_stack=1" in text
        assert "seed 3" not in text
    with (tmp_path / "trials.csv").open(newline="") as f:
        t = {r["seed"]: r for r in csv.DictReader(f)}
    assert len(t) == 3 and t["1"]["sentinel:unsymbolized"] == "1"
    assert t["2"]["sentinel:no_stack"] == "1" and t["3"]["sentinel:no_stack"] == "0"
    assert {"target", "schedule", "seed", "sentinel:no_target_frame"} <= set(t["1"])


def test_unique_crashes_counts_buckets(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)],
          [(1.0, "check"), (2.0, "check"), (3.0, "scan"), (4.0, "no_stack")])
    r = ag.load_trials(tmp_path).iloc[0]
    assert r.unique_crashes == 2 and r["ttfc:toy-1"] == 1.0 and r["ttfc:toy-2"] == 3.0
    assert r["sentinel:no_stack"] == 1


def test_smoke_and_excluded_trials_skipped(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    trial(tmp_path, "toy_parser", "fast", 2, [(0, 5)], kind="smoke")
    d = trial(tmp_path, "toy_parser", "fast", 3, [(0, 5)], kind="other")
    (d.parent.parent.parent / "campaign.json").write_text(
        json.dumps({"kind": "main", "excluded_from_analysis": True}))
    assert [rj["config"]["seed"] for _, rj in ag.trial_dirs(tmp_path)] == [1]
    assert list(ag.load_trials(tmp_path).seed) == [1]


def test_aborted_trials_dropped(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    d2 = trial(tmp_path, "toy_parser", "fast", 2, [(0, 5)])
    d3 = trial(tmp_path, "toy_parser", "uniform", 3, [(0, 5)])
    camp = tmp_path / "main" / "campaign.json"
    camp.write_text(json.dumps({"kind": "main", "trials": {str(d2): {"aborted": True}},
                                "aborted": [{"trial": str(d3), "error": "x"}]}))
    assert [rj["config"]["seed"] for _, rj in ag.trial_dirs(tmp_path)] == [1]
    assert not ag.is_main_trial(d2, tmp_path) and not ag.is_main_trial(d3, tmp_path)
    with pytest.raises(ValueError, match="recorded aborts"):
        ag.load_trials(tmp_path)  # Q11: aborted main campaign refused


def test_campaign_level_abort_with_null_trial(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    (tmp_path / "main" / "campaign.json").write_text(json.dumps(
        {"kind": "main", "aborted": [{"trial": None, "error": "runner received signal SIGINT"}]}))
    assert [rj["config"]["seed"] for _, rj in ag.trial_dirs(tmp_path)] == [1]  # no TypeError
    assert ag.main([str(tmp_path)]) == 1  # refused, not analysed


def test_missing_target_without_override_raises(tmp_path: Path) -> None:
    many(tmp_path, "toy_parser", 10, 100, 50)
    df = ag.load_trials(tmp_path)
    c = camp(tmp_path)
    with pytest.raises(ValueError, match="tlv_parser"):
        ag.build_summary(df, {**c, "allow_fewer_targets": None})
    with pytest.raises(ValueError, match="tlv_parser"):  # override set but target was in the run
        ag.build_summary(df, {**c, "targets": ["toy_parser", "tlv_parser", "mini_format"]})
    rows, removed = ag.build_summary(df, c)
    assert len(removed) == 4 and rows


def test_removed_members_and_reason_in_summary(tmp_path: Path) -> None:
    many(tmp_path, "toy_parser", 10, 100, 50)
    assert ag.main([str(tmp_path)]) == 0
    md = (tmp_path / "summary.md").read_text()
    assert "m = 2 of 6" in md and "test: only some targets" in md and "tlv_parser/final_edges" in md


def test_missing_arm_error_names_target_and_metric(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    with pytest.raises(ValueError, match="toy_parser final_edges"):
        ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))


def test_differing_budgets_raise(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    trial(tmp_path, "toy_parser", "uniform", 2, [(0, 5)], budget=300.0)
    with pytest.raises(ValueError, match="different budgets"):
        ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))


def test_low_n_uses_min_of_arm_sizes(tmp_path: Path) -> None:
    for i in range(3):
        trial(tmp_path, "toy_parser", "fast", i, [(0, 5 + i)])
    for i in range(10):
        trial(tmp_path, "toy_parser", "uniform", i, [(0, 50 + i)])
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    assert all(r["low_n"] and r["n_fast"] == 3 and r["n_uniform"] == 10 for r in rows)


def test_refusal_from_per_trial_aborted_marker_only(tmp_path: Path) -> None:
    d = trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)])
    (tmp_path / "main" / "campaign.json").write_text(
        json.dumps({"kind": "main", "trials": {str(d): {"aborted": True}}}))
    with pytest.raises(ValueError, match="recorded aborts"):
        ag.main_campaign(tmp_path)
    assert ag.main([str(tmp_path)]) == 1


def test_several_main_campaigns_refused_naming_each(tmp_path: Path) -> None:
    for name in ("run_a", "run_b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "campaign.json").write_text(json.dumps({"kind": "main"}))
    with pytest.raises(ValueError, match="several main campaigns") as e:
        ag.main_campaign(tmp_path)
    assert "run_a" in str(e.value) and "run_b" in str(e.value)


def test_half_censored_wording_in_summary_md(tmp_path: Path) -> None:
    for i in range(10):
        trial(tmp_path, "toy_parser", "uniform", i, [(0, 5)], [(1.0 + i, "check")] if i < 5 else [])
        trial(tmp_path, "toy_parser", "fast", i, [(0, 5)], [(1.0 + i, "check")])
    assert ag.main([str(tmp_path)]) == 0
    lines = (tmp_path / "summary.md").read_text().splitlines()
    cell = next(ln for ln in lines if "| ttfc:toy-1 |" in ln)
    assert "not determinable (>= half not reached) [" in cell
    legend = next(ln for ln in lines if "Mann-Whitney" in ln)
    assert "not determinable (>= half not reached)" in legend and ag.STRADDLE in legend


def test_quartile_straddling_censored_not_determinable() -> None:
    # n = 10, 3 observed: q1 (h = 2.25) interpolates obs[2] and a censored time; q3 is wholly
    # censored; median wholly censored
    q1, med, q3 = ag.censored_quantiles([1.0, 2.0, 3.0] + [None] * 7, BUDGET)
    assert q1 == ">= 3 " + ag.STRADDLE and med == "> budget" and q3 == "> budget"
    # 7 observed: q3 (h = 6.75) interpolates obs[6] with a censored time
    q1, med, q3 = ag.censored_quantiles([float(i) for i in range(1, 8)] + [None] * 3, BUDGET)
    assert q3 == ">= 7 " + ag.STRADDLE and q1 == 3.25 and med == 4.5 + 1.0


def _full_tree(root: Path, truncated: int = 0) -> None:
    """10 trials per arm on toy_parser; the first `truncated` uniform ones stop at 120 s."""
    for i in range(10):
        trial(root, "toy_parser", "fast", i, [(0, 5 + i)])
        trial(root, "toy_parser", "uniform", i, [(0, 5), (120, 6 + i)], finish=i >= truncated)
    cj = root / "main" / "campaign.json"
    cj.write_text(json.dumps({**json.loads(cj.read_text()), "finished_at": "2026-11-16"}))


def _no_outputs(root: Path) -> bool:
    return not any((root / n).exists() for n in ("summary.csv", "summary.md", "trials.csv"))


def test_guard_no_finished_at(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _full_tree(tmp_path)
    cj = tmp_path / "main" / "campaign.json"
    cj.write_text(json.dumps({k: v for k, v in json.loads(cj.read_text()).items()
                              if k != "finished_at"}))
    assert ag.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "finished_at" in err and str(tmp_path / "main") in err and _no_outputs(tmp_path)


def test_guard_truncated_trials_probe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _full_tree(tmp_path, truncated=3)
    assert ag.main([str(tmp_path)]) == 1
    assert "truncated" in capsys.readouterr().err and _no_outputs(tmp_path)


def test_guard_complete_tree_passes(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    assert ag.main([str(tmp_path)]) == 0 and (tmp_path / "summary.md").exists()


def test_significant_decided_from_p_holm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = dict(zip(ag.PRIMARY_FAMILY, [0.001, 0.011, 0.012, 0.04, 0.3, 0.6], strict=True))
    monkeypatch.setattr(ag, "_row", lambda t, m, g: {
        "target": t, "metric": m, "p": raw.get((t, m), 0.5)})
    for i, t in enumerate(("toy_parser", "tlv_parser", "mini_format")):
        trial(tmp_path, t, "fast", i, [(0, 5)])
    rows, removed = ag.build_summary(ag.load_trials(tmp_path), {})
    by = {(r["target"], r["metric"]): r for r in rows if r["family"] == "primary"}
    assert not removed and len(by) == 6
    assert by[ag.PRIMARY_FAMILY[0]]["significant"] is True  # p_holm 0.006
    second = by[ag.PRIMARY_FAMILY[1]]  # raw 0.011 < 0.05, p_holm 0.055
    assert second["p"] < 0.05 and second["significant"] is False
    assert second["p_holm"] == pytest.approx(0.055)


def test_edges_auc_clipped_at_budget() -> None:
    assert ag.edges_auc([(0, 10), (100, 20), (605, 25)], 600) == 11000


def test_cutoff_final_edges_ignores_row_past_budget(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 10), (100, 20), (605, 25)])
    r = ag.load_trials(tmp_path).iloc[0]
    assert r.final_edges == 20 and r.edges_auc == 11000


def test_cutoff_unique_crashes_and_ttfc(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)], [(603.0, "check")])
    trial(tmp_path, "toy_parser", "uniform", 2, [(0, 5)], [(10.0, "check")])
    df = ag.load_trials(tmp_path).set_index("seed")
    assert df.loc[1, "unique_crashes"] == 0 and df.loc[1, "ttfc:toy-1"] != df.loc[1, "ttfc:toy-1"]
    assert df.loc[2, "unique_crashes"] == 1 and df.loc[2, "ttfc:toy-1"] == 10.0
    for i in range(10):
        trial(tmp_path, "toy_parser", "fast", 10 + i, [(0, 5)], [(603.0, "check")])
        trial(tmp_path, "toy_parser", "uniform", 10 + i, [(0, 5)])
    rows, _ = ag.build_summary(ag.load_trials(tmp_path), camp(tmp_path))
    t = next(r for r in rows if r["metric"] == "ttfc:toy-1")
    assert t["find_rate_fast"] == "0/11" and t["find_rate_uniform"] == "1/11"
    out = tmp_path / "t"
    out.mkdir()
    ag.write_outputs(rows, [], ag.load_trials(tmp_path), out)
    with (out / "trials.csv").open(newline="") as f:
        late = next(r for r in csv.DictReader(f) if r["seed"] == "1" and r["schedule"] == "fast")
    assert late["ttfc:toy-1"] == "" and late["unique_crashes"] == "0"


def test_sentinel_counts_include_rows_after_deadline(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)],
          [(1.0, "no_stack"), (700.0, "no_stack"), (701.0, "unsymbolized")])
    r = ag.load_trials(tmp_path).iloc[0]
    assert r["sentinel:no_stack"] == 2 and r["sentinel:unsymbolized"] == 1
    assert r.unique_crashes == 0


def test_unique_crashes_exclude_sentinel(tmp_path: Path) -> None:
    trial(tmp_path, "toy_parser", "fast", 1, [(0, 5)], [(1.0, "check"), (2.0, "no_stack")])
    r = ag.load_trials(tmp_path).iloc[0]
    assert r.unique_crashes == 1 and r["sentinel:no_stack"] == 1


def test_half_censored_median_lower_bound() -> None:
    q1, med, q3 = ag.censored_quantiles([10.0, 20.0, 30.0, 40.0, 50.0] + [None] * 5, BUDGET)
    assert med.startswith(">= 50 ") and "not determinable" in med and med.endswith(ag.HALF_CENSORED)
    assert q1 == 32.5 and q3 == "> budget"


def test_straddling_quartile_lower_bound() -> None:
    q1, med, q3 = ag.censored_quantiles([10.0, 20.0, 30.0] + [None] * 7, BUDGET)
    assert q1.startswith(">= 30 ") and "not determinable" in q1 and q1.endswith(ag.STRADDLE)
    assert med == "> budget" and q3 == "> budget"


def test_lower_bound_legend_in_summary_md(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    assert ag.main([str(tmp_path)]) == 0
    assert "lower bound" in (tmp_path / "summary.md").read_text()
