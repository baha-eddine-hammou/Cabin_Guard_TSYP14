"""End-to-end evaluation of the fused detector on composite episodes.

No public dataset records an incapacitated driver with all four CabinGuard
modalities at once, so each test episode is assembled from independent
sources, which is exactly the conditional-independence assumption the fusion
rule already makes:

* cardiac branch: real PhysioNet pulse-rhythm windows (drivedb for driving,
  vfdb/cudb/mitdb arrhythmia onsets for syncope, szdb seizures);
* motion branch: real hip accelerometry recorded while driving. Seizure
  episodes take, from onset, the neck accelerometry of a real motor seizure of
  a held-out SeizeIT2 patient; or, after a tonic phase, recorded seizure mimics
  (UEA Epilepsy TEST split) or a modelled clonic jerk train added to the
  driving signal at a swept amplitude;
* vision and posture branches: generated from documented models that include
  everyday confounders (blinks, glances down, leaning, one-handed steering).

Every model is applied out of fold: the cardiac model never saw the record
under test and the motion model never saw the accelerometry subjects under
test (the motion model is trained on recorded motion only, as in
``train_motion_real.py``). Decisions run every 0.5 s with the runtime rule: posterior >= Gamma for
2 s, with evidence from at least two physical sensors.
Writes ``results/fusion_metrics.json``.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_motion_real as tmr  # noqa: E402
from cabinguard import config  # noqa: E402
from cabinguard.fusion import CLASSES, FusionClassifier  # noqa: E402
from cabinguard.motion_features import branch_features, clonic_waveform  # noqa: E402

DATA = ROOT.parent / "data"
DER = DATA / "derived"
STEP = 0.5
PERSIST = int(config.VERIFICATION_DURATION_S / STEP)
GAMMA = config.CONFIDENCE_THRESHOLD_GAMMA
N_MOTION_FOLDS = 5
REFRACTORY_S = 60.0
AMPLITUDES_G = (0.1, 0.2, 0.5)


def logreg():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))


# ---------------------------------------------------------------- models ---
def cardiac_models(records_needed):
    d = np.load(DER / "cardiac_windows.npz")
    keep = d["y"] != "Exclude"
    X, y, rec = d["X"][keep], d["y"][keep], d["record"][keep]
    out = {}
    for r in records_needed:
        m = logreg().fit(X[rec != r], y[rec != r])
        # balanced class weights: posteriors correspond to a uniform prior
        out[r] = {"model": m, "classes": list(m.classes_),
                  "train_prior": {c: 1.0 / 3 for c in ("Normal", "Seizure", "Cardiac")}}
    return out


def motion_models(fold_of, sz_fold_of, acc, mh, epi, sz):
    """Recorded-motion models (``train_motion_real.training_set``), one per fold of driving subjects
    and SeizeIT2 patients."""
    people = ({f"acc:{s}" for s in acc["subject"]} | {f"mh:{s}" for s in mh["subject"]}
              | {f"sz:{s}" for s in sz["subject"]})
    out = {}
    for f in range(N_MOTION_FOLDS):
        held = {f"acc:{s}" for s, k in fold_of.items() if k == f} | {f"sz:{s}" for s, k in sz_fold_of.items() if k == f}
        out[f] = {"model": tmr.fit(*tmr.training_set(acc, mh, epi, sz, people - held)),
                  "train_prior_clonic": 0.5}      # equal class weight
    return out


# ------------------------------------------------------- motion streams ---
class DrivingMotion:
    """Real hip-accelerometer driving, per subject, as raw g and as features."""

    def __init__(self):
        real = np.load(DER / "motion_real_branch.npz")
        m = (real["location"] == "lh") & (real["activity"] == "driving")
        self.feats = {s: real["X"][m & (real["subject"] == s)] for s in np.unique(real["subject"][m])}
        self.subjects = sorted(self.feats)
        self._raw = {}

    def raw(self, subject: str) -> np.ndarray:
        if subject not in self._raw:
            df = pd.read_csv(DATA / "accelerometry-walk-climb-drive" / "raw_accelerometry_data" / f"{subject}.csv",
                             usecols=["activity", "lh_x", "lh_y", "lh_z"])
            self._raw[subject] = df.loc[df.activity == 4, ["lh_x", "lh_y", "lh_z"]].to_numpy()
        return self._raw[subject]

    def feature_stream(self, subjects, n: int) -> np.ndarray:
        """``n`` consecutive driving feature windows, cycling through ``subjects``."""
        parts, total, i = [], 0, 0
        while total < n:
            f = self.feats[subjects[i % len(subjects)]]
            parts.append(f)
            total += len(f)
            i += 1
        return np.vstack(parts)[:n]

    def injected_stream(self, subject: str, n: int, onset_idx: int, amp: float, rng) -> np.ndarray:
        raw = self.raw(subject)
        need = int((n * STEP + 2.0) * 100)
        start = int(rng.integers(0, max(1, raw.shape[0] - need)))
        acc = raw[start:start + need].copy()
        if acc.shape[0] < need:
            acc = np.vstack([acc, raw[: need - acc.shape[0]]])
        on = int((onset_idx * STEP + 2.0) * 100)
        sp0 = float(rng.uniform(0.05, 0.15))
        acc[on:] += clonic_waveform((need - on) / 100.0, 100.0, amp, sp0, math.log(1 / sp0) / 40, rng)
        return np.array([branch_features(acc[k * 50: k * 50 + 200], 100.0).vector() for k in range(n)])

    def clinical_stream(self, subjects, n: int, onset_idx: int, seizure: np.ndarray) -> np.ndarray:
        """Driving windows, then a recorded seizure from its onset to the end of its recording."""
        out = self.feature_stream(subjects, n).copy()
        k = min(len(seizure), n - onset_idx)
        out[onset_idx:onset_idx + k] = seizure[:k]
        return out

    def mimic_stream(self, subjects, n: int, onset_idx: int, mimics: list, rng) -> np.ndarray:
        """Driving windows, then recorded seizure-mimic series in random order from ``onset_idx``."""
        out = self.feature_stream(subjects, n).copy()
        k = onset_idx
        while k < n:
            f = mimics[rng.integers(len(mimics))]
            out[k:k + len(f)] = f[: n - k]
            k += len(f)
        return out


# ------------------------------------------------- vision/posture model ---
def modelled_channels(n: int, rng, event: str | None = None, change_idx: int | None = None):
    """EAR, pitch, PSI and grip every 0.5 s with everyday confounders.

    Rates: a blink in ~10 % of samples, a 1-3 s downward glance every ~45 s,
    a 2-8 s forward lean every ~120 s, a 1-4 s hand-off-wheel every ~60 s.
    After ``change_idx`` the channels follow the event pattern.
    """
    ear = rng.normal(0.30, 0.04, n)
    ear[rng.random(n) < 0.10] = 0.10
    pitch = rng.normal(0.0, 4.0, n)
    psi = rng.normal(0.15, 0.06, n)
    grip = np.array(["ACTIVE"] * n, dtype=object)
    for rate_s, dur, fn in ((45, (1, 3), "glance"), (120, (2, 8), "lean"), (60, (1, 4), "hand")):
        t = 0.0
        while True:
            t += rng.exponential(rate_s)
            if t >= n * STEP:
                break
            a, b = int(t / STEP), int(min(n, (t + rng.uniform(*dur)) / STEP))
            if fn == "glance":
                pitch[a:b] = rng.normal(-20, 5, b - a)
                ear[a:b] = rng.normal(0.18, 0.04, b - a)
            elif fn == "lean":
                psi[a:b] = rng.normal(0.5, 0.1, b - a)
            else:
                grip[a:b] = "DISENGAGED"
    if event is not None and change_idx is not None and change_idx < n:
        k = n - change_idx
        if event == "Syncope":
            ear[change_idx:] = np.clip(rng.normal(0.08, 0.04, k), 0, None)
            pitch[change_idx:] = rng.normal(-28, 10, k)
            psi[change_idx:] = np.clip(rng.normal(0.65, 0.2, k), 0, 1)
            grip[change_idx:] = np.where(rng.random(k) < 0.9, "DISENGAGED", "ACTIVE")
        else:
            ear[change_idx:] = np.clip(rng.normal(0.17, 0.08, k), 0, None)
            pitch[change_idx:] = rng.normal(0, 15, k)
            psi[change_idx:] = np.clip(rng.normal(0.38, 0.15, k), 0, 1)
            grip[change_idx:] = rng.choice(["CLENCHED", "ACTIVE", "DISENGAGED"], k, p=[0.7, 0.2, 0.1])
    return ear, np.clip(psi, 0, 1), pitch, grip


# ------------------------------------------------------------ decision ---
def run_episode(clf: FusionClassifier, card: np.ndarray, motion: np.ndarray, chans, require_two: bool = True,
                trace: list | None = None, smooth_s: float = 0.0):
    """Return list of (step index, class) MRM triggers, using the runtime decision rule."""
    ear, psi, pitch, grip = chans
    n = len(motion)
    ev = clf.batch_evidence(cardiac=card, motion=motion, ear=ear, pitch=pitch, psi=psi, grip=grip)
    ev = {b: causal_mean(v, int(round(smooth_s / STEP))) for b, v in ev.items()}
    post, corro = clf.combine(ev, n)
    top = post.argmax(1)
    ok = (top != 0) & (post.max(1) >= GAMMA)
    if require_two:
        ok &= corro[np.arange(n), top] >= 2
    run, cand, last_trigger, triggers = 0, None, -1e9, []
    for k in range(n):
        c = int(top[k]) if ok[k] else None
        if c is not None and c == cand:
            run += 1
        else:
            run, cand = (1, c) if c is not None else (0, None)
        if run >= PERSIST and k * STEP - last_trigger >= REFRACTORY_S:
            triggers.append((k, CLASSES[cand]))
            if trace is not None:
                trace.append({b: round(float(v[k, cand]), 2) for b, v in ev.items()})
            last_trigger = k * STEP
            run = 0
    return triggers


def causal_mean(v: np.ndarray, k: int) -> np.ndarray:
    """Mean of the last ``k`` rows at every row (fewer at the start); k <= 1 is identity."""
    if k <= 1:
        return v
    c = np.cumsum(np.vstack([np.zeros((1, v.shape[1])), v]), axis=0)
    idx = np.arange(1, len(v) + 1)
    lo = np.maximum(0, idx - k)
    return (c[idx] - c[lo]) / (idx - lo)[:, None]


def hold(card_X, card_t, t0, n):
    """Cardiac features at each 0.5 s step: latest 5 s window at or before the step."""
    times = t0 + np.arange(n) * STEP
    idx = np.searchsorted(card_t, times, side="right") - 1
    out = card_X[np.clip(idx, 0, len(card_X) - 1)].copy()
    out[idx < 0] = (0.0, 0.0, 0.0, 1.0)
    return out


# ---------------------------------------------------------- episodes ---
SMOOTH_S = 2.0
CONFIGS = {
    # name: (enabled branches, cap, require two sensors, evidence smoothing in s)
    "cardiac only (uncapped)": (("cardiac",), 50.0, False, SMOOTH_S),
    "motion only (uncapped)": (("motion",), 50.0, False, SMOOTH_S),
    "vision only (uncapped)": (("vision",), 50.0, False, SMOOTH_S),
    "posture only (uncapped)": (("posture",), 50.0, False, SMOOTH_S),
    "real branches: cardiac + motion": (("cardiac", "motion"), 3.0, True, SMOOTH_S),
    "full fusion": (("cardiac", "motion", "vision", "posture"), 3.0, True, SMOOTH_S),
    "full fusion, one sensor may decide": (("cardiac", "motion", "vision", "posture"), 3.0, False, SMOOTH_S),
    "camera lost (motion + posture)": (("motion", "posture"), 3.0, True, SMOOTH_S),
    "IMU lost (cardiac + vision + posture)": (("cardiac", "vision", "posture"), 3.0, True, SMOOTH_S),
}
# Smoothing window sweep, reported in full rather than only the chosen value.
for _w in (0.0, 2.0, 4.0, 8.0):
    CONFIGS[f"sweep: full fusion, smoothing {_w:g} s"] = (("cardiac", "motion", "vision", "posture"), 3.0, True, _w)
    CONFIGS[f"sweep: real branches, smoothing {_w:g} s"] = (("cardiac", "motion"), 3.0, True, _w)


def main() -> None:
    rng = np.random.default_rng(2026)
    d = np.load(DER / "cardiac_windows.npz")
    X, y, rec, src, t = d["X"], d["y"], d["record"], d["source"], d["t"]
    motion = DrivingMotion()
    fold_of = {s: i % N_MOTION_FOLDS for i, s in enumerate(motion.subjects)}

    episodes = []   # (kind, record, start_t, n, onset_idx or None)
    for r in np.unique(rec[src == "drivedb"]):
        m = rec == r
        episodes.append(("Normal", r, float(t[m][0]), int((t[m][-1] - t[m][0]) / STEP), None))
    for r in np.unique(rec[np.isin(src, ["vfdb", "cudb", "mitdb"])]):
        m = rec == r
        lab, tt = y[m], t[m]
        last = -1e9
        for i in range(6, len(lab)):
            # An onset: the first Cardiac window after 30 s with no Cardiac
            # window and at least 20 s of clean Normal rhythm; onsets in one
            # record at least 60 s apart.
            if (lab[i] == "Cardiac" and np.all(lab[i - 6:i] != "Cardiac")
                    and (lab[i - 6:i] == "Normal").sum() >= 4 and tt[i] - last >= 60.0):
                onset = tt[i] - 5.0
                last = tt[i]
                episodes.append(("Syncope", r, onset - 30.0, int(90.0 / STEP), int(30.0 / STEP)))
    seiz = {}
    for line in (DATA / "szdb" / "times.seize").read_text().split("\n"):
        p = line.split()
        if len(p) == 3:
            sec = [sum(int(x) * w for x, w in zip(v.split(":"), (3600, 60, 1))) for v in p[1:]]
            seiz.setdefault(p[0], []).append(sec)
    for r, evs in seiz.items():
        for on, off in evs:
            for amp in ("clinical", "mimic") + AMPLITUDES_G:
                tag = amp if isinstance(amp, str) else f"{amp:g}g"
                episodes.append((f"Seizure@{tag}", r, on - 120.0, int((off - on + 150.0) / STEP), int(120.0 / STEP)))

    needed = sorted({e[1] for e in episodes})
    print(f"{len(episodes)} episodes; training {len(needed)} cardiac folds and {N_MOTION_FOLDS} motion folds")
    cmods = cardiac_models(needed)
    acc, mh, epi, sz = tmr.accelerometry(), tmr.mhealth_windows(), tmr.epilepsy_windows(), tmr.seizeit2_windows()
    te = epi["TEST"]
    mimics = [te["X"][te["series"] == s] for s in np.unique(te["series"][te["label"] == "EPILEPSY"])]
    sz_fold_of = {s: i % N_MOTION_FOLDS for i, s in enumerate(np.unique(sz["subject"]))}
    clinical = {f: [] for f in range(N_MOTION_FOLDS)}     # motor seizures from onset, per patient fold
    for seg in np.unique(sz["segment"][np.isin(sz["group"], tmr.MOTOR)]):
        m = (sz["segment"] == seg) & (sz["t_rel"] >= 1.0)
        clinical[sz_fold_of[str(sz["subject"][m][0])]].append(sz["X"][m])
    mmods = motion_models(fold_of, sz_fold_of, acc, mh, epi, sz)

    results = {name: {"Normal": {"triggers": 0, "hours": 0.0, "by_class": {}}, "events": {}} for name in CONFIGS}
    for ei, (kind, r, t0, n, onset) in enumerate(episodes):
        m = rec == r
        card = hold(X[m], t[m], t0, n)
        f = ei % N_MOTION_FOLDS
        subj = [s for s, k in fold_of.items() if k == f]
        erng = np.random.default_rng(rng.integers(1 << 31))
        if kind == "Seizure@clinical":
            pool = clinical[f]
            mot = motion.clinical_stream(subj[erng.integers(len(subj)):] + subj, n, onset, pool[erng.integers(len(pool))])
            chans = modelled_channels(n, erng, "Seizure", onset + int(erng.uniform(0, 5) / STEP))
        elif kind == "Seizure@mimic":
            tonic = int(erng.uniform(5, 15) / STEP)
            mot = motion.mimic_stream(subj[erng.integers(len(subj)):] + subj, n, onset + tonic, mimics, erng)
            chans = modelled_channels(n, erng, "Seizure", onset + int(erng.uniform(0, 5) / STEP))
        elif kind.startswith("Seizure"):
            amp = float(kind.split("@")[1][:-1])
            tonic = int(erng.uniform(5, 15) / STEP)
            mot = motion.injected_stream(subj[erng.integers(len(subj))], n, onset + tonic, amp, erng)
            chans = modelled_channels(n, erng, "Seizure", onset + int(erng.uniform(0, 5) / STEP))
        elif kind == "Syncope":
            mot = motion.feature_stream(subj[erng.integers(len(subj)):] + subj, n)
            # loss of consciousness some seconds after the arrhythmia starts
            chans = modelled_channels(n, erng, "Syncope", onset + int(erng.uniform(6, 12) / STEP))
        else:
            mot = motion.feature_stream(subj, n)
            chans = modelled_channels(n, erng)
        for name, (enabled, cap, two, sm) in CONFIGS.items():
            clf = FusionClassifier(cmods[r], mmods[f], cap=cap, enabled=enabled)
            trig = run_episode(clf, card, mot, chans, require_two=two, smooth_s=sm)
            res = results[name]
            if kind == "Normal":
                res["Normal"]["triggers"] += len(trig)
                res["Normal"]["hours"] += n * STEP / 3600
                for _, c in trig:
                    res["Normal"]["by_class"][c] = res["Normal"]["by_class"].get(c, 0) + 1
                continue
            truth = "Seizure" if kind.startswith("Seizure") else "Syncope"
            pre = [c for k, c in trig if k < onset]
            post = [(k, c) for k, c in trig if k >= onset]
            ev = res["events"].setdefault(kind, {"n": 0, "detected": 0, "wrong_class": 0, "pre_onset_false": 0,
                                                 "latencies_s": []})
            ev["n"] += 1
            ev["pre_onset_false"] += len(pre)
            if post:
                k, c = post[0]
                if c == truth:
                    ev["detected"] += 1
                    ev["latencies_s"].append((k - onset) * STEP)
                else:
                    ev["wrong_class"] += 1
        if ei % 20 == 0:
            print(f"  episode {ei}/{len(episodes)}")

    summary = {"scope": "composite episodes: real cardiac and motion branches, modelled vision and posture; "
                        "out-of-fold models", "smoothing_s": SMOOTH_S, "persistence_s": PERSIST * STEP,
               "configs": {}}
    for name, res in results.items():
        nrm = res["Normal"]
        s = {"false_mrm_per_hour": nrm["triggers"] / nrm["hours"], "driving_hours": nrm["hours"],
             "false_by_class": nrm["by_class"], "events": {}}
        for kind, ev in sorted(res["events"].items()):
            lat = ev.pop("latencies_s")
            s["events"][kind] = {**ev, "sensitivity": ev["detected"] / ev["n"],
                                 "median_latency_s": float(np.median(lat)) if lat else None,
                                 "p90_latency_s": float(np.percentile(lat, 90)) if lat else None}
        summary["configs"][name] = s
    out = ROOT / "results" / "fusion_metrics.json"
    out.write_text(json.dumps(summary, indent=2))
    for name, s in summary["configs"].items():
        ev = {k: (round(v["sensitivity"], 2), v["median_latency_s"], v["wrong_class"]) for k, v in s["events"].items()}
        print(f"{name:40s} FA/h {s['false_mrm_per_hour']:.3f}  {ev}")


if __name__ == "__main__":
    main()
