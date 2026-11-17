"""AFL-014: plots (harness/plots.py), FR-8. Figures are written under tmp_path only."""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import aggregate
import plots

FIX = ROOT / "tests/fixtures/plots"


def load(base: Path) -> list[tuple[Path, dict]]:  # type: ignore[type-arg]
    """Stand-in for aggregate.trial_dirs (same contract), used so the tests do not depend on it."""
    return [(p.parent, json.loads(p.read_text())) for p in sorted(base.glob("**/run.json"))]


def test_resample_carries_last_value_forward() -> None:
    grid = np.arange(0.0, 6.0)
    got = plots.resample([0.0, 2.0, 4.5], [5, 8, 9], grid)
    assert got.tolist() == [5, 5, 8, 8, 8, 9]


def test_resample_before_first_sample_uses_first_value() -> None:
    assert plots.resample([1.5], [7], np.array([0.0, 1.0, 2.0])).tolist() == [7, 7, 7]


def test_crash_series_is_step_from_zero(tmp_path: Path) -> None:
    d = FIX / "main/tlv_parser/uniform/s2"
    t, v = plots.trial_series(d, "tlv_parser", "unique_crashes")
    assert (t, v) == ([0.0, 2.0, 4.0], [0.0, 1.0, 2.0])
    assert plots.resample(t, v, np.arange(0.0, 6.0)).tolist() == [0, 0, 1, 1, 2, 2]


def test_main_writes_both_figures_nonanalysed_excluded(tmp_path: Path) -> None:
    res = _tree(tmp_path)
    assert plots.main([str(res)]) == 0
    figs = sorted(p.name for p in (res / "figures").iterdir())
    assert figs == ["tlv_parser_coverage.png", "tlv_parser_unique_crashes.png"]
    assert all((res / "figures" / f).stat().st_size > 1000 for f in figs)


def test_main_no_main_trial_exits_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copytree(FIX / "pilot", tmp_path / "r")
    assert plots.main([str(tmp_path / "r")]) == 1
    assert "no main-campaign trial" in capsys.readouterr().err


def test_empty_metrics_csv_is_clear_error(tmp_path: Path) -> None:
    (tmp_path / "metrics.csv").write_text("elapsed_s,execs,edges\n")
    with pytest.raises(ValueError, match="no rows"):
        plots.trial_series(tmp_path, "tlv_parser", "edges")


def test_is_analysed_uses_campaign_kind() -> None:
    assert plots.aggregate.is_main_trial(FIX / "main/tlv_parser/fast/s3", FIX)
    assert not plots.aggregate.is_main_trial(FIX / "pilot/first_pilot/tlv_parser/uniform/s1001", FIX)


def test_plot_metric_median_and_iqr_per_arm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    real = plots.plt.subplots

    def spy(*a, **k):  # type: ignore[no-untyped-def]
        fig, ax = real(*a, **k)
        captured["ax"] = ax
        return fig, ax

    monkeypatch.setattr(plots.plt, "subplots", spy)
    trials = [t for t in load(FIX / "main")]
    plots.plot_metric(trials, "tlv_parser", "edges", tmp_path / "e.png")
    ax = captured["ax"]
    labels = [ln.get_label() for ln in ax.get_lines()]
    assert labels == ["UNIFORM (n=2)", "FAST (n=3)"]
    assert len(ax.collections) == 2  # one IQR band per arm
    uni = ax.get_lines()[0].get_ydata()
    assert uni[-1] == 8.5  # median of final edges 9 and 8
    fast = ax.get_lines()[1].get_ydata()
    assert fast[-1] == 14  # median of final edges 14, 16, 13 (the mean would be 14.33)
    verts = ax.collections[1].get_paths()[0].vertices
    edges_at_end = sorted(set(verts[verts[:, 0] == verts[:, 0].max(), 1]))
    assert edges_at_end == [13.5, 15]  # IQR (min/max would give 13 and 16)


def test_plot_metric_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plots.plot_metric(load(FIX / "main"), "tlv_parser", "bogus", tmp_path / "x.png")
    with pytest.raises(ValueError):
        plots.plot_metric(load(FIX / "main"), "nope", "edges", tmp_path / "x.png")


def _refused(tmp_path: Path, camp: dict, capsys: pytest.CaptureFixture[str]) -> None:  # type: ignore[type-arg]
    res = tmp_path / "results"
    shutil.copytree(FIX, res)
    (res / "main" / "campaign.json").write_text(json.dumps(camp))
    assert plots.main([str(res)]) == 1
    assert "recorded aborts" in capsys.readouterr().err
    assert not (res / "figures").exists()


def test_aborted_main_campaign_refused_per_trial_marker(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = FIX / "main/tlv_parser/fast/s3"
    _refused(tmp_path, {"kind": "main", "trials": {str(d): {"aborted": True}}}, capsys)


def test_aborted_main_campaign_refused_campaign_level_null_trial(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _refused(tmp_path, {"kind": "main",
                        "aborted": [{"trial": None, "error": "runner received signal SIGINT"}]}, capsys)


def _tree(tmp_path: Path, finished: bool = True, truncated: bool = False) -> Path:
    """Copy of the fixture (budget 5 s) with finished_at and every trial run to the budget."""
    res = tmp_path / "results"
    shutil.copytree(FIX, res)
    cj = res / "main" / "campaign.json"
    cj.write_text(json.dumps({"kind": "main", **({"finished_at": "2026-11-16"} if finished else {})}))
    if not truncated:
        for m in res.glob("main/**/metrics.csv"):
            last = m.read_text().splitlines()[-1].split(",")
            if float(last[0]) < 5:
                with m.open("a") as f:
                    f.write(f"5,9,{last[2]}\n")
    return res


def test_guards_pass_on_complete_tree(tmp_path: Path) -> None:
    assert plots.main([str(_tree(tmp_path))]) == 0


def test_no_finished_at_refused_without_figure(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    res = _tree(tmp_path, finished=False)
    assert plots.main([str(res)]) == 1
    assert "finished_at" in capsys.readouterr().err and not (res / "figures").exists()


def test_truncated_trial_refused_without_figure(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    res = _tree(tmp_path, truncated=True)
    assert plots.main([str(res)]) == 1
    err = capsys.readouterr().err
    assert "truncated" in err and "fast/s3" in err and not (res / "figures").exists()
    assert aggregate.main([str(res)]) == 1  # same guard, same message
    assert capsys.readouterr().err == err


def test_plots_source_has_no_guard_logic() -> None:
    src = (ROOT / "harness/plots.py").read_text()
    assert "finished_at" not in src and "truncated" not in src and "< budget" not in src


def test_unique_crash_series_matches_load_trials(tmp_path: Path) -> None:
    run = tmp_path / "main"
    d = run / "toy_parser" / "fast" / "s1"
    d.mkdir(parents=True)
    (run / "campaign.json").write_text(json.dumps({"kind": "main", "finished_at": "x"}))
    (d / "run.json").write_text(json.dumps({"config": {
        "target": "targets/bin/toy_parser", "schedule": "fast", "seconds": 600.0, "seed": 1}}))
    (d / "metrics.csv").write_text("elapsed_s,execs,edges\n0,0,5\n600,9,5\n")
    events = [(5.0, "check"), (20.0, "no_stack"), (50.0, "scan"), (603.0, "other")]
    (d / "crash_events.csv").write_text(
        "elapsed_s,execs,signal,crash_site,path_id,saved\n"
        + "".join(f"{t},{i},11,{s},1,\n" for i, (t, s) in enumerate(events)))
    t, v = plots.trial_series(d, "toy_parser", "unique_crashes", 600.0)
    assert (t, v) == ([0.0, 5.0, 50.0], [0.0, 1.0, 2.0])
    assert v[-1] == aggregate.load_trials(tmp_path).iloc[0].unique_crashes == 2
