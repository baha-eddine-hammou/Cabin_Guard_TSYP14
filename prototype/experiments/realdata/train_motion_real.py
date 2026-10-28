"""Motion branch trained on recorded motion only, and its held-out evaluation.

    python experiments/realdata/train_motion_real.py

Every window, from every source, goes through ``branch_windows`` (2 s windows
every 0.5 s at 100 Hz, each low-passed on its own exactly as at runtime).

Training windows, all real recordings:

* positives: motor seizures recorded in epilepsy monitoring units with a neck
  accelerometer (SeizeIT2, OpenNeuro ds005873, ``extract_seizeit2.py``):
  focal-to-bilateral tonic-clonic, hyperkinetic, tonic, clonic and myoclonic, inside
  the annotated onset and offset where the motion exceeds twice the RMS of
  the same seizure's pre-ictal minute and the median motion of the training
  drivers' hip sensor (motion weaker than road vibration cannot be told apart
  at a seat; those ictal windows are not trained on);
  and the seizure mimics of healthy volunteers (UEA Epilepsy, Villar et al., TRAIN split, wrist);
* negatives: SeizeIT2 background more than 10 min from any seizure and the
  minute before each seizure; the Epilepsy TRAIN walking, running and sawing;
  PhysioNet walk-climb-drive (hip, wrist: driving, walking, stairs, clapping);
  UCI MHEALTH everyday activities (chest).

Seizures with automatisms only, non-motor and unclassified seizures are not
trained on; they are scored, by type. Sample weights give the two classes
equal total weight, the two positive sources equal shares, and each negative
source an equal share.

Evaluation, never on a window the scoring model was trained on:

* SeizeIT2 patients, accelerometry and MHEALTH subjects: grouped 5-fold
  cross-validation by person (the Epilepsy TRAIN split is in every fold);
* Epilepsy TEST split: final model. The archive carries no participant IDs and
  its six volunteers recorded both splits, so it is held out by recording only;
* UCI HAR: final model, never trained on;
* clonic jerk trains added to held-out driving (``motion_injected_branch.npz``):
  test only.

The cross-validation is repeated without MHEALTH to show what the everyday
activities contribute. Writes ``results/motion_real.json`` and the deployed
``models/motion_branch.joblib`` (trained with every source).
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
from cabinguard.motion_features import FEATURE_NAMES, branch_windows  # noqa: E402

DER = ROOT.parent / "data" / "derived"
OUT = ROOT / "results" / "motion_real.json"
FS = 100.0
STEP_S = 0.5
PERSIST = ext.PERSIST
GAMMA = ext.GAMMA
N_FOLDS = 5
LOCATIONS = ("lh", "lw")
PREICTAL_S = 10.0           # windows ending this long before onset are negatives
ACTIVE_RATIO = 2.0          # ictal windows train as positives only above this multiple of pre-ictal RMS


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


def first_alarm(flags: np.ndarray, k: int = PERSIST) -> int | None:
    run = 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        if run == k:
            return i
    return None


def seizure_group(event: str) -> str:
    """SeizeIT2 event type -> the group it is scored and trained under."""
    if event == "bckg":
        return "background"
    if "f2b" in event:
        return "convulsive"
    if "hyperkinetic" in event:
        return "hyperkinetic"
    if any(m in event for m in ("_m_tonic", "clonic", "tonicMyo")) or event.endswith("_m"):
        return "tonic or clonic"
    if "automatisms" in event:
        return "automatisms"
    if "_nm" in event:
        return "non-motor"
    return "unclassified"


MOTOR = ("convulsive", "hyperkinetic", "tonic or clonic")


# ------------------------------------------------------------- sources ---
def _to100(x: np.ndarray, fs: float) -> np.ndarray:
    return x if fs == FS else ext.to_100hz(x, fs)


def _mhealth_subject(item):
    sid, (acc, lab) = item
    X, act, seg = [], [], []
    edges = np.flatnonzero(np.diff(lab)) + 1
    for k, (a, b) in enumerate(zip(np.r_[0, edges], np.r_[edges, lab.size])):
        code = int(lab[a])
        if code == 0 or b - a < 2 * 50:
            continue
        f = branch_windows(_to100(acc[a:b], 50.0), FS)
        if len(f):
            X.append(f)
            act += [ext.MHEALTH_ACTIVITIES[code]] * len(f)
            seg += [f"{sid}/{k}"] * len(f)
    return sid, np.vstack(X), act, seg


def mhealth_windows() -> dict:
    cache = DER / "mhealth_branch.npz"
    if not cache.exists():
        with ProcessPoolExecutor() as pool:
            parts = list(pool.map(_mhealth_subject, ext.load_mhealth().items()))
        np.savez_compressed(cache, X=np.vstack([p[1] for p in parts]),
                            activity=np.concatenate([p[2] for p in parts]),
                            segment=np.concatenate([p[3] for p in parts]),
                            subject=np.concatenate([[p[0]] * len(p[2]) for p in parts]))
    d = np.load(cache)
    return {k: d[k] for k in d.files}


def _epilepsy_series(x):
    return branch_windows(_to100(x.T, 16.0), FS)


def epilepsy_windows() -> dict:
    cache = DER / "epilepsy_branch.npz"
    if not cache.exists():
        arrays = {}
        for split, (X, y) in ext.load_epilepsy().items():
            with ProcessPoolExecutor() as pool:
                feats = list(pool.map(_epilepsy_series, X))
            arrays[f"{split}_X"] = np.vstack(feats)
            arrays[f"{split}_label"] = np.concatenate([[str(l).upper()] * len(f) for f, l in zip(feats, y)])
            arrays[f"{split}_series"] = np.concatenate([[i] * len(f) for i, f in enumerate(feats)])
        np.savez_compressed(cache, **arrays)
    d = np.load(cache)
    return {s: {"X": d[f"{s}_X"], "label": d[f"{s}_label"], "series": d[f"{s}_series"]} for s in ("TRAIN", "TEST")}


def _seizeit2_segment(args):
    x, fs = args
    return branch_windows(_to100(x.astype(float), fs), FS)


def seizeit2_windows() -> dict:
    cache = DER / "seizeit2_branch.npz"
    if not cache.exists():
        d = np.load(DER / "seizeit2_segments.npz")
        x = d["x"]                                    # decompress once, not once per segment
        segs = [(x[a:a + n], f) for a, n, f in zip(d["start"], d["length"], d["fs"])]
        with ProcessPoolExecutor() as pool:
            feats = list(pool.map(_seizeit2_segment, segs, chunksize=16))
        X, t_rel, inside, group, subj, seg = [], [], [], [], [], []
        for i, F in enumerate(feats):
            if len(F) == 0:
                continue
            t_end = (np.arange(len(F)) * STEP_S * FS + 2 * FS) / FS
            onset, dur = float(d["onset"][i]), float(d["duration"][i])
            X.append(F)
            t_rel.append(t_end - onset if np.isfinite(onset) else np.full(len(F), np.nan))
            inside.append((t_end - 1.0 >= onset) & (t_end - 1.0 <= onset + dur) if np.isfinite(onset)
                          else np.zeros(len(F), bool))
            group += [seizure_group(str(d["type"][i]))] * len(F)
            subj += [str(d["subject"][i])] * len(F)
            seg += [i] * len(F)
        np.savez_compressed(cache, X=np.vstack(X), t_rel=np.concatenate(t_rel), inside=np.concatenate(inside),
                            group=np.array(group), subject=np.array(subj), segment=np.array(seg))
    d = np.load(cache)
    return {k: d[k] for k in d.files}


def accelerometry() -> dict:
    d = np.load(DER / "motion_real_branch.npz")
    return {k: d[k] for k in d.files}


def injected() -> dict:
    i = np.load(DER / "motion_injected_branch.npz")
    m = i["location"] == "lh"
    return {"X": i["X"][m], "subject": i["subject"][m], "amplitude": i["amplitude"][m],
            "episode": i["episode"][m], "t_end": i["t_end"][m], "onset": float(i["onset_s"])}


# ------------------------------------------------------------- training ---
def active(sz: dict, floor_g: float = 0.0) -> np.ndarray:
    """Ictal windows whose 2-6 Hz or total RMS exceeds ``ACTIVE_RATIO`` times the median of the same
    seizure's pre-ictal windows, and whose total RMS exceeds ``floor_g``. The annotation spans the
    whole seizure, including phases too still to show; those windows are left out of training,
    not labelled negative."""
    out = np.zeros(len(sz["X"]), bool)
    lim = np.log10(ACTIVE_RATIO)
    for seg in np.unique(sz["segment"][sz["inside"]]):
        m = sz["segment"] == seg
        pre = m & (sz["t_rel"] < -PREICTAL_S)
        if not pre.any():
            continue
        base = np.median(sz["X"][pre][:, [1, 3]], axis=0)       # log band RMS, log total RMS
        out[m] = sz["inside"][m] & np.any(sz["X"][m][:, [1, 3]] > base + lim, axis=1)
    return out & (sz["X"][:, 3] > np.log10(floor_g + 1e-4)) if floor_g > 0 else out


def driving_floor_g(acc: dict, keep=None) -> float:
    """Median total RMS of hip driving windows of the training drivers: motion below it cannot be
    told apart from road vibration at a seat, so seizure windows below it are not trained on."""
    if "activity" not in acc:
        return 0.0
    m = (acc["activity"] == "driving") & (acc["location"] == "lh")
    if keep is not None:
        m &= np.isin(np.char.add("acc:", acc["subject"].astype(str)), list(keep))
    return float(np.median(10 ** acc["X"][m, 3] - 1e-4)) if m.any() else 0.0


def sz_roles(sz: dict, floor_g: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Masks of SeizeIT2 training positives (moving motor ictal) and negatives (background, pre-ictal)."""
    pos = np.isin(sz["group"], MOTOR) & active(sz, floor_g)
    neg = (sz["group"] == "background") | (sz["t_rel"] < -PREICTAL_S)
    return pos, neg


def training_set(acc: dict, mh: dict | None, epi: dict, sz: dict, keep=None):
    """Features, labels and source-balanced weights. ``keep``: allowed person ids (``None``: all)."""
    def sel(ids):
        return np.ones(len(ids), bool) if keep is None else np.isin(ids, list(keep))
    tr = epi["TRAIN"]
    sz_pos, sz_neg = sz_roles(sz, driving_floor_g(acc, keep))
    s = sel(np.char.add("sz:", sz["subject"].astype(str)))
    pos = [p for p in (sz["X"][sz_pos & s], tr["X"][tr["label"] == "EPILEPSY"]) if len(p)]
    negs = [tr["X"][tr["label"] != "EPILEPSY"],
            acc["X"][sel(np.char.add("acc:", acc["subject"].astype(str)))],
            sz["X"][sz_neg & s]]
    if mh is not None:
        negs.append(mh["X"][sel(np.char.add("mh:", mh["subject"].astype(str)))])
    negs = [n for n in negs if len(n)]
    X = np.vstack(pos + negs)
    y = np.concatenate([np.ones(len(p)) for p in pos] + [np.zeros(len(n)) for n in negs])
    w = np.concatenate([np.full(len(p), 0.5 / len(pos) / len(p)) for p in pos] +
                       [np.full(len(n), 0.5 / len(negs) / len(n)) for n in negs])
    return X, y, w * len(y)


def fit(X, y, w):
    return gbdt().fit(X, y, sample_weight=w)


def folds(acc: dict, mh: dict, sz: dict) -> dict[str, int]:
    people = np.array(sorted({f"acc:{s}" for s in acc["subject"]} | {f"mh:{s}" for s in mh["subject"]}
                             | {f"sz:{s}" for s in sz["subject"]}))
    out = {}
    for k, (_, test) in enumerate(GroupKFold(N_FOLDS).split(people, groups=people)):
        out.update({p: k for p in people[test]})
    return out


# ----------------------------------------------------------- evaluation ---
def _rate_by_activity(p, act, groups):
    out = {}
    for a in np.unique(act):
        m = act == a
        n = sum(runs(p[m & (groups == g)] >= GAMMA) for g in np.unique(groups[m]))
        hours = m.sum() * STEP_S / 3600
        out[str(a)] = {"alarms": int(n), "hours": float(hours), "alarms_per_hour": float(n / hours),
                       "window_rate": float((p[m] >= GAMMA).mean())}
    return out


def seizeit2_scores(p: np.ndarray, sz: dict) -> dict:
    out = {}
    for g in np.unique(sz["group"]):
        if g == "background":
            m = sz["group"] == g
            n = sum(runs(p[sz["segment"] == s] >= GAMMA) for s in np.unique(sz["segment"][m]))
            hours = m.sum() * STEP_S / 3600
            out[g] = {"alarms": int(n), "hours": float(hours), "alarms_per_hour": float(n / hours),
                      "patients": int(np.unique(sz["subject"][m]).size)}
            continue
        hits, lat, pre, n = 0, [], 0, 0
        for s in np.unique(sz["segment"][sz["group"] == g]):
            m = sz["segment"] == s
            t, ins = sz["t_rel"][m], sz["inside"][m]
            flags = p[m] >= GAMMA
            n += 1
            pre += int(runs(flags[t < 0]) > 0)
            i = first_alarm(np.where(ins, flags, False))
            if i is not None:
                hits += 1
                lat.append(float(t[i]))
        out[g] = {"seizures": n, "detected": hits, "sensitivity": hits / n if n else None,
                  "median_latency_s": float(np.median(lat)) if lat else None,
                  "alarm_in_minute_before": pre,
                  "patients": int(np.unique(sz["subject"][sz["group"] == g]).size)}
    return out


def injected_sensitivity(p: np.ndarray, inj: dict) -> dict:
    out = {}
    for amp in np.unique(inj["amplitude"]):
        hits, lat = 0, []
        eps = np.unique(inj["episode"][inj["amplitude"] == amp])
        for e in eps:
            sel = inj["episode"] == e
            i = first_alarm((p[sel] >= GAMMA) & (inj["t_end"][sel] >= inj["onset"] + 1.0))
            if i is not None:
                hits += 1
                lat.append(float(inj["t_end"][sel][i] - inj["onset"]))
        out[f"{amp:g}"] = {"episodes": int(len(eps)), "sensitivity": hits / len(eps),
                           "median_latency_s": float(np.median(lat)) if lat else None}
    return out


def cross_validate(acc, mh, epi, sz, inj, fold, use_mhealth=True) -> dict:
    p_acc, p_mh, p_sz, p_inj = (np.zeros(len(d["X"])) for d in (acc, mh, sz, inj))
    ids = {"acc": np.char.add("acc:", acc["subject"].astype(str)),
           "mh": np.char.add("mh:", mh["subject"].astype(str)),
           "sz": np.char.add("sz:", sz["subject"].astype(str)),
           "inj": np.char.add("acc:", inj["subject"].astype(str))}
    for k in range(N_FOLDS):
        held = {p for p, f in fold.items() if f == k}
        m = fit(*training_set(acc, mh if use_mhealth else None, epi, sz, set(fold) - held))
        for p, d, key in ((p_acc, acc, "acc"), (p_mh, mh, "mh"), (p_sz, sz, "sz"), (p_inj, inj, "inj")):
            t = np.isin(ids[key], list(held))
            if t.any():
                p[t] = m.predict_proba(d["X"][t])[:, 1]
        print(f"  {'with' if use_mhealth else 'without'} MHEALTH, fold {k + 1}/{N_FOLDS}", flush=True)
    res = {"accelerometry": {loc: _rate_by_activity(p_acc[acc["location"] == loc],
                                                    acc["activity"][acc["location"] == loc],
                                                    acc["subject"][acc["location"] == loc])
                             for loc in LOCATIONS},
           "mhealth": _rate_by_activity(p_mh, mh["activity"], mh["segment"]),
           "seizeit2": seizeit2_scores(p_sz, sz),
           "injected_clonic_lh": injected_sensitivity(p_inj, inj)}
    return res


def main() -> None:
    acc, mh, epi, sz, inj = accelerometry(), mhealth_windows(), epilepsy_windows(), seizeit2_windows(), injected()
    pos, neg = sz_roles(sz, driving_floor_g(acc))
    print(f"windows: accelerometry {len(acc['X'])}, MHEALTH {len(mh['X'])}, Epilepsy TRAIN "
          f"{len(epi['TRAIN']['X'])}, SeizeIT2 {len(sz['X'])} ({int(pos.sum())} motor ictal, {int(neg.sum())} "
          f"background), {np.unique(sz['subject']).size} patients", flush=True)
    fold = folds(acc, mh, sz)
    res = {"scope": "trained on recorded motion only: SeizeIT2 motor seizures (neck accelerometer, patients) and "
                    "UEA Epilepsy seizure mimics (wrist, volunteers) against SeizeIT2 background, Epilepsy other "
                    "activities, PhysioNet walk-climb-drive and UCI MHEALTH; every window low-passed as at runtime",
           "features": list(FEATURE_NAMES), "persistence_windows": PERSIST, "gamma": GAMMA,
           "cross_validation": cross_validate(acc, mh, epi, sz, inj, fold, True),
           "cross_validation_without_mhealth": cross_validate(acc, mh, epi, sz, inj, fold, False)}

    final = fit(*training_set(acc, mh, epi, sz))
    te = epi["TEST"]
    pt = final.predict_proba(te["X"])[:, 1]
    res["epilepsy_test"], score, truth = {}, [], []
    for lab in np.unique(te["label"]):
        series = np.unique(te["series"][te["label"] == lab])
        fired = [runs(pt[te["series"] == s] >= GAMMA) > 0 for s in series]
        res["epilepsy_test"][str(lab)] = {"series": int(len(series)), "fired": int(sum(fired))}
        score += [float(np.median(pt[te["series"] == s])) for s in series]
        truth += [lab == "EPILEPSY"] * len(series)
    res["epilepsy_test_auc_series"] = float(roc_auc_score(truth, score))
    har = {}
    for acc_w, lab, _ in ext.load_har().values():
        F = np.vstack([branch_windows(_to100(w, 50.0), FS)[:1] for w in acc_w])
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
                 "training": res["scope"], "input": "branch_features"}, ROOT / "models" / "motion_branch.joblib")
    cv = res["cross_validation"]
    print("SeizeIT2:", {g: (v.get("detected"), v.get("seizures")) if "seizures" in v else v["alarms_per_hour"]
                        for g, v in cv["seizeit2"].items()})
    print(f"driving alarms/h hip {cv['accelerometry']['lh']['driving']['alarms_per_hour']:.2f}, "
          f"Epilepsy TEST {res['epilepsy_test']['EPILEPSY']['fired']}/{res['epilepsy_test']['EPILEPSY']['series']}")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
