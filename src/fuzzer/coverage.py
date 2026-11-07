"""Edge-coverage collection from an instrumented target. [implements FR-1 / ticket AFL-002]

Mechanism (ADR-0001): the target's C runtime (targets/cov_rt.c) marks hit
trace-pc-guard ids in a POSIX shared-memory bitmap named by env FUZZ_SHM_NAME.
Edge presence only (no hit counts). Coverage never steers mutation (CLAUDE.md s2);
consumers treat edge ints as opaque and use has_new_edges / path_id only.
"""
import hashlib
import subprocess
from multiprocessing import shared_memory

import numpy as np

MAP_SIZE = 1 << 16


class ShmBitmap:
    """Shared-memory edge bitmap; the executor (AFL-003) owns and drives it."""

    def __init__(self, size: int = MAP_SIZE) -> None:
        self._shm = shared_memory.SharedMemory(create=True, size=size)
        assert self._shm.buf is not None  # always set for a live segment
        self._map = np.frombuffer(self._shm.buf, dtype=np.uint8)

    def env(self) -> dict[str, str]:
        """Environment that tells the target runtime where the bitmap lives."""
        return {"FUZZ_SHM_NAME": self._shm.name}

    def reset(self) -> None:
        self._map[:] = 0

    def edges(self) -> frozenset[int]:
        """Ids of edges hit since the last reset."""
        return frozenset(np.flatnonzero(self._map).tolist())

    def close(self) -> None:
        """Release and unlink the segment."""
        del self._map  # exported buffer must be dropped before close()
        self._shm.close()
        self._shm.unlink()


def has_new_edges(edges: frozenset[int], seen: set[int]) -> bool:
    """True if `edges` has an edge not in `seen`. Pure; the caller updates `seen`."""
    return not edges <= seen


def path_id(edges: frozenset[int]) -> int:
    """Stable 64-bit path identity (the only one in the package; FAST's f(i), AFL-006)."""
    h = hashlib.blake2b(digest_size=8)
    for e in sorted(edges):
        h.update(e.to_bytes(4, "little"))
    return int.from_bytes(h.digest(), "little")


def run_with_coverage(binary: str, data: bytes, timeout: float = 5.0) -> frozenset[int]:
    """Run `binary` with `data` on stdin; return the set of edge ids it hit."""
    bm = ShmBitmap()
    try:
        subprocess.run(
            [binary], input=data, capture_output=True, timeout=timeout,
            check=False,  # non-zero exit / crash is a normal fuzz outcome
            env=bm.env(),
        )
        return bm.edges()
    finally:
        bm.close()
