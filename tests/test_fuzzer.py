"""AFL-007: main loop (stubbed executor for logic, real toy_parser/tlv_parser for integration)."""
import ast
import csv
import hashlib
import json
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import pytest
from conftest import needs_clang

from fuzzer import fuzzer as fz
from fuzzer.corpus import Corpus, Seed
from fuzzer.executor import ExecResult, Executor
from fuzzer.fuzzer import FuzzConfig, crash_site, run, seed_files, validate_config

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "targets"
FIXTURE = ROOT / "tests/fixtures/tlv_parser_asan_memcpy.txt"
SRC = ROOT / "src/fuzzer/fuzzer.py"

Fn = Callable[[int, bytes], ExecResult]


def clean(*edges: int) -> ExecResult:
    return ExecResult(0, None, False, frozenset((e, 1) for e in edges), 0.001, b"")


def crash(edges: tuple[int, ...] = (1,), stderr: bytes = b"") -> ExecResult:
    return ExecResult(None, signal.SIGABRT, False, frozenset((e, 1) for e in edges), 0.001, stderr)


def report(func: str, src: str = "tgt.c") -> bytes:
    return (b"==1==ERROR: AddressSanitizer: x\n    #0 0x1 in __asan_memcpy+0x4 (lib.dylib:arm64+0x5)\n"
            + f"    #1 0x2 in {func} {src}:9\n    #2 0x3 in start+0x1 (dyld:arm64e+0x1)\n".encode())


class Stub:
    """Replaces Executor: result i (1-based exec index) = fn(i, data); `tick` advances a clock."""

    fn: Fn = staticmethod(lambda i, d: clean(1))
    calls: ClassVar[list[bytes]] = []
    clock: ClassVar[list[float] | None] = None
    init_cost = 0.0
    run_cost = 0.0

    def __init__(self, target: Path, timeout_s: float = 1.0) -> None:
        if Stub.clock is not None:
            Stub.clock[0] += Stub.init_cost

    def run(self, data: bytes) -> ExecResult:
        Stub.calls.append(data)
        if Stub.clock is not None:
            Stub.clock[0] += Stub.run_cost
        return Stub.fn(len(Stub.calls), data)

    def close(self) -> None:
        pass


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> type[Stub]:
    monkeypatch.setattr(fz, "Executor", Stub)
    Stub.calls = []
    Stub.clock = None
    Stub.fn = staticmethod(lambda i, d: clean(1))
    return Stub


def cfg(tmp: Path, **kw: object) -> FuzzConfig:
    seeds = tmp / "seeds"
    if not seeds.exists():
        seeds.mkdir()
        (seeds / "S0").write_bytes(b"seed0")
    base: dict[str, object] = {
        "target": tmp / "tgt", "schedule": "uniform", "seconds": 1e6, "seed": 1,
        "out_dir": tmp / "out", "seeds_dir": seeds, "max_execs": 20}
    return FuzzConfig(**{**base, **kw})  # type: ignore[arg-type]


def rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open()))


def metrics(tmp: Path) -> list[dict[str, str]]:
    return rows(tmp / "out/metrics.csv")


def events(tmp: Path) -> list[dict[str, str]]:
    return rows(tmp / "out/crash_events.csv")


# ---- seeds, validation -------------------------------------------------------------

def test_seed_files_skips_hidden_and_sorts(tmp_path: Path) -> None:
    for n in ("b", ".DS_Store", "a"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in seed_files(tmp_path)] == ["a", "b"]
    with pytest.raises(FileNotFoundError):
        seed_files(tmp_path / "nope")


def test_run_loads_only_s0_not_ds_store(stub: type[Stub], tmp_path: Path) -> None:
    c = cfg(tmp_path, max_execs=1)
    (c.seeds_dir / ".DS_Store").write_bytes(b"junk")
    run(c)
    assert stub.calls == [b"seed0"]


def test_run_loads_in_sorted_order(stub: type[Stub], tmp_path: Path) -> None:
    c = cfg(tmp_path, max_execs=2)
    (c.seeds_dir / "S0").unlink()
    (c.seeds_dir / "b").write_bytes(b"B")
    (c.seeds_dir / "a").write_bytes(b"A")
    stub.fn = staticmethod(lambda i, d: clean(i))  # each seed has a new edge
    run(c)
    assert stub.calls == [b"A", b"B"]


def test_subdirectory_never_a_seed(stub: type[Stub], tmp_path: Path) -> None:
    c = cfg(tmp_path, max_execs=1)
    (c.seeds_dir / "sub").mkdir()
    (c.seeds_dir / "sub" / "inner").write_bytes(b"nested")
    assert [p.name for p in seed_files(c.seeds_dir)] == ["S0"]
    run(c)
    assert stub.calls == [b"seed0"]


def test_only_subdirectory_raises_before_execution(stub: type[Stub], tmp_path: Path) -> None:
    c = cfg(tmp_path)
    (c.seeds_dir / "S0").unlink()
    (c.seeds_dir / "sub").mkdir()
    (c.seeds_dir / "sub" / "inner").write_bytes(b"nested")
    with pytest.raises(ValueError):
        run(c)
    assert stub.calls == []


def test_empty_or_missing_seeds_raise_before_execution(stub: type[Stub], tmp_path: Path) -> None:
    c = cfg(tmp_path)
    (c.seeds_dir / "S0").unlink()
    (c.seeds_dir / ".DS_Store").write_bytes(b"x")
    with pytest.raises(ValueError):
        run(c)
    with pytest.raises(FileNotFoundError):
        run(cfg(tmp_path, seeds_dir=tmp_path / "missing"))
    assert stub.calls == [] and not (tmp_path / "out/metrics.csv").exists()


@pytest.mark.parametrize("kw,name", [
    ({"max_execs": 0}, "max_execs"), ({"seconds": 0}, "seconds"),
    ({"seconds": -1}, "seconds"), ({"timeout_s": 0}, "timeout_s")])
def test_validation(stub: type[Stub], tmp_path: Path, kw: dict[str, object], name: str) -> None:
    c = cfg(tmp_path, **kw)
    with pytest.raises(ValueError, match=name) as ei:
        run(c)
    assert str(next(iter(kw.values()))) in str(ei.value)
    with pytest.raises(ValueError):
        validate_config(c)
    assert stub.calls == [] and not c.out_dir.exists()


def test_validate_config_order_names_first_failing_parameter(tmp_path: Path) -> None:
    both = [({"max_execs": 0, "seconds": 0}, "max_execs"),
            ({"seconds": 0, "timeout_s": 0}, "seconds"),
            ({"max_execs": 0, "seconds": 0, "timeout_s": 0}, "max_execs")]
    for kw, first in both:
        with pytest.raises(ValueError, match=f"^{first} must") as ei:
            validate_config(cfg(tmp_path, **kw))
        assert str(ei.value).startswith(first)


def test_max_execs_none_is_valid() -> None:
    validate_config(FuzzConfig(Path("t"), "uniform", 1.0, 1, Path("o"), Path("s")))


# ---- exec counting, stopping, clock ------------------------------------------------

def test_max_execs_one_runs_s0_only(stub: type[Stub], tmp_path: Path) -> None:
    run(cfg(tmp_path, max_execs=1))
    assert len(stub.calls) == 1
    assert [m["execs"] for m in metrics(tmp_path)] == ["1", "1"]


def test_max_execs_counts_s0_and_candidates(stub: type[Stub], tmp_path: Path) -> None:
    stub.fn = staticmethod(lambda i, d: crash() if i == 2 else clean(1))
    run(cfg(tmp_path, max_execs=7))
    assert len(stub.calls) == 7 and stub.calls[0] == b"seed0"
    assert metrics(tmp_path)[0]["execs"] == "1"  # row after S0
    assert metrics(tmp_path)[-1]["execs"] == "7"
    assert [e["execs"] for e in events(tmp_path)] == ["2"]  # first candidate is exec 2


def test_fake_clock_stop_and_setup_excluded(
        stub: type[Stub], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub.clock, stub.init_cost, stub.run_cost = [1000.0], 50.0, 1.0
    monkeypatch.setattr(time, "monotonic", lambda: Stub.clock[0])  # type: ignore[index]
    run(cfg(tmp_path, seconds=3.5, max_execs=None))
    assert len(stub.calls) == 4
    m = metrics(tmp_path)
    assert m[-1]["execs"] == "4" and float(m[0]["elapsed_s"]) == 1.0


def test_no_wall_clock_time_time() -> None:
    for n in ast.walk(ast.parse(SRC.read_text())):
        assert not (isinstance(n, ast.Attribute) and n.attr == "time"
                    and isinstance(n.value, ast.Name) and n.value.id == "time")
        assert not (isinstance(n, ast.ImportFrom) and n.module == "time"
                    and any(a.name == "time" for a in n.names))


# ---- loop semantics ----------------------------------------------------------------

def test_energy_below_one_raises(
        stub: type[Stub], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(fz.SCHEDULES, "zero", lambda s, c: 0)
    with pytest.raises(ValueError, match="energy"):
        run(cfg(tmp_path, schedule="zero"))
    assert len(stub.calls) == 1  # S0 only; no spinning


def test_mark_fuzzed_after_full_energy_and_observe_every_clean(
        stub: type[Stub], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, int, int]] = []

    def sched(s: Seed, c: Corpus) -> int:
        seen.append((s.id, s.times_selected, s.path_freq))
        return 3

    monkeypatch.setitem(fz.SCHEDULES, "probe", sched)
    run(cfg(tmp_path, schedule="probe", max_execs=1 + 3 * 2))
    # one seed; all execs clean on its path: f(i) counts S0 + every candidate; s(i) 0 then 1
    assert seen == [(0, 0, 1), (0, 1, 4)]


def test_crash_hang_never_enter_corpus(stub: type[Stub], tmp_path: Path) -> None:
    kinds = {2: crash((7,)), 3: ExecResult(None, None, True, frozenset(), 1.0, b"")}
    stub.fn = staticmethod(lambda i, d: kinds.get(i, clean(1)))
    run(cfg(tmp_path, max_execs=5))
    assert sorted(p.name for p in (tmp_path / "out/queue").iterdir()) == ["id_000000"]
    last = metrics(tmp_path)[-1]
    assert (last["hangs"], last["crash_events"], last["corpus_size"]) == ("1", "1", "1")


def test_hang_time_sums_exec_time(stub: type[Stub], tmp_path: Path) -> None:
    k = 4
    hang = ExecResult(None, None, True, frozenset(), 1.25, b"")
    stub.fn = staticmethod(lambda i, d: hang if i > 1 else clean(1))
    run(cfg(tmp_path, max_execs=k + 1))
    last = metrics(tmp_path)[-1]
    assert last["hangs"] == str(k) and float(last["hang_time_s"]) == k * 1.25


def test_no_hangs_writes_literal_zero_float(stub: type[Stub], tmp_path: Path) -> None:
    stub.fn = staticmethod(lambda i, d: clean(1, 2) if i == 3 else clean(1))
    run(cfg(tmp_path, max_execs=5))
    m = metrics(tmp_path)
    assert len(m) > 1 and {r["hang_time_s"] for r in m} == {"0.0"}


def test_metrics_columns_and_change_rows(stub: type[Stub], tmp_path: Path) -> None:
    stub.fn = staticmethod(lambda i, d: clean(1, 2) if i == 4 else clean(1))
    run(cfg(tmp_path, max_execs=6))
    m = metrics(tmp_path)
    assert list(m[0]) == ["elapsed_s", "execs", "edges", "corpus_size", "distinct_path_ids",
                          "crash_events", "crashes_saved", "hangs", "hang_time_s"]
    assert [r["execs"] for r in m] == ["1", "4", "6"]  # S0, new edge, final
    assert [r["distinct_path_ids"] for r in m] == ["1", "2", "2"]


def test_row_triggers_hang_none_crash_event_yes(stub: type[Stub], tmp_path: Path) -> None:
    hang = ExecResult(None, None, True, frozenset(), 1.0, b"")
    # exec 2 hang (no row), exec 3 crash on S0's edge only (crash_events is the sole change)
    script = {2: hang, 3: crash((1,))}
    stub.fn = staticmethod(lambda i, d: script.get(i, clean(1)))
    run(cfg(tmp_path, max_execs=5))
    m = metrics(tmp_path)
    assert [r["execs"] for r in m] == ["1", "3", "5"]  # S0, crash event, final
    assert (m[1]["hangs"], m[1]["crash_events"], m[1]["edges"]) == ("1", "1", "1")


def test_bucket_change_moves_corpus_and_paths_not_edges(stub: type[Stub], tmp_path: Path) -> None:
    """AFL-034 (d): metrics `edges` (-> final_edges) counts edge ids, not (edge, bucket) pairs."""
    bucket8 = ExecResult(0, None, False, frozenset({(1, 8)}), 0.001, b"")
    stub.fn = staticmethod(lambda i, d: bucket8 if i == 2 else ExecResult(
        0, None, False, frozenset({(1, 1)}), 0.001, b""))
    run(cfg(tmp_path, max_execs=5))
    m = metrics(tmp_path)
    assert {r["edges"] for r in m} == {"1"}
    assert (m[-1]["corpus_size"], m[-1]["distinct_path_ids"]) == ("2", "2")


def test_distinct_path_ids_counts_clean_and_crash_never_hang(
        stub: type[Stub], tmp_path: Path) -> None:
    script = {2: crash((1, 9)),  # path no clean exec took
              3: ExecResult(None, None, True, frozenset({(1, 1), (2, 1), (3, 1)}), 1.0, b"")}  # hang edges
    stub.fn = staticmethod(lambda i, d: script.get(i, clean(1)))
    run(cfg(tmp_path, max_execs=5))
    assert metrics(tmp_path)[-1]["distinct_path_ids"] == "2"  # {1}, {1,9}; not {1,2,3}
    assert metrics(tmp_path)[-1]["edges"] == "1"  # ADR-0005 s6: clean execs only; 9, 2, 3 stay out


def test_crash_only_edge_enters_edges_only_after_clean_reach(
        stub: type[Stub], tmp_path: Path) -> None:
    # ADR-0005 s6: edge 9 first reached by a crash stays out; a later clean exec brings it in
    script = {2: crash((1, 9)), 3: clean(1, 9)}
    stub.fn = staticmethod(lambda i, d: script.get(i, clean(1)))
    run(cfg(tmp_path, max_execs=4))
    by_execs = {r["execs"]: r["edges"] for r in metrics(tmp_path)}
    assert by_execs["1"] == "1"  # S0
    assert by_execs["2"] == "1"  # crash row (crash_events trigger): edge 9 not counted
    assert by_execs["3"] == "2"  # clean exec reaches 9: row fires, edges enters
    assert metrics(tmp_path)[-1]["edges"] == "2"


@pytest.mark.parametrize("bad", [crash((1,)), ExecResult(None, None, True, frozenset({(1, 1)}), 1.0, b"")],
                         ids=["crash", "hang"])
def test_bad_s0_raises_valueerror_after_one_exec(
        stub: type[Stub], tmp_path: Path, bad: ExecResult) -> None:
    stub.fn = staticmethod(lambda i, d: bad)
    with pytest.raises(ValueError):
        run(cfg(tmp_path))
    assert len(stub.calls) == 1


# ---- crash storage -----------------------------------------------------------------

def crashes(tmp: Path, script: dict[int, ExecResult], n: int) -> list[dict[str, str]]:
    Stub.fn = staticmethod(lambda i, d: script.get(i, clean(1)))
    run(cfg(tmp, max_execs=n))
    return events(tmp)


def test_save_rule_a_same_path_same_site(stub: type[Stub], tmp_path: Path) -> None:
    ev = crashes(tmp_path, {i: crash((5,), report("f")) for i in range(2, 7)}, 6)
    assert len(ev) == 5 and len(list((tmp_path / "out/crashes").glob("*.bin"))) == 1
    assert [e["saved"] != "" for e in ev] == [True, False, False, False, False]
    assert metrics(tmp_path)[-1]["crashes_saved"] == "1"


def test_save_rule_b_new_path(stub: type[Stub], tmp_path: Path) -> None:
    ev = crashes(tmp_path, {2: crash((5,), report("f")), 3: crash((6,), report("f"))}, 4)
    assert [e["saved"] for e in ev] == ["crashes/000000.bin", "crashes/000001.bin"]


def test_save_rule_c_seen_path_new_site_and_link(stub: type[Stub], tmp_path: Path) -> None:
    ev = crashes(tmp_path, {2: crash((5,), report("f")), 3: crash((5,), report("g")),
                            4: crash((5,), report("g"))}, 5)
    assert [e["saved"] != "" for e in ev] == [True, True, False]
    for e in ev:
        if e["saved"]:
            j = tmp_path / "out" / e["saved"].replace(".bin", ".json")
            assert (tmp_path / "out" / e["saved"]).exists()
            assert json.loads(j.read_text())["execs"] == int(e["execs"])
    first: dict[str, dict[str, str]] = {}
    for e in ev:
        first.setdefault(e["crash_site"], e)
    assert all(e["saved"] for e in first.values())


@pytest.mark.parametrize("stderr,site", [(b"", "no_stack"),
                                         (b"    #0 0x10 (lib+0x4)\n    #1 0x11 (lib+0x8)\n",
                                          "unsymbolized")])
def test_sentinels_counted(stub: type[Stub], tmp_path: Path, stderr: bytes, site: str) -> None:
    ev = crashes(tmp_path, {2: ExecResult(None, signal.SIGSEGV, False, frozenset({(3, 1)}), 0.0,
                                          stderr)}, 3)
    assert [e["crash_site"] for e in ev] == [site]
    assert metrics(tmp_path)[-1]["crash_events"] == "1"


# ---- crash_site --------------------------------------------------------------------

def test_crash_site_variants() -> None:
    assert crash_site(report("f"), "tgt.c") == "f"
    assert crash_site(b"", "tgt.c") == "no_stack"
    assert crash_site(b"#0 0x1 (a+0x1)\n", "tgt.c") == "unsymbolized"
    only_rt = (b"    #0 0x1 in __interceptor_free+0x4 (lib:arm64+0x5)\n"
               b"    #1 0x2 in abort+0x1 (libsystem_c.dylib:arm64+0x1)\n")
    assert crash_site(only_rt, "tgt.c") == "no_target_frame"
    assert crash_site(report("f", "other.c"), "tgt.c") == "no_target_frame"
    assert all(crash_site(s, "tgt.c") != "" for s in (b"", only_rt, report("f")))


def test_crash_site_real_report_fixture() -> None:
    assert crash_site(FIXTURE.read_bytes(), "tlv_parser.c") == "main"


@needs_clang
def test_fixture_not_stale() -> None:
    subprocess.run(["make", "-C", str(TARGETS), "bin/tlv_parser"], check=True)
    ex = Executor(TARGETS / "bin/tlv_parser")
    try:
        r = ex.run(b"A" + bytes([100]) + b"x" * 100)
    finally:
        ex.close()
    assert r.outcome == "crash"
    assert crash_site(r.stderr, "tlv_parser.c") == crash_site(FIXTURE.read_bytes(),
                                                              "tlv_parser.c")


# ---- determinism, NFR-1/2, blindness -----------------------------------------------

def hashed(i: int, d: bytes) -> ExecResult:
    h = hashlib.sha256(d).digest()
    return crash((h[0] % 5,), report("f" if h[1] % 2 else "g")) if h[2] % 17 == 0 \
        else clean(*{h[0] % 11, h[1] % 11, 100})


def stream(tmp: Path, name: str, seed: int) -> tuple[list[bytes], list[list[str]], list[list[str]]]:
    Stub.calls = []
    Stub.fn = staticmethod(hashed)
    (tmp / name).mkdir()
    run(cfg(tmp / name, seed=seed, max_execs=3000))

    def drop(rs: list[dict[str, str]]) -> list[list[str]]:
        return [[v for k, v in r.items() if k not in ("elapsed_s", "hang_time_s")] for r in rs]

    return (list(Stub.calls), drop(rows(tmp / name / "out/metrics.csv")),
            drop(rows(tmp / name / "out/crash_events.csv")))


def test_replay_same_seed_identical_different_seed_differs(
        stub: type[Stub], tmp_path: Path) -> None:
    a, b, c = stream(tmp_path, "a", 5), stream(tmp_path, "b", 5), stream(tmp_path, "c", 6)
    assert a == b and a[0] != c[0]
    assert a[1][-1][0] == "3000" and a[2]  # exec-indexed, crashes exercised
    assert len(a[1]) > 3  # corpus grew, so splice/pool path is covered


def test_single_rng_and_single_schedule_branch_and_blind_mutate() -> None:
    tree = ast.parse(SRC.read_text())
    ctors = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) in ("random.Random", "Random")]
    assert len(ctors) == 1
    sched = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and ast.unparse(n) == "cfg.schedule"]
    assert len(sched) == 1
    muts = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and ast.unparse(n.func) == "mutator.mutate"]
    assert len(muts) == 1
    assert [ast.unparse(a) for a in muts[0].args] == [
        "seed.data", "rng", "[s.data for s in corpus.seeds]"]


# ---- startup guard -----------------------------------------------------------------

def test_zero_edge_first_exec_aborts_before_metrics(stub: type[Stub], tmp_path: Path) -> None:
    stub.fn = staticmethod(lambda i, d: clean())
    with pytest.raises(RuntimeError, match="no instrumentation detected"):
        run(cfg(tmp_path))
    assert not (tmp_path / "out/metrics.csv").exists()


@needs_clang
def test_uninstrumented_target_aborts(tmp_path: Path) -> None:
    (tmp_path / "t.c").write_text("int main(void){return 0;}\n")
    subprocess.run(["cc", "-o", str(tmp_path / "t"), str(tmp_path / "t.c")], check=True)
    with pytest.raises(RuntimeError, match="no instrumentation detected"):
        run(cfg(tmp_path, target=tmp_path / "t"))
    assert not (tmp_path / "out/metrics.csv").exists()


# ---- integration -------------------------------------------------------------------

@needs_clang
@pytest.mark.slow
def test_uniform_finds_toy_parser_bug(tmp_path: Path) -> None:
    subprocess.run(["make", "-C", str(TARGETS), "bin/toy_parser"], check=True)
    c = FuzzConfig(TARGETS / "bin/toy_parser", "uniform", 1e6, 1, tmp_path / "out",
                   TARGETS / "seeds/toy_parser", max_execs=INTEG_EXECS)
    run(c)
    ev = rows(tmp_path / "out/crash_events.csv")
    assert ev and {e["crash_site"] for e in ev} <= {"check", "scan"}
    assert rows(tmp_path / "out/metrics.csv")[-1]["execs"] == str(INTEG_EXECS)


INTEG_EXECS = 1500  # seed 1: first toy_parser crash at exec 688 (scan); ~15 execs/s here
