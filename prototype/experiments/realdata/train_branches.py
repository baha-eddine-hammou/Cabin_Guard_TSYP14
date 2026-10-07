"""Train and evaluate the cardiac and motion branch models on real data.

Cardiac branch: 3 classes (Normal / Seizure / Cardiac) from pulse-rhythm
features, evaluated with leave-one-record-out cross-validation (every record
is a different patient or driver, except szdb, whose 7 records come from 5
patients without a published mapping).

Motion branch: clonic vs non-clonic from inertial features. Negatives are
real windows (driving, walking, stairs, clapping); positives are real driving
windows with injected clonic motion. Leave-one-subject-out. The headline
false-alarm figure is computed on real driving only, with the same 2 s
persistence the runtime watchdog applies.

Writes ``results/branch_metrics.json`` and the deployable models to
``models/cardiac_branch.joblib`` and ``models/motion_branch.joblib``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from cabinguard.cardiac_features import FEATURE_NAMES as CARDIAC_FEATURES  # noqa: E402
from cabinguard.motion_features import FEATURE_NAMES as MOTION_FEATURES  # noqa: E402

DATA = ROOT.parent / "data" / "derived"
CLASSES = ["Normal", "Seizure", "Cardiac"]
GAMMA = 0.85
STEP_CARDIAC_S = 5.0
STEP_MOTION_S = 0.5
PERSIST_MOTION = int(2.0 / STEP_MOTION_S)
MIN_TRAIN_AMPLITUDE_G = 0.1
DEPLOYED_CARDIAC = "LogReg"
DEPLOYED_MOTION = "GBDT"


def models():
    return {
        "GaussianNB": lambda: make_pipeline(StandardScaler(), GaussianNB()),
        "LogReg": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
        "GBDT": lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, class_weight="balanced",
                                                       random_state=0),
    }


def _runs(flags: np.ndarray, k: int) -> int:
    """Number of distinct alarms: runs of >= k consecutive True values."""
    count, run = 0, 0
    for f in flags:
        run = run + 1 if f else 0
        if run == k:
            count += 1
    return count


def cardiac(results: dict) -> None:
    d = np.load(DATA / "cardiac_windows.npz")
    keep = d["y"] != "Exclude"
    X, y, rec, src = d["X"][keep], d["y"][keep], d["record"][keep], d["source"][keep]
    out = {"n_windows": {c: int((y == c).sum()) for c in CLASSES},
           "n_records": int(np.unique(rec).size),
           "drive_hours": float((src == "drivedb").sum() * STEP_CARDIAC_S / 3600), "models": {}}
    for name, make in models().items():
        proba = np.zeros((len(y), len(CLASSES)))
        for r in np.unique(rec):
            test = rec == r
            train = ~test
            if np.unique(y[train]).size < len(CLASSES):
                continue
            m = make().fit(X[train], y[train])
            p = m.predict_proba(X[test])
            proba[np.ix_(test, [CLASSES.index(c) for c in m.classes_])] = p
        pred = np.array(CLASSES)[proba.argmax(1)]
        confident = proba.max(1) >= GAMMA
        alarm = (pred != "Normal") & confident
        cm = confusion_matrix(y, pred, labels=CLASSES)
        drive = src == "drivedb"
        n_alarms = sum(_runs(alarm[(rec == r)], 2) for r in np.unique(rec[drive]))
        entry = {
            "confusion": cm.tolist(),
            "recall": {c: float(cm[i, i] / cm[i].sum()) for i, c in enumerate(CLASSES)},
            "auc_ovr": {c: float(roc_auc_score(y == c, proba[:, i])) for i, c in enumerate(CLASSES)},
            "window_alarm_rate_drive": float(alarm[drive].mean()),
            "drive_false_alarms_per_hour": float(n_alarms / out["drive_hours"]),
            "recall_at_gamma": {c: float(((pred == c) & confident)[y == c].mean()) for c in CLASSES[1:]},
        }
        # Per-seizure detection: any confident Seizure window inside the event.
        sz = (src == "szdb") & (y == "Seizure")
        events = {}
        for r, t in zip(rec[sz], d["t"][keep][sz]):
            events.setdefault(r, []).append(t)
        entry["per_record_seizure_hit"] = {
            r: bool(((pred == "Seizure") & confident & (rec == r) & (y == "Seizure")).any()) for r in events}
        out["models"][name] = entry
    results["cardiac"] = out
    # Deployed model: best leave-one-record-out AUC (logistic regression).
    # Balanced class weights make its posteriors correspond to equal priors,
    # so the prior divided out to obtain likelihood ratios is uniform.
    final = models()[DEPLOYED_CARDIAC]().fit(X, y)
    joblib.dump({"model": final, "features": CARDIAC_FEATURES, "classes": list(final.classes_),
                 "train_prior": {c: 1.0 / len(CLASSES) for c in CLASSES}},
                ROOT / "models" / "cardiac_branch.joblib")


def motion(results: dict) -> None:
    real = np.load(DATA / "motion_real.npz")
    inj = np.load(DATA / "motion_injected.npz")
    onset = float(inj["onset_s"])
    out = {"locations": {}}
    for loc in ("lh", "lw"):
        rm = real["location"] == loc
        Xr, act, sr = real["X"][rm], real["activity"][rm], real["subject"][rm]
        im = inj["location"] == loc
        post = inj["t_end"] >= onset + 1.0         # window mostly after onset
        trainable = inj["amplitude"] >= MIN_TRAIN_AMPLITUDE_G
        Xi, si, ai, ep = inj["X"][im & post], inj["subject"][im & post], inj["amplitude"][im & post], inj["episode"][im & post]
        X = np.vstack([Xr, Xi])
        y = np.concatenate([np.zeros(len(Xr)), np.ones(len(Xi))])
        groups = np.concatenate([sr, si])
        # Weak injections are scored but never used as positives in training:
        # below ~0.1 g the jerks sink into road vibration and only teach the
        # model to flag ordinary driving.
        fit_mask = np.concatenate([np.ones(len(Xr), bool), trainable[im & post]])
        loc_out = {"driving_hours": float((act == "driving").sum() * STEP_MOTION_S / 3600), "models": {}}
        for name, make in list(models().items()):
            p = np.zeros(len(y))
            for g in np.unique(groups):
                test = groups == g
                tr = ~test & fit_mask
                if not (y[tr] == 1).any():
                    continue
                m = make().fit(X[tr], y[tr])
                p[test] = m.predict_proba(X[test])[:, list(m.classes_).index(1.0)]
            pr, pi = p[: len(Xr)], p[len(Xr):]
            alarm = pr >= GAMMA
            fa = {}
            for a in ("driving", "walking", "stairs_up", "stairs_down", "clapping"):
                mask = act == a
                hours = mask.sum() * STEP_MOTION_S / 3600
                n = sum(_runs(alarm[mask & (sr == s)], PERSIST_MOTION) for s in np.unique(sr[mask]))
                fa[a] = {"false_alarms_per_hour": float(n / hours) if hours else None,
                         "window_rate": float(alarm[mask].mean()), "hours": float(hours)}
            sens = {}
            for amp in np.unique(ai):
                eps = np.unique(ep[ai == amp])
                hits, lat = 0, []
                for e in eps:
                    sel = ep == e
                    flags = pi[sel] >= GAMMA
                    run = 0
                    for k, f in enumerate(flags):
                        run = run + 1 if f else 0
                        if run == PERSIST_MOTION:
                            hits += 1
                            # first post-onset window ends at onset+1 s; each step adds 0.5 s
                            lat.append(1.0 + k * STEP_MOTION_S)
                            break
                sens[f"{amp:g}"] = {"episode_sensitivity": hits / len(eps),
                                    "median_latency_s": float(np.median(lat)) if lat else None,
                                    "episodes": int(len(eps))}
            loc_out["models"][name] = {
                "auc_drive_vs_clonic": float(roc_auc_score(
                    np.concatenate([np.zeros((act == "driving").sum()), np.ones(len(pi))]),
                    np.concatenate([pr[act == "driving"], pi]))),
                "false_alarms": fa, "sensitivity_by_amplitude_g": sens}
        # Baseline: the Phase 1 fixed rule SER > 0.65 alone, same persistence.
        ser_alarm = Xr[:, 0] > 0.65
        loc_out["baseline_ser_rule"] = {
            a: float(sum(_runs(ser_alarm[(act == a) & (sr == s)], PERSIST_MOTION) for s in np.unique(sr[act == a]))
                     / max(1e-9, (act == a).sum() * STEP_MOTION_S / 3600))
            for a in ("driving", "walking", "stairs_up", "stairs_down", "clapping")}
        loc_out["baseline_ser_rule_sensitivity"] = {
            f"{amp:g}": float(np.mean([_runs(Xi[ep == e][:, 0] > 0.65, PERSIST_MOTION) > 0
                                       for e in np.unique(ep[ai == amp])])) for amp in np.unique(ai)}
        out["locations"][loc] = loc_out
        if loc == "lh":
            final = models()[DEPLOYED_MOTION]().fit(X[fit_mask], y[fit_mask])
            joblib.dump({"model": final, "features": MOTION_FEATURES, "train_prior_clonic": 0.5},  # balanced weights
                        ROOT / "models" / "motion_branch.joblib")
    results["motion"] = out


def main() -> None:
    results: dict = {"scope": "public PhysioNet recordings; motion positives are real driving windows with "
                              "injected clonic motion (Conradsen et al. 2013 discharge model)"}
    which = sys.argv[1:] or ["cardiac", "motion"]
    path = ROOT / "results" / "branch_metrics.json"
    if path.exists():
        results.update(json.loads(path.read_text()))
    if "cardiac" in which:
        cardiac(results)
    if "motion" in which:
        motion(results)
    path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=1)[:6000])


if __name__ == "__main__":
    main()
