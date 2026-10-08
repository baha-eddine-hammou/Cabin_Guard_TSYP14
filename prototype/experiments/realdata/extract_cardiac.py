"""Extract labelled 10 s pulse-rhythm windows from public PhysioNet recordings.

Sources and labels (one row per window, every 5 s):

* drivedb  (Healey & Picard): real road driving, ECG beats by XQRS -> Normal
* szdb     (Al-Aweel et al.): annotated beats, seizure intervals -> Seizure,
           windows more than 10 min from any seizure -> Normal
* vfdb, cudb, mitdb: VT, ventricular flutter, VF, asystole -> Cardiac (the
           syncope-producing arrhythmias); every other rhythm, including
           atrial fibrillation and bigeminy, -> Normal (a hard negative)

VF, flutter and asystole produce no perfusing pulse, so beats detected inside
them are removed before feature extraction (a camera sees no pulse there).
Output: ``data/derived/cardiac_windows.npz``.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import wfdb
from wfdb import processing

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cabinguard.cardiac_features import WINDOW_S, features_for_record  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "data"
STEP_S = 5.0
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ")
CARDIAC_RHYTHMS = {"(VT", "(VFL", "(VF", "(VFIB", "(ASYS"}
PULSELESS = {"(VFL", "(VF", "(VFIB", "(ASYS"}
NOISE = {"(NOISE"}


def _clean(beats: np.ndarray) -> np.ndarray:
    beats = np.sort(beats)
    keep = np.concatenate([[True], np.diff(beats) >= 0.2])
    return beats[keep]


def _rhythm_intervals(ann, fs: float, n: int) -> list[tuple[float, float, str]]:
    marks = [(s / fs, a.strip("\x00").strip()) for s, a in zip(ann.sample, ann.aux_note) if a.startswith("(")]
    out = []
    for i, (t, lab) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else n / fs
        out.append((t, end, lab))
    return out


def _overlap(a: float, b: float, intervals) -> float:
    return sum(max(0.0, min(b, e) - max(a, s)) for s, e in intervals)


def _windows(duration: float) -> np.ndarray:
    return np.arange(WINDOW_S, duration, STEP_S)


def drivedb_record(name: str):
    hdr = wfdb.rdheader(str(DATA / "drivedb" / name))
    ch = hdr.sig_name.index("ECG")
    fs = hdr.fs * hdr.samps_per_frame[ch]
    rec = wfdb.rdrecord(str(DATA / "drivedb" / name), channels=[ch], smooth_frames=False)
    sig = np.asarray(rec.e_p_signal[0], float)
    sig = np.nan_to_num(sig)
    beats = _clean(processing.xqrs_detect(sig, fs=fs, verbose=False) / fs)
    times = _windows(sig.size / fs)
    feats = features_for_record(beats, times)
    return name, "drivedb", feats, np.array(["Normal"] * len(times)), times


def szdb_record(name: str, seizures):
    ann = wfdb.rdann(str(DATA / "szdb" / name), "ari")
    hdr = wfdb.rdheader(str(DATA / "szdb" / name))
    beats = _clean(np.array([s for s, sym in zip(ann.sample, ann.symbol) if sym in BEAT_SYMBOLS]) / ann.fs)
    times = _windows(hdr.sig_len / hdr.fs)
    feats = features_for_record(beats, times)
    labels = []
    for t in times:
        a = t - WINDOW_S
        if _overlap(a, t, seizures) >= WINDOW_S / 2:
            labels.append("Seizure")
        elif all(t < s - 600 or a > e + 600 for s, e in seizures):
            labels.append("Normal")
        else:
            labels.append("Exclude")
    return name, "szdb", feats, np.array(labels), times


def arrhythmia_record(db: str, name: str):
    path = str(DATA / db / name)
    hdr = wfdb.rdheader(path)
    ann = wfdb.rdann(path, "atr")
    fs, n = hdr.fs, hdr.sig_len
    if db == "cudb":
        # VF episodes are bracketed by '[' and ']'.
        starts = [s / fs for s, sym in zip(ann.sample, ann.symbol) if sym == "["]
        ends = [s / fs for s, sym in zip(ann.sample, ann.symbol) if sym == "]"]
        rhythm = []
        for s in starts:
            e = min([x for x in ends if x > s], default=n / fs)
            rhythm.append((s, e, "(VF"))
        noise = [(s / fs - 1, s / fs + 1) for s, sym in zip(ann.sample, ann.symbol) if sym == "~"]
    else:
        rhythm = _rhythm_intervals(ann, fs, n)
        noise = [(s, e) for s, e, lab in rhythm if lab in NOISE]
    beat_ann = [s for s, sym in zip(ann.sample, ann.symbol) if sym in BEAT_SYMBOLS]
    if len(beat_ann) > 0.5 * n / fs:              # database ships beat annotations
        beats = np.array(beat_ann) / fs
    else:
        sig = wfdb.rdrecord(path, channels=[0]).p_signal[:, 0]
        beats = processing.xqrs_detect(np.nan_to_num(sig), fs=fs, verbose=False) / fs
    beats = _clean(beats)
    pulseless = [(s, e) for s, e, lab in rhythm if lab in PULSELESS]
    cardiac = [(s, e) for s, e, lab in rhythm if lab in CARDIAC_RHYTHMS]
    times = _windows(n / fs)
    feats = features_for_record(beats, times, pulseless)
    labels = []
    for t in times:
        a = t - WINDOW_S
        if _overlap(a, t, noise) > 0:
            labels.append("Exclude")
        elif _overlap(a, t, cardiac) >= WINDOW_S / 2:
            labels.append("Cardiac")
        elif _overlap(a, t, cardiac) > 0:
            labels.append("Exclude")
        else:
            labels.append("Normal")
    return f"{db}/{name}", db, feats, np.array(labels), times


def _seizure_table() -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list] = {}
    for line in (DATA / "szdb" / "times.seize").read_text().split("\n"):
        parts = line.split()
        if len(parts) == 3:
            def sec(x):
                h, m, s = map(int, x.split(":"))
                return 3600 * h + 60 * m + s
            out.setdefault(parts[0], []).append((sec(parts[1]), sec(parts[2])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DATA / "derived" / "cardiac_windows.npz")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    jobs = []
    with ProcessPoolExecutor(args.workers) as pool:
        for name in (DATA / "drivedb" / "RECORDS").read_text().split():
            jobs.append(pool.submit(drivedb_record, name))
        for name, sz in _seizure_table().items():
            jobs.append(pool.submit(szdb_record, name, sz))
        for db in ("vfdb", "cudb", "mitdb"):
            for name in (DATA / db / "RECORDS").read_text().split():
                jobs.append(pool.submit(arrhythmia_record, db, name))
        rows = []
        for i, j in enumerate(jobs, 1):
            rows.append(j.result())
            print(f"  cardiac windows: record {i}/{len(jobs)} {rows[-1][0]}", flush=True)
    X = np.concatenate([r[2] for r in rows])
    y = np.concatenate([r[3] for r in rows])
    rec = np.concatenate([[r[0]] * len(r[3]) for r in rows])
    src = np.concatenate([[r[1]] * len(r[3]) for r in rows])
    t = np.concatenate([r[4] for r in rows])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, X=X, y=y, record=rec, source=src, t=t)
    for s in np.unique(src):
        m = src == s
        print(s, {lab: int((y[m] == lab).sum()) for lab in np.unique(y[m])})


if __name__ == "__main__":
    main()
