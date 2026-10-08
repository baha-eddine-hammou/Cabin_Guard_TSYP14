"""Motion branch trained on recorded motion only, and its held-out evaluation.

    python experiments/realdata/train_motion_real.py

Training windows, all real recordings:

* positives: the UEA Epilepsy (Villar et al.) seizure mimics of the official
  TRAIN split, wrist accelerometer at 16 Hz;
* negatives: the Epilepsy TRAIN walking, running and sawing series; PhysioNet
  walk-climb-drive accelerometry (hip and wrist, driving, walking, stairs,
  clapping); UCI MHEALTH everyday activities (chest), including cycling.

Every 100 Hz and 50 Hz negative also enters training band-limited to 16 Hz
(``extract_motion.py --bandlimited``), so the sampling rate cannot separate the
classes. Sample weights give the two classes equal total weight and each
negative source an equal share of it.

Evaluation, never on a window the scoring model was trained on:

* accelerometry and MHEALTH subjects: grouped 5-fold cross-validation by
  subject (the Epilepsy TRAIN split is in every fold's training set);
* Epilepsy TEST split: final model. The archive carries no participant IDs and
  six participants recorded both splits, so this split is held out by
  recording, not by person;
* UCI HAR: final model, never trained on;
* clonic jerk trains injected into held-out driving (``motion_injected.npz``):
  evaluation only, the sensitivity of a branch that never saw them.

Writes ``results/motion_real.json`` and the deployed ``models/motion_branch.joblib``.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import external_checks as ext  # noqa: E402
from cabinguard.motion_features import FEATURE_NAMES  # noqa: E402
from extract_motion import bandlimit  # noqa: E402

DER = ROOT.parent / "data" / "derived"
OUT = ROOT / "results" / "motion_real.json"
STEP_S = 0.5
PERSIST = ext.PERSIST
GAMMA = ext.GAMMA
N_FOLDS = 5
LOCATIONS = ("lh", "lw")
ACC_ACTIVITIES = ("driving", "walking", "stairs_up", "stairs_down", "clapping")


def gbdt():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=0)


def runs(flags: np.ndarray, k: int = PERSIST) -> int:
    """Distinct alarms: runs of at least ``k`` consecutive confident windows."""
    count, run = 0, 0
    for f in flags:
        run = run + 1 if f else 0
        if run == k:
            count += 1
    return count


# ------------------------------------------------------------- sources ---
def _mhealth_subject(item):
    sid, (acc, lab) = item
    raw, bl, act, seg = [], [], [], []
    edges = np.flatnonzero(np.diff(lab)) + 1
    for k, (a, b) in enumerate(zip(np.r_[0, edges], np.r_[edges, lab.size])):
        code = int(lab[a])
        if code == 0 or b - a < 2 * 50:
            continue
        x100 = ext.to_100hz(acc[a:b], 50.0)
        f, g = ext.window_features(x100), ext.window_features(bandlimit(x100))
        if len(f) == 0:
            continue
        raw.append(f)
        bl.append(g[:len(f)])
        act += [ext.MHEALTH_ACTIVITIES[code]] * len(f)
        seg += [f"{sid}/{k}"] * len(f)
    return sid, np.vstack(raw), np.vstack(bl), act, seg


def mhealth_windows() -> dict:
    cache = DER / "mhealth_windows.npz"
    if not cache.exists():
        with ProcessPoolExecutor() as pool:
            parts = list(pool.map(_mhealth_subject, ext.load_mhealth().items()))
        np.savez_compressed(cache, X=np.vstack([p[1] for p in parts]), X_bl=np.vstack([p[2] for p in parts]),
                            activity=np.concatenate([p[3] for p in parts]),
                            segment=np.concatenate([p[4] for p in parts]),
                            subject=np.concatenate([[p[0]] * len(p[3]) for p in parts]))
    d = np.load(cache)
    return {k: d[k] for k in d.files}


def epilepsy_windows() -> dict:
    out = {}
    for split, (X, y) in ext.load_epilepsy().items():
        feats = [ext.window_features(ext.to_100hz(x.T, 16.0)) for x in X]
        out[split] = {"X": np.vstack(feats),
                      "label": np.concatenate([[str(l).upper()] * len(f) for f, l in zip(feats, y)]),
                      "series": np.concatenate([[i] * len(f) for i, f in enumerate(feats)])}
    return out


def accelerometry() -> dict:
    real, bl = np.load(DER / "motion_real.npz"), np.load(DER / "motion_real_bl.npz")
    keep = np.isin(real["location"], LOCATIONS)
    return {"X": real["X"][keep], "activity": real["activity"][keep], "location": real["location"][keep],
            "subject": real["subject"][keep],
            "X_bl": bl["X"], "subject_bl": bl["subject"]}


# ------------------------------------------------------------- training ---
def training_set(acc: dict, mh: dict, epi: dict, acc_subjects=None, mh_subjects=None):
    """Features, labels and source-balanced weights; ``None`` keeps every subject."""
    def sel(subj, allowed):
        return np.ones(len(subj), bool) if allowed is None else np.isin(subj, list(allowed))
    tr = epi["TRAIN"]
    pos = tr["X"][tr["label"] == "EPILEPSY"]
    negs = [tr["X"][tr["label"] != "EPILEPSY"],
            acc["X"][sel(acc["subject"], acc_subjects)],
            acc["X_bl"][sel(acc["subject_bl"], acc_subjects)],
            mh["X"][sel(mh["subject"], mh_subjects)],
            mh["X_bl"][sel(mh["subject"], mh_subjects)]]
    negs = [n for n in negs if len(n)]
    X = np.vstack([pos] + negs)
    y = np.concatenate([np.ones(len(pos))] + [np.zeros(len(n)) for n in negs])
    w = np.concatenate([np.full(len(pos), 0.5 / len(pos))] +
                       [np.full(len(n), 0.5 / len(negs) / len(n)) for n in negs])
    return X, y, w * len(y)


def fit(X, y, w):
    return gbdt().fit(X, y, sample_weight=w)


# ----------------------------------------------------------- evaluation ---
def _rate_by_activity(p, act, groups, hours_per_window=STEP_S / 3600):
    out = {}
    for a in np.unique(act):
        m = act == a
        n = sum(runs(p[m & (groups == g)] >= GAMMA) for g in np.unique(groups[m]))
        hours = m.sum() * hours_per_window
        out[str(a)] = {"alarms": int(n), "hours": float(hours), "alarms_per_hour": float(n / hours),
                       "window_rate": float((p[m] >= GAMMA).mean())}
    return out


def injected_sensitivity(p: np.ndarray, inj: dict) -> dict:
    out = {}
    for amp in np.unique(inj["amplitude"]):
        hits, lat = 0, []
        eps = np.unique(inj["episode"][inj["amplitude"] == amp])
        for e in eps:
            sel = inj["episode"] == e
            flags = (p[sel] >= GAMMA) & (inj["t_end"][sel] >= inj["onset"] + 1.0)
            run = 0
            for t, f in zip(inj["t_end"][sel], flags):
                run = run + 1 if f else 0
                if run == PERSIST:
                    hits += 1
                    lat.append(float(t - inj["onset"]))
                    break
        out[f"{amp:g}"] = {"episodes": int(len(eps)), "sensitivity": hits / len(eps),
                           "median_latency_s": float(np.median(lat)) if lat else None}
    return out


def main() -> None:
    acc, mh, epi = accelerometry(), mhealth_windows(), epilepsy_windows()
    i = np.load(DER / "motion_injected.npz")
    im = i["location"] == "lh"
    inj = {"X": i["X"][im], "subject": i["subject"][im], "amplitude": i["amplitude"][im],
           "episode": i["episode"][im], "t_end": i["t_end"][im], "onset": float(i["onset_s"])}
    print(f"windows: accelerometry {len(acc['X'])} (+{len(acc['X_bl'])} band-limited), "
          f"MHEALTH {len(mh['X'])} (+{len(mh['X_bl'])}), Epilepsy TRAIN {len(epi['TRAIN']['X'])}, "
          f"TEST {len(epi['TEST']['X'])}", flush=True)

    groups = np.array([f"acc:{s}" for s in np.unique(acc["subject"])] + [f"mh:{s}" for s in np.unique(mh["subject"])])
    fold = {}
    for k, (_, test) in enumerate(GroupKFold(N_FOLDS).split(groups, groups=groups)):
        for g in groups[test]:
            fold[g] = k
    p_acc, p_mh, p_inj = np.zeros(len(acc["X"])), np.zeros(len(mh["X"])), np.zeros(len(inj["X"]))
    for k in range(N_FOLDS):
        held_acc = {g[4:] for g, f in fold.items() if f == k and g.startswith("acc:")}
        held_mh = {g[3:] for g, f in fold.items() if f == k and g.startswith("mh:")}
        keep_acc = set(np.unique(acc["subject"])) - held_acc
        keep_mh = set(np.unique(mh["subject"])) - held_mh
        m = fit(*training_set(acc, mh, epi, keep_acc, keep_mh))
        ta, tm, ti = np.isin(acc["subject"], list(held_acc)), np.isin(mh["subject"], list(held_mh)), \
            np.isin(inj["subject"], list(held_acc))
        p_acc[ta] = m.predict_proba(acc["X"][ta])[:, 1]
        if tm.any():
            p_mh[tm] = m.predict_proba(mh["X"][tm])[:, 1]
        if ti.any():
            p_inj[ti] = m.predict_proba(inj["X"][ti])[:, 1]
        print(f"  fold {k + 1}/{N_FOLDS}: held out {len(held_acc)} accelerometry, {len(held_mh)} MHEALTH subjects",
              flush=True)

    final = fit(*training_set(acc, mh, epi))
    res = {"scope": "trained on recorded motion only: UEA Epilepsy TRAIN seizure mimics (positives); Epilepsy "
                    "TRAIN other activities, PhysioNet walk-climb-drive (hip, wrist) and UCI MHEALTH (negatives)",
           "features": list(FEATURE_NAMES), "persistence_windows": PERSIST, "gamma": GAMMA,
           "accelerometry": {loc: _rate_by_activity(p_acc[acc["location"] == loc],
                                                    acc["activity"][acc["location"] == loc],
                                                    acc["subject"][acc["location"] == loc])
                             for loc in LOCATIONS},
           "mhealth": _rate_by_activity(p_mh, mh["activity"], mh["segment"]),
           "injected_clonic_lh": injected_sensitivity(p_inj, inj)}
    for loc in LOCATIONS:
        m = (acc["location"] == loc) & (acc["activity"] == "driving")
        res["accelerometry"][loc]["driving"]["per_subject_alarms"] = {
            str(s): runs(p_acc[m & (acc["subject"] == s)] >= GAMMA) for s in np.unique(acc["subject"][m])}

    te = epi["TEST"]
    pt = final.predict_proba(te["X"])[:, 1]
    res["epilepsy_test"] = {}
    score, truth = [], []
    for lab in np.unique(te["label"]):
        series = np.unique(te["series"][te["label"] == lab])
        fired = [runs(pt[te["series"] == s] >= GAMMA) > 0 for s in series]
        res["epilepsy_test"][str(lab)] = {"series": int(len(series)), "fired": int(sum(fired))}
        score += [float(np.median(pt[te["series"] == s])) for s in series]
        truth += [lab == "EPILEPSY"] * len(series)
    res["epilepsy_test_auc_series"] = float(roc_auc_score(truth, score))

    har = {}
    for acc_w, lab, _ in ext.load_har().values():
        F = np.array([ext.window_features(ext.to_100hz(w, 50.0))[0] for w in acc_w])
        p = final.predict_proba(F)[:, 1]
        for code in np.unique(lab):
            r = har.setdefault(ext.HAR_ACTIVITIES[int(code)], {"windows": 0, "confident": 0})
            r["windows"] += int((lab == code).sum())
            r["confident"] += int((p[lab == code] >= GAMMA).sum())
    for r in har.values():
        r["window_rate"] = r["confident"] / r["windows"]
    res["har"] = har

    OUT.write_text(json.dumps(res, indent=2))
    joblib.dump({"model": final, "features": FEATURE_NAMES, "train_prior_clonic": 0.5,   # equal class weight
                 "training": res["scope"]}, ROOT / "models" / "motion_branch.joblib")
    lh = res["accelerometry"]["lh"]
    print(f"driving (hip) alarms/h {lh['driving']['alarms_per_hour']:.2f}, "
          f"cycling alarms {res['mhealth'].get('cycling', {}).get('alarms')}, "
          f"Epilepsy TEST fired {res['epilepsy_test']['EPILEPSY']['fired']}/{res['epilepsy_test']['EPILEPSY']['series']}, "
          f"AUC {res['epilepsy_test_auc_series']:.3f}")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
