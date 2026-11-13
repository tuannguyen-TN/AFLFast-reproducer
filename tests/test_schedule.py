"""AFL-006, AFL-023 / FR-5: power schedules (table, purity, arm boundary)."""
import ast
import dataclasses
from pathlib import Path

import pytest

from fuzzer import schedule
from fuzzer.corpus import Corpus, Seed
from fuzzer.executor import ExecResult
from fuzzer.schedule import SCHEDULES, fast, next_p2, uniform

SRC = Path(schedule.__file__)


def make_corpus(n: int, tmp_path: Path) -> Corpus:
    c = Corpus(tmp_path)
    c.seeds = [Seed(i, b"x", frozenset({i}), i, 0.0, path_freq=1) for i in range(n)]
    return c


def snap(corpus: Corpus) -> list[dict[str, object]]:
    """Deep snapshot: catches in-place mutation of corpus members."""
    return [dataclasses.asdict(x) for x in corpus.seeds]


def make_seed(s: int, f: int, data: bytes = b"ab") -> Seed:
    return Seed(99, data, frozenset({1, 2}), 7, 0.5, times_selected=s, path_freq=f)


BIG = 11  # > SKIP_QUEUE_THRESHOLD
SMALL = 10


@pytest.mark.parametrize(
    ("s", "f", "n", "want"),
    [
        (0, 1, 1, 256), (0, 1, BIG, 256),
        (1, 100, 1, 16), (1, 100, 10, 16), (1, 100, 11, 1),
        (3, 5, 1, 256), (3, 5, BIG, 256),
        (4, 2, 1, 2048), (4, 2, BIG, 2048),
        (4, 1, 1, 4096), (4, 1, BIG, 4096),
        (15, 1, 1, 4096), (15, 1, BIG, 4096),
        (16, 1, 1, 4096), (16, 1, BIG, 4096),
        (16, 5, 1, 1024), (16, 5, BIG, 1024),
        (15, 33, 1, 4096), (15, 33, BIG, 4096),
        (16, 33, 1, 16), (16, 33, 11, 1),
        (10**6, 7, 1, 1024), (10**6, 7, BIG, 1024),
    ],
)
def test_fast_table(s: int, f: int, n: int, want: int, tmp_path: Path) -> None:
    corpus = make_corpus(n, tmp_path)
    seed = make_seed(s, f)
    before_seed, before_seeds = dataclasses.asdict(seed), snap(corpus)
    assert fast(seed, corpus) == want
    assert dataclasses.asdict(seed) == before_seed
    assert snap(corpus) == before_seeds


def test_next_p2() -> None:
    assert (next_p2(1), next_p2(32), next_p2(33)) == (1, 32, 64)


def test_uniform_constant_and_floor(tmp_path: Path) -> None:
    for n in (1, SMALL, BIG, 50):
        corpus = make_corpus(n, tmp_path)
        for s, f in [(0, 1), (4, 1), (16, 33), (10**6, 7), (1, 10**9)]:
            for data in (b"", b"a" * 5000):
                seed = make_seed(s, f, data)
                seed.exec_time = 1e9
                before, before_c = dataclasses.asdict(seed), snap(corpus)
                assert uniform(seed, corpus) == 256
                assert dataclasses.asdict(seed) == before
                assert snap(corpus) == before_c
                for fn in SCHEDULES.values():
                    e = fn(seed, corpus)
                    assert isinstance(e, int) and e >= 1
                    assert dataclasses.asdict(seed) == before
                    assert snap(corpus) == before_c


def test_schedules_registry() -> None:
    assert set(SCHEDULES) == {"uniform", "fast"}
    assert SCHEDULES["uniform"] is uniform and SCHEDULES["fast"] is fast


BANNED = {
    "random", "secrets", "numpy", "uuid", "time", "os", "urandom", "importlib", "__import__", "math",
}


def check_no_rng_or_clock(src: str) -> None:
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import | ast.ImportFrom):
            assert all(a.asname is None for a in n.names), f"import alias at {n.lineno}"
        if isinstance(n, ast.Import):
            assert not {a.name.split(".")[0] for a in n.names} & BANNED, f"banned import at {n.lineno}"
        if isinstance(n, ast.ImportFrom):
            assert (n.module or "").split(".")[0] not in BANNED, f"banned import at {n.lineno}"
            assert all(a.name not in BANNED for a in n.names), f"banned name at {n.lineno}"
        if isinstance(n, ast.Name):
            assert n.id not in BANNED, f"{n.id} at {n.lineno}"
        if isinstance(n, ast.Attribute):
            assert n.attr not in BANNED, f"{n.attr} at {n.lineno}"


def test_no_rng_or_clock_whole_module() -> None:
    check_no_rng_or_clock(SRC.read_text())


def test_imports_stdlib_plus_corpus_only() -> None:
    import sys

    tree = ast.parse(SRC.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            roots = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            assert n.level == 0
            roots = [n.module or ""]
        else:
            continue
        for m in roots:
            assert m == "fuzzer.corpus" or m.split(".")[0] in sys.stdlib_module_names, m


def full_state(c: Corpus) -> tuple[object, ...]:
    """Every Corpus field that schedule.py must leave untouched (AFL-023 AC1)."""
    return (
        snap(c), set(c.seen), dict(c._path_count),
        {k: dataclasses.asdict(v) for k, v in c._seed_by_path.items()}, c._pos,
    )


def clean(edge: int) -> ExecResult:
    return ExecResult(exit_status=0, signal=None, timed_out=False, edges=frozenset({edge}),
                      exec_time=0.0, stderr=b"")


def test_schedules_leave_corpus_state_untouched(tmp_path: Path) -> None:
    """AFL-023 AC1: R (no schedule), U, F stay state-identical after every step."""
    stream: list[tuple[str, int]] = [("obs", 0)] * 3 + [("round", 0)] * 17
    stream += [("obs", 1)] * 2 + [("obs", k) for k in range(2, 12)] + [("round", 0)] * 12
    runs = [(Corpus(tmp_path / n), fn) for n, fn in (("R", None), ("U", uniform), ("F", fast))]
    f_calls: list[tuple[int, int, int]] = []  # (s, len(seeds), energy) at call time
    repeats = 0
    for op, k in stream:
        for c, fn in runs:
            if op == "obs":
                got = c.observe(b"x", clean(k))
                repeats += got is None and fn is fast
                continue
            seed = c.select()
            if fn is not None:
                s, n = seed.times_selected, len(c.seeds)
                e = fn(seed, c)
                if fn is fast:
                    f_calls.append((s, n, e))
                else:
                    assert e == 256
            c.mark_fuzzed(seed)
        ref = full_state(runs[0][0])
        assert full_state(runs[1][0]) == ref, (op, k, "uniform diverged from R")
        assert full_state(runs[2][0]) == ref, (op, k, "fast diverged from R")
    assert len(runs[2][0].seeds) > 10  # (i)
    assert repeats >= 1  # (ii) observe without retention
    assert any(s >= 16 for s, _, _ in f_calls)  # (iii)
    energies = [e for _, _, e in f_calls]
    assert 16 in energies and 1 in energies  # (iv)


def test_schedule_attribute_access_whole_module() -> None:
    """AFL-023 AC2: only Load of seed.times_selected/path_freq and len(corpus.seeds)."""
    tree = ast.parse(SRC.read_text())
    parent = {id(ch): p for p in ast.walk(tree) for ch in ast.iter_child_nodes(p)}
    allowed = {"Seed": {"times_selected", "path_freq"}, "Corpus": {"seeds"}}
    names: dict[str, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for a in fn.args.args:
                if isinstance(a.annotation, ast.Name) and a.annotation.id in allowed:
                    names[a.arg] = a.annotation.id
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            assert not isinstance(n.func, ast.Attribute), f"method call at {n.lineno}"
        if not isinstance(n, ast.Attribute):
            continue
        assert isinstance(n.value, ast.Name) and n.value.id in names, f"attribute base at {n.lineno}"
        assert isinstance(n.ctx, ast.Load), f"non-Load access at {n.lineno}"
        assert n.attr in allowed[names[n.value.id]], f"{n.attr} read at {n.lineno}"
        if n.attr == "seeds":
            p = parent[id(n)]
            assert (isinstance(p, ast.Call) and isinstance(p.func, ast.Name)
                    and p.func.id == "len" and p.args == [n] and not p.keywords), \
                f"corpus.seeds outside len() at {n.lineno}"
