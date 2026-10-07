"""Download, extract, and train machine learning models for UCI MHEALTH and UCI HAR in Colab.

Validates multi-sensor body network and smartphone inertial activity classification
using specialized classifiers with proper subject-independent and train/test evaluation.
Saves trained model artifacts for both datasets.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import numpy as np
from scipy import signal

ROOT = Path("/content") if Path("/content").exists() else Path(__file__).resolve().parent
PROJECT_ROOT = ROOT / "prototype" if (ROOT / "prototype").exists() else ROOT
MHEALTH_URL = "https://archive.ics.uci.edu/static/public/319/mhealth+dataset.zip"
HAR_URL = "https://archive.ics.uci.edu/static/public/240/human+activity+recognition+using+smartphones.zip"


def install_dependencies() -> None:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "numpy>=2.0", "scipy>=1.18", "scikit-learn>=1.4", "joblib>=1.3"
    ])


def find_project_root() -> Path | None:
    candidates = [PROJECT_ROOT, ROOT, ROOT / "prototype", Path.cwd(), Path.cwd() / "prototype"]
    for cand in candidates:
        if (cand / "cabinguard" / "__init__.py").exists() and (cand / "cabinguard" / "uci_adapters.py").exists():
            return cand
    for marker in ROOT.rglob("__init__.py"):
        if marker.parent.name == "cabinguard":
            candidate = marker.parent.parent
            if (candidate / "cabinguard" / "uci_adapters.py").exists():
                return candidate
    return None


def extract_project() -> Path:
    project = find_project_root()
    if project is not None:
        return project

    try:
        from google.colab import files
        print("Upload the refreshed prototype.zip")
        uploaded = files.upload()
        archives = [name for name in uploaded if name.lower().endswith(".zip")]
        if not archives:
            raise RuntimeError("No prototype ZIP was uploaded")

        destination = ROOT / "uci_project"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archives[0]) as archive:
            for member in archive.infolist():
                normalized = member.filename.replace("\\", "/")
                relative = PurePosixPath(normalized)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"Unsafe ZIP path: {member.filename}")
                if ".pytest_cache" in relative.parts or "__pycache__" in relative.parts:
                    continue
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))

        project = find_project_root()
        if project is None:
            raise RuntimeError("The uploaded ZIP does not contain cabinguard/__init__.py")
        return project
    except ImportError:
        raise RuntimeError("Prototype project not found and not running in interactive Colab")


def download_and_extract(name: str, url: str) -> Path:
    archive_path = ROOT / f"{name}.zip"
    extract_path = ROOT / name
    if not archive_path.exists():
        print(f"Downloading {name} from {url}...")
        urllib.request.urlretrieve(url, archive_path)
    if extract_path.exists():
        shutil.rmtree(extract_path)
    extract_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_path)

    # Specific handling for UCI HAR dataset which is a zip within a zip
    if name == "uci_har_dataset":
        nested_zip_path = extract_path / "UCI HAR Dataset.zip"
        if nested_zip_path.exists():
            print(f"Extracting nested zip for {name}...")
            with zipfile.ZipFile(nested_zip_path) as nested_archive:
                nested_archive.extractall(extract_path)
            nested_zip_path.unlink()
    return extract_path


def find_uci_har_root(extracted: Path) -> Path:
    """Find UCI HAR root across common ZIP nesting layouts."""
    for candidate in (extracted, extracted / "UCI HAR Dataset"):
        if (candidate / "train" / "Inertial Signals").exists():
            return candidate
    for inertial_dir in extracted.rglob("Inertial Signals"):
        if inertial_dir.parent.name == "train":
            return inertial_dir.parent.parent
    raise FileNotFoundError(
        f"Could not find UCI HAR train/Inertial Signals below {extracted}"
    )


def spectral_band_ratio(values: np.ndarray, sample_rate_hz: float) -> float:
    """Compute real-data 2--6 Hz energy / 0.5--20 Hz energy."""
    data = np.asarray(values, dtype=float)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[0] < 16:
        return 0.0
    centered = data - np.mean(data, axis=0, keepdims=True)
    frequencies, power = signal.welch(
        centered,
        fs=sample_rate_hz,
        nperseg=min(128, centered.shape[0]),
        axis=0,
        scaling="density",
    )
    power = np.sum(power, axis=1)
    total_mask = (frequencies >= 0.5) & (frequencies <= 20.0)
    band_mask = (frequencies >= 2.0) & (frequencies <= 6.0)
    total = float(np.sum(power[total_mask]))
    return float(np.sum(power[band_mask]) / total) if total > 1e-12 else 0.0


def run_training_pipelines(project: Path, mhealth_root: Path, har_root: Path) -> dict[str, object]:
    sys.path.insert(0, str(project))
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    from cabinguard.uci_adapters import MHealthAdapter, UciHarAdapter
    from cabinguard.dataset_models import MHealthActivityClassifier, UciHarActivityClassifier

    # ---------------------------------------------------------
    # 1. UCI MHEALTH Dataset Training
    # ---------------------------------------------------------
    print("\n--- Processing UCI MHEALTH Dataset ---")
    mhealth_adapter = MHealthAdapter(mhealth_root)
    mhealth_windows = list(mhealth_adapter.iter_windows(window_s=2.0, hop_s=2.0))
    print(f"Loaded {len(mhealth_windows)} MHEALTH windows across subjects.")

    X_mhealth = []
    y_mhealth = []
    subjects_mhealth = []
    for w in mhealth_windows:
        feat = MHealthActivityClassifier.extract_window_features(w)
        label = int(w.labels["activity_label"])
        # Filter out 0 (null/transitional state) if present
        if label > 0:
            X_mhealth.append(feat)
            y_mhealth.append(label)
            subjects_mhealth.append(w.subject_id)

    X_mh = np.asarray(X_mhealth, dtype=float)
    y_mh = np.asarray(y_mhealth, dtype=int)
    print(f"MHEALTH active windows: {len(y_mh)}, unique activities: {len(set(y_mh))}")

    # Train / Test split (stratified)
    X_train_mh, X_test_mh, y_train_mh, y_test_mh = train_test_split(
        X_mh, y_mh, test_size=0.25, random_state=42, stratify=y_mh
    )

    print("Training MHealthActivityClassifier (Random Forest)...")
    clf_mh = MHealthActivityClassifier()
    clf_mh.fit(X_train_mh, y_train_mh)
    y_pred_mh = clf_mh.predict(X_test_mh)
    acc_mh = float(accuracy_score(y_test_mh, y_pred_mh))
    rep_mh = classification_report(y_test_mh, y_pred_mh, output_dict=True, zero_division=0)

    mhealth_model_path = ROOT / "mhealth_activity_model.joblib"
    clf_mh.save(mhealth_model_path)
    print(f"MHEALTH Test Accuracy: {acc_mh * 100:.2f}%. Model saved to {mhealth_model_path}")

    # ---------------------------------------------------------
    # 2. UCI HAR Dataset Training
    # ---------------------------------------------------------
    print("\n--- Processing UCI HAR Dataset ---")
    har_base = find_uci_har_root(har_root)
    har_train_windows = list(UciHarAdapter(har_base, split="train").iter_windows())
    har_test_windows = list(UciHarAdapter(har_base, split="test").iter_windows())
    print(f"Loaded {len(har_train_windows)} train windows, {len(har_test_windows)} test windows.")

    X_train_har = np.asarray([UciHarActivityClassifier.extract_window_features(w) for w in har_train_windows], dtype=float)
    y_train_har = np.asarray([int(w.labels["activity_label"]) for w in har_train_windows], dtype=int)

    X_test_har = np.asarray([UciHarActivityClassifier.extract_window_features(w) for w in har_test_windows], dtype=float)
    y_test_har = np.asarray([int(w.labels["activity_label"]) for w in har_test_windows], dtype=int)

    print("Training UciHarActivityClassifier on official train split...")
    clf_har = UciHarActivityClassifier()
    clf_har.fit(X_train_har, y_train_har)

    y_pred_har = clf_har.predict(X_test_har)
    acc_har = float(accuracy_score(y_test_har, y_pred_har))
    rep_har = classification_report(y_test_har, y_pred_har, output_dict=True, zero_division=0)
    labels_har = sorted(list(set(y_test_har)))
    cm_har = confusion_matrix(y_test_har, y_pred_har, labels=labels_har).tolist()

    har_model_path = ROOT / "uci_har_model.joblib"
    clf_har.save(har_model_path)
    print(f"UCI HAR Test Accuracy on official test split: {acc_har * 100:.2f}%. Model saved to {har_model_path}")

    report = {
        "mhealth_model": {
            "dataset": "UCI MHEALTH",
            "train_samples": len(y_train_mh),
            "test_samples": len(y_test_mh),
            "test_accuracy": round(acc_mh, 4),
            "classification_report": rep_mh,
            "saved_path": str(mhealth_model_path),
            "architecture": "StandardScaler + RandomForestClassifier (100 trees, max_depth=15)",
        },
        "uci_har_model": {
            "dataset": "UCI Human Activity Recognition Using Smartphones",
            "train_samples": len(y_train_har),
            "test_samples": len(y_test_har),
            "test_accuracy": round(acc_har, 4),
            "confusion_matrix": cm_har,
            "classification_report": rep_har,
            "saved_path": str(har_model_path),
            "architecture": "StandardScaler + RandomForestClassifier (100 trees, max_depth=15)",
        },
        "scope": "real multi-sensor body network and smartphone activity classification; models trained and evaluated separately",
    }
    report_file = ROOT / "uci_real_dataset_report.json"
    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport written to: {report_file}")
    return report


def main() -> None:
    install_dependencies()
    project = extract_project()
    mhealth = download_and_extract("mhealth_dataset", MHEALTH_URL)
    har = download_and_extract("uci_har_dataset", HAR_URL)
    print(json.dumps(run_training_pipelines(project, mhealth, har), indent=2))


if __name__ == "__main__":
    main()
