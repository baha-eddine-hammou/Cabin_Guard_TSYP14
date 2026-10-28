"""Checks of the motion branch on datasets that need open internet (run in Colab).

    python experiments/realdata/external_checks.py epilepsy mhealth har

The model checked is ``models/motion_branch_injected.joblib``, the motion
branch trained on injected jerks; ``train_motion_real.py`` evaluates the
deployed branch trained on recorded motion.

* ``epilepsy``: UEA "Epilepsy" (Villar et al.): healthy participants with a
  wrist accelerometer at 16 Hz performing seizure mimics, walking, running
  and sawing. Two tests: (a) transfer, the injected-jerk motion branch (trained on
  hip driving data with injected jerks) applied unchanged after resampling to
  100 Hz; (b) within-dataset, the same features and model family trained on
  the official TRAIN split and scored on TEST. Real recorded seizure-like
  motion, which the injected jerks only model; still a mimic by healthy
  actors, at the wrist, not a seizure at a seat.
* ``mhealth``, ``har``: everyday activities from UCI MHEALTH (chest sensor,
  50 Hz) and UCI HAR (waist phone, 50 Hz). No seizures: the only question is
  how often the motion branch fires on rhythmic non-driving movement.

Writes ``results/external_checks.json`` (merged with earlier runs).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import joblib
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from cabinguard import config  # noqa: E402
from cabinguard.motion_features import motion_features  # noqa: E402

DATA = ROOT.parent / "data"
OUT = ROOT / "results" / "external_checks.json"
FS = 100.0
WIN, STEP = 200, 50                       # 2 s windows every 0.5 s at 100 Hz
PERSIST = int(config.VERIFICATION_DURATION_S / 0.5)
GAMMA = config.CONFIDENCE_THRESHOLD_GAMMA
G = 9.80665

EPILEPSY_URLS = ("https://timeseriesclassification.com/aeon-toolkit/Epilepsy.zip",
                 "https://www.timeseriesclassification.com/aeon-toolkit/Epilepsy.zip")
MHEALTH_URL = "https://archive.ics.uci.edu/static/public/319/mhealth+dataset.zip"
HAR_URL = "https://archive.ics.uci.edu/static/public/240/human+activity+recognition+using+smartphones.zip"
MHEALTH_ACTIVITIES = {1: "standing", 2: "sitting", 3: "lying", 4: "walking", 5: "climbing stairs",
                      6: "waist bends", 7: "arm elevation", 8: "knee bends", 9: "cycling", 10: "jogging",
                      11: "running", 12: "jumping"}
HAR_ACTIVITIES = {1: "walking", 2: "upstairs", 3: "downstairs", 4: "sitting", 5: "standing", 6: "lying"}


# ---------------------------------------------------------------- loading ---
def download(urls, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in (urls if isinstance(urls, (list, tuple)) else [urls]):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 (fixed hosts)
                dest.write_bytes(r.read())
            return dest
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise OSError("; ".join(errors))


def parse_ts(text: str):
    """Minimal reader for the sktime/aeon .ts format with equal-length series."""
    X, y, in_data = [], [], False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("@data"):
            in_data = True
            continue
        if not in_data or line.startswith("@"):
            continue
        *dims, label = line.split(":")
        X.append([[float(v) for v in d.split(",")] for d in dims])
        y.append(label.strip())
    return np.array(X, float), np.array(y)          # X: (n, channels, length)


def load_epilepsy():
    z = zipfile.ZipFile(download(EPILEPSY_URLS, DATA / "external" / "Epilepsy.zip"))
    parts = {}
    for split in ("TRAIN", "TEST"):
        name = next(n for n in z.namelist() if n.endswith(f"Epilepsy_{split}.ts"))
        parts[split] = parse_ts(z.read(name).decode("utf-8", "replace"))
    X, y = parts["TRAIN"]
    if X.shape[1] != 3 or not {"EPILEPSY", "WALKING", "RUNNING", "SAWING"} <= set(np.char.upper(y.astype(str))):
        raise ValueError(f"unexpected Epilepsy archive content: shape {X.shape}, labels {sorted(set(y))}")
    return parts


def _open_inner(z: zipfile.ZipFile) -> zipfile.ZipFile:
    """UCI's static downloads sometimes wrap the original zip in another zip."""
    inner = [n for n in z.namelist() if n.lower().endswith(".zip")]
    return zipfile.ZipFile(io.BytesIO(z.read(inner[0]))) if inner else z


def load_mhealth():
    z = _open_inner(zipfile.ZipFile(download(MHEALTH_URL, DATA / "external" / "mhealth.zip")))
    out = {}
    for name in sorted(n for n in z.namelist() if n.endswith(".log") and "mHealth_subject" in n):
        arr = np.loadtxt(io.BytesIO(z.read(name)))
        out[Path(name).stem] = (arr[:, 0:3] / G, arr[:, 23].astype(int))   # chest accel in g, label
    if not out:
        raise ValueError("no mHealth_subject*.log files in the MHEALTH archive")
    return out


def load_har():
    z = _open_inner(zipfile.ZipFile(download(HAR_URL, DATA / "external" / "har.zip")))
    names = z.namelist()

    def rows(suffix):
        n = next(x for x in names if x.endswith(suffix))
        return np.loadtxt(io.BytesIO(z.read(n)))
    out = {}
    for split in ("train", "test"):
        acc = np.stack([rows(f"Inertial Signals/total_acc_{a}_{split}.txt") for a in "xyz"], axis=2)  # (n, 128, 3) g
        out[split] = (acc, rows(f"{split}/y_{split}.txt").astype(int), rows(f"{split}/subject_{split}.txt").astype(int))
    return out


# --------------------------------------------------------------- features ---
def to_100hz(x: np.ndarray, fs: float) -> np.ndarray:
    """Resample an (n, 3) series to 100 Hz with a polyphase filter."""
    from fractions import Fraction
    fr = Fraction(100, int(round(fs))).limit_denominator(100)
    return signal.resample_poly(x, fr.numerator, fr.denominator, axis=0)


def window_features(x100: np.ndarray) -> np.ndarray:
    return np.array([motion_features(x100[i:i + WIN], FS).vector()
                     for i in range(0, len(x100) - WIN + 1, STEP)])


def fires(p: np.ndarray) -> bool:
    run = 0
    for v in p >= GAMMA:
        run = run + 1 if v else 0
        if run >= PERSIST:
            return True
    return False


def deployed_motion():
    m = joblib.load(ROOT / "models" / "motion_branch_injected.joblib")
    return lambda F: m["model"].predict_proba(F)[:, 1]


# ------------------------------------------------------------------ checks ---
def check_epilepsy() -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    parts = load_epilepsy()
    score = deployed_motion()
    res = {"source": "UEA Epilepsy (Villar et al.), wrist accelerometer, 16 Hz, healthy actors",
           "transfer": {}, "within_dataset": {}}
    feats = {}
    for split, (X, y) in parts.items():
        feats[split] = [(window_features(to_100hz(x.T, 16.0)), str(lab).upper()) for x, lab in zip(X, y)]
    # (a) transfer: deployed branch, unchanged
    for lab in sorted({lab for _, lab in feats["TEST"]}):
        hits = [fires(score(F)) for F, l in feats["TEST"] if l == lab]
        res["transfer"][lab] = {"series": len(hits), "fired": int(sum(hits)), "rate": float(np.mean(hits))}
    # (b) within dataset: same features, model trained on TRAIN windows
    Xtr = np.vstack([F for F, _ in feats["TRAIN"]])
    ytr = np.concatenate([[lab == "EPILEPSY"] * len(F) for F, lab in feats["TRAIN"]])
    clf = HistGradientBoostingClassifier(max_iter=200, class_weight="balanced", random_state=0).fit(Xtr, ytr)
    series_score, truth = [], []
    for lab in sorted({lab for _, lab in feats["TEST"]}):
        hits = []
        for F, l in feats["TEST"]:
            if l != lab:
                continue
            p = clf.predict_proba(F)[:, 1]
            hits.append(fires(p))
            series_score.append(float(np.median(p)))
            truth.append(l == "EPILEPSY")
        res["within_dataset"][lab] = {"series": len(hits), "fired": int(sum(hits)), "rate": float(np.mean(hits))}
    res["within_dataset_auc_series"] = float(roc_auc_score(truth, series_score))
    return res


def check_mhealth() -> dict:
    score = deployed_motion()
    rates: dict = {}
    for _, (acc, lab) in load_mhealth().items():
        edges = np.flatnonzero(np.diff(lab)) + 1
        for a, b in zip(np.r_[0, edges], np.r_[edges, lab.size]):
            code = int(lab[a])
            if code == 0 or b - a < 2 * 50:
                continue
            F = window_features(to_100hz(acc[a:b], 50.0))
            if len(F) == 0:
                continue
            r = rates.setdefault(MHEALTH_ACTIVITIES[code], {"windows": 0, "confident": 0, "alarms": 0, "hours": 0.0})
            p = score(F)
            r["windows"] += len(F)
            r["confident"] += int((p >= GAMMA).sum())
            r["alarms"] += int(fires(p))
            r["hours"] += (b - a) / 50.0 / 3600
    return {"source": "UCI MHEALTH, chest accelerometer, 50 Hz", "by_activity": rates}


def check_har() -> dict:
    score = deployed_motion()
    rates: dict = {}
    for acc, lab, _ in load_har().values():
        for w, code in zip(acc, lab):
            F = window_features(to_100hz(w, 50.0))[:1]           # one 2 s window per 2.56 s sample
            r = rates.setdefault(HAR_ACTIVITIES[int(code)], {"windows": 0, "confident": 0})
            r["windows"] += 1
            r["confident"] += int(score(F)[0] >= GAMMA)
    for r in rates.values():
        r["window_rate"] = r["confident"] / r["windows"]
    return {"source": "UCI HAR, waist smartphone, total acceleration, 50 Hz", "by_activity": rates}


def main() -> None:
    which = sys.argv[1:] or ["epilepsy", "mhealth", "har"]
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for name in which:
        results[name] = {"epilepsy": check_epilepsy, "mhealth": check_mhealth, "har": check_har}[name]()
        print(name, json.dumps(results[name], indent=1)[:1500])
    OUT.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
