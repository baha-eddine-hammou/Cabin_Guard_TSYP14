"""Motion windows from real driving accelerometry, with and without clonic injection.

Source: PhysioNet "Labeled raw accelerometry data captured during walking,
stair climbing and driving" (32 adults, 100 Hz, wrist/hip/ankles, in g).

Two products, both in ``data/derived/``:

* ``motion_real.npz``: 2 s windows every 0.5 s for every labelled activity
  (driving, walking, stairs, clapping) at every body location. No injection.
* ``motion_injected.npz``: 30 s real driving excerpts with a clonic jerk
  train (``clonic_waveform``) added from t = 10 s; amplitude and the initial
  silent period are swept because no public recording measures clonic motion
  at a vehicle seat or headrest.

With ``--branch`` the same products are written as the deployed motion branch
sees them (``branch_windows``: each window low-passed on its own, as at
runtime), for the hip and wrist sensors (``motion_real_branch.npz``,
``motion_injected_branch.npz``). The training recordings are sampled between
16 and 100 Hz, and the common low-pass keeps the sampling rate from separating
the classes.
"""
from __future__ import annotations

import argparse
import functools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cabinguard.motion_features import branch_windows, clonic_waveform, motion_features  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "data"
SRC = DATA / "accelerometry-walk-climb-drive" / "raw_accelerometry_data"
FS = 100.0
WIN = int(2 * FS)
STEP = int(0.5 * FS)
LOCATIONS = ("lw", "lh", "la", "ra")
ACTIVITIES = {1: "walking", 2: "stairs_down", 3: "stairs_up", 4: "driving", 77: "clapping"}
AMPLITUDES_G = (0.02, 0.05, 0.1, 0.2, 0.5)
EXCERPTS_PER_SUBJECT = 12
EXCERPT_S = 30.0
ONSET_S = 10.0


def _segments(activity: np.ndarray):
    """Contiguous runs of one activity code: (code, start, stop)."""
    edges = np.flatnonzero(np.diff(activity)) + 1
    starts = np.concatenate([[0], edges])
    stops = np.concatenate([edges, [activity.size]])
    return [(int(activity[a]), a, b) for a, b in zip(starts, stops)]


def _window_feats(acc: np.ndarray, limit: bool = False):
    if limit:
        return branch_windows(acc, FS)
    return np.array([motion_features(acc[i:i + WIN], FS).vector()
                     for i in range(0, acc.shape[0] - WIN + 1, STEP)])


def subject(path: Path, seed: int, limit: bool = False):
    df = pd.read_csv(path)
    act = df["activity"].to_numpy()
    sid = path.stem
    real = []
    for code, a, b in _segments(act):
        if code not in ACTIVITIES or b - a < WIN:
            continue
        for loc in (("lh", "lw") if limit else LOCATIONS):
            acc = df[[f"{loc}_x", f"{loc}_y", f"{loc}_z"]].to_numpy()[a:b]
            f = _window_feats(acc, limit)
            real.append((f, ACTIVITIES[code], loc))
    inj = []
    rng = np.random.default_rng(seed)
    drive = [(a, b) for code, a, b in _segments(act) if code == 4 and b - a >= EXCERPT_S * FS]
    if drive:
        n = int(EXCERPT_S * FS)
        for k in range(EXCERPTS_PER_SUBJECT):
            a, b = drive[rng.integers(len(drive))]
            start = int(rng.integers(a, b - n + 1))
            sp0 = float(rng.uniform(0.05, 0.15))
            growth = float(np.log(1.0 / sp0) / 40.0)       # silent period reaches ~1 s after 40 jerks
            for loc in ("lh", "lw"):
                base = df[[f"{loc}_x", f"{loc}_y", f"{loc}_z"]].to_numpy()[start:start + n]
                for amp in AMPLITUDES_G:
                    acc = base.copy()
                    on = int(ONSET_S * FS)
                    acc[on:] += clonic_waveform(EXCERPT_S - ONSET_S, FS, amp, sp0, growth,
                                                np.random.default_rng(rng.integers(1 << 31)))
                    f = _window_feats(acc, limit)
                    t_end = (np.arange(len(f)) * STEP + WIN) / FS
                    inj.append((f, t_end, amp, sp0, loc, k))
    return sid, real, inj


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--branch", action="store_true", help="hip and wrist windows as the motion branch sees them")
    args = ap.parse_args()
    suffix = "_branch" if args.branch else ""
    files = sorted(SRC.glob("*.csv"))
    with ProcessPoolExecutor(args.workers) as pool:
        results = []
        work = functools.partial(subject, limit=args.branch)
        for i, r in enumerate(pool.map(work, files, range(len(files))), 1):
            results.append(r)
            print(f"  motion windows: subject {i}/{len(files)} {r[0]}", flush=True)
    X, act, loc, subj = [], [], [], []
    for sid, real, _ in results:
        for f, a, l in real:
            X.append(f)
            act += [a] * len(f)
            loc += [l] * len(f)
            subj += [sid] * len(f)
    out = DATA / "derived"
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / f"motion_real{suffix}.npz", X=np.concatenate(X), activity=np.array(act),
                        location=np.array(loc), subject=np.array(subj))
    IX, it, iamp, isp, iloc, isubj, iep = [], [], [], [], [], [], []
    for sid, _, inj in results:
        for f, t_end, amp, sp0, l, k in inj:
            IX.append(f)
            it.append(t_end)
            iamp += [amp] * len(f)
            isp += [sp0] * len(f)
            iloc += [l] * len(f)
            isubj += [sid] * len(f)
            iep += [f"{sid}/{l}/{k}/{amp}"] * len(f)
    np.savez_compressed(out / f"motion_injected{suffix}.npz", X=np.concatenate(IX), t_end=np.concatenate(it),
                        amplitude=np.array(iamp), sp0=np.array(isp), location=np.array(iloc),
                        subject=np.array(isubj), episode=np.array(iep), onset_s=ONSET_S)
    a = np.array(act)
    print({k: int((a == k).sum()) for k in np.unique(a)}, "injected windows:", sum(len(x) for x in IX))


if __name__ == "__main__":
    main()
