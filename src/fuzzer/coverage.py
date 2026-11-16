"""Edge-coverage collection from an instrumented target. [implements FR-1 / ticket AFL-002]

Mechanism (ADR-0001): the target's C runtime (targets/cov_rt.c) marks hit
trace-pc-guard ids in a POSIX shared-memory bitmap named by env FUZZ_SHM_NAME.
Each guard has a saturating 8-bit hit counter (AFL-034), bucketed AFL's way into
(edge, bucket) pairs: retention and path_id use pairs, the `edges` endpoint (ADR-0005 s6)
stays distinct edge ids. Coverage never steers mutation (CLAUDE.md s2); consumers treat
edge ints as opaque and use has_new_edges / path_id only.
"""
import hashlib
import subprocess
from multiprocessing import shared_memory
from typing import TypeVar

import numpy as np

MAP_SIZE = 1 << 16
T = TypeVar("T")
Hit = tuple[int, int]  # (edge id, bucket); bucket is AFL's bit value, see BUCKET_LUT

# count -> bucket: 0 = not hit; 1, 2, 3, 4-7, 8-15, 16-31, 32-127, 128+ -> 1,2,4,8,16,32,64,128
BUCKET_LUT = np.zeros(256, dtype=np.uint8)
for _lo, _b in ((1, 1), (2, 2), (3, 4), (4, 8), (8, 16), (16, 32), (32, 64), (128, 128)):
    BUCKET_LUT[_lo:] = _b


class ShmBitmap:
    """Shared-memory edge bitmap; the executor (AFL-003) owns and drives it."""

    def __init__(self, size: int = MAP_SIZE) -> None:
        self._shm = shared_memory.SharedMemory(create=True, size=size)
        assert self._shm.buf is not None  # always set for a live segment
        self._map = np.frombuffer(self._shm.buf, dtype=np.uint8)
        self._closed = False

    def env(self) -> dict[str, str]:
        """Environment that tells the target runtime where the bitmap lives."""
        return {"FUZZ_SHM_NAME": self._shm.name}

    def reset(self) -> None:
        self._map[:] = 0

    def hits(self) -> frozenset[Hit]:
        """(edge id, bucket) pairs since the last reset; count 0 yields no pair."""
        idx = np.flatnonzero(self._map)
        return frozenset(zip(idx.tolist(), BUCKET_LUT[self._map[idx]].tolist(), strict=True))

    def close(self) -> None:
        """Release and unlink the segment. Idempotent; unlinks even if close() raises."""
        if self._closed:
            return
        self._closed = True
        del self._map  # exported buffer must be dropped before close()
        try:
            self._shm.close()
        finally:
            self._shm.unlink()


def has_new_edges(edges: frozenset[T], seen: set[T]) -> bool:
    """True if `edges` has an element (an edge id or an (edge, bucket) hit) not in `seen`. Pure; the caller updates `seen`."""
    return not edges <= seen


def path_id(hits: frozenset[Hit]) -> int:
    """Stable 64-bit identity of an (edge, bucket) set (the only one; FAST's f(i), AFL-006/034)."""
    h = hashlib.blake2b(digest_size=8)
    for e, b in sorted(hits):
        h.update(e.to_bytes(4, "little") + bytes([b]))
    return int.from_bytes(h.digest(), "little")


def run_with_coverage(binary: str, data: bytes, timeout: float = 5.0) -> frozenset[Hit]:
    """Run `binary` with `data` on stdin; return its (edge id, bucket) pairs."""
    bm = ShmBitmap()
    try:
        subprocess.run(
            [binary], input=data, capture_output=True, timeout=timeout,
            check=False,  # non-zero exit / crash is a normal fuzz outcome
            env=bm.env(),
        )
        return bm.hits()
    finally:
        bm.close()
