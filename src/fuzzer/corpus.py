"""Seed corpus / queue management. [implements FR-3 / ticket AFL-004, ADR-0004]

Coverage acts here only through retention (CLAUDE.md s2): an input joins the corpus
iff it reveals a new edge. The corpus owns s(i) (`times_selected`) and f(i)
(`path_freq`); schedule.py only reads them. Nothing here knows the schedule (NFR-2).
"""
from dataclasses import dataclass
from pathlib import Path

from fuzzer import coverage
from fuzzer.executor import ExecResult


@dataclass
class Seed:
    id: int
    data: bytes
    edges: frozenset[int]
    path_id: int
    exec_time: float  # of the single run that retained the seed
    times_selected: int = 0  # s(i)
    path_freq: int = 0  # f(i): clean execs on this seed's path

    @property
    def size(self) -> int:
        return len(self.data)


class Corpus:
    def __init__(self, out_dir: Path) -> None:
        self._queue_dir = Path(out_dir) / "queue"
        self.seeds: list[Seed] = []  # insertion order; read by schedule (AFL-006)
        self.seen: set[int] = set()  # lookup-only, never iterated for decisions
        self._path_count: dict[int, int] = {}
        self._seed_by_path: dict[int, Seed] = {}
        self._pos = 0

    def observe(self, data: bytes, result: ExecResult) -> Seed | None:
        """One call per clean execution: count its path, retain iff new edges."""
        if result.outcome != "clean":
            raise ValueError(f"observe() takes clean executions only, got {result.outcome}")
        pid = coverage.path_id(result.edges)
        self._path_count[pid] = self._path_count.get(pid, 0) + 1
        owner = self._seed_by_path.get(pid)
        if owner is not None:
            owner.path_freq = self._path_count[pid]
        if not coverage.has_new_edges(result.edges, self.seen):
            return None
        self.seen |= result.edges
        seed = Seed(len(self.seeds), data, result.edges, pid, result.exec_time,
                    path_freq=self._path_count[pid])
        self._queue_dir.mkdir(parents=True, exist_ok=True)
        (self._queue_dir / f"id_{seed.id:06d}").write_bytes(data)
        self.seeds.append(seed)
        self._seed_by_path[pid] = seed
        return seed

    def select(self) -> Seed:
        """Round-robin in insertion order, no RNG; mid-cycle appends join the cycle."""
        if not self.seeds:
            raise RuntimeError("select() on empty corpus")
        i = self._pos % len(self.seeds)  # length read now (ADR-0004 s4)
        self._pos = i + 1
        return self.seeds[i]

    def mark_fuzzed(self, seed: Seed) -> None:
        seed.times_selected += 1
