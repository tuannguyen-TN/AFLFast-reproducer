"""Command-line entry point. [implements FR-10 / ticket AFL-008]

Example:
    python -m fuzzer.cli --target targets/bin/tlv_parser \\
        --schedule fast --seconds 600 --seed 1 --out results/run1

Every run writes `<out>/run.json` (NFR-1 provenance) before fuzzing starts. All checks that can
fail (parameters, seeds, `--out`, `--freeze-commit`) happen before anything is written under
`--out` and before the target is executed.
"""
import argparse
import dataclasses
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fuzzer import fuzzer
from fuzzer.schedule import SCHEDULES


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    """Run git in the current directory; None if git cannot be run at all."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError:
        return None


def resolve_freeze_commit(h: str) -> str:
    """Full 40-char hash of `h`, which must be an ancestor of HEAD (AFL-008; used by AFL-011)."""
    full = _git("rev-parse", f"{h}^{{commit}}")
    if full is None or full.returncode != 0:
        head = _git("rev-parse", "HEAD")
        at = head.stdout.strip() if head and head.returncode == 0 else "unknown"
        raise ValueError(f"freeze commit {h!r} does not resolve to a commit (HEAD is {at})")
    sha = full.stdout.strip()
    anc = _git("merge-base", "--is-ancestor", sha, "HEAD")
    if anc is None or anc.returncode != 0:
        raise ValueError(f"freeze commit {h!r} ({sha}) is not an ancestor of HEAD")
    return sha


def _provenance() -> tuple[str, bool | None]:
    """(commit, dirty): `unknown`/None when git cannot tell; None never means clean."""
    head = _git("rev-parse", "HEAD")
    commit = head.stdout.strip() if head and head.returncode == 0 else "unknown"
    st = _git("status", "--porcelain", "--untracked-files=no")
    dirty = bool(st.stdout.strip()) if st and st.returncode == 0 else None
    return commit, dirty


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fuzzer.cli", description="Run one fuzzing session.")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--schedule", required=True, choices=sorted(SCHEDULES))
    p.add_argument("--seconds", required=True, type=float, help="time budget")
    p.add_argument("--seed", required=True, type=int, help="the run's only RNG seed")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--seeds", type=Path, help="initial corpus dir (default targets/seeds/<target>/)")
    p.add_argument("--max-execs", type=int, default=None)
    p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--freeze-commit", default=None, metavar="HASH")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    a = _parser().parse_args(argv)
    seeds_dir = a.seeds if a.seeds is not None else Path("targets/seeds") / a.target.name
    cfg = fuzzer.FuzzConfig(a.target, a.schedule, a.seconds, a.seed, a.out, seeds_dir,
                            a.max_execs, a.timeout)
    try:
        fuzzer.validate_config(cfg)
        if not (a.target.is_file() and os.access(a.target, os.X_OK)):
            raise ValueError(f"target {a.target} does not exist or is not executable")
        files = fuzzer.seed_files(seeds_dir) if seeds_dir.is_dir() else []
        if not files:
            raise ValueError(f"seeds directory {seeds_dir} is missing or has no seed files")
        if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
            raise ValueError(f"--out {a.out} exists and is not empty")
        freeze = resolve_freeze_commit(a.freeze_commit) if a.freeze_commit is not None else None
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    commit, dirty = _provenance()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "run.json").write_text(json.dumps({
        "argv": argv,
        "config": dataclasses.asdict(cfg),
        "commit": commit,
        "dirty": dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "started_at": datetime.now(timezone.utc).isoformat(),  # provenance only, no duration
        "seed_files": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in files],
        "freeze_commit": freeze,
    }, indent=2, default=str))
    fuzzer.run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
