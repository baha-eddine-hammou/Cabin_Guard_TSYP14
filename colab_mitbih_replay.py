"""Stream, train, and test MIT-BIH ECG Arrhythmia AI model in Google Colab.

This downloads real PhysioNet WFDB records, extracts beat morphology around R-peaks,
trains an AI beat classification model (Normal vs Ventricular Ectopic vs Other),
evaluates classification metrics, and saves the trained model artifact.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import numpy as np

# Use /content if in Colab, else local directory
ROOT = Path("/content") if Path("/content").exists() else Path(__file__).resolve().parent
PROJECT_ROOT = ROOT / "prototype" if (ROOT / "prototype").exists() else ROOT
RECORDS = ("100", "200")


def install_dependencies() -> None:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "numpy>=2.0", "scipy>=1.18", "wfdb>=4.1", "scikit-learn>=1.4", "joblib>=1.3"
    ])


def find_project_root() -> Path | None:
    candidates = [PROJECT_ROOT, ROOT, ROOT / "prototype", Path.cwd(), Path.cwd() / "prototype"]
    for cand in candidates:
        if (cand / "cabinguard" / "__init__.py").exists() and (cand / "cabinguard" / "mitbih_adapter.py").exists():
            return cand
    for marker in ROOT.rglob("__init__.py"):
        if marker.parent.name == "cabinguard":
            candidate = marker.parent.parent
            if (candidate / "cabinguard" / "mitbih_adapter.py").exists():
                return candidate
    return None


def ensure_project() -> Path:
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
        destination = ROOT / "mitbih_project"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archives[0]) as archive:
            for member in archive.infolist():
                relative = PurePosixPath(member.filename.replace("\\", "/"))
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
            raise RuntimeError("Uploaded ZIP does not contain cabinguard/mitbih_adapter.py")
        return project
    except ImportError:
        raise RuntimeError("Prototype project not found and not running in interactive Colab")


def run() -> dict[str, object]:
    project = ensure_project()
    print(f"Using prototype project: {project}")
    adapter_path = project / "cabinguard" / "mitbih_adapter.py"
    if not adapter_path.exists():
        raise FileNotFoundError(f"MIT-BIH adapter not found at {adapter_path}")

    for module_name in list(sys.modules):
        if module_name == "cabinguard" or module_name.startswith("cabinguard."):
            del sys.modules[module_name]
    sys.path.insert(0, str(project))

    import wfdb
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    from cabinguard.mitbih_adapter import MitBihAdapter
    from cabinguard.dataset_models import MitBihArrhythmiaClassifier, map_mitbih_symbol

    print(f"Streaming and downloading MIT-BIH records: {RECORDS} via PhysioNet WFDB...")
    adapter = MitBihAdapter(record_names=RECORDS)
    windows = list(adapter.iter_windows(window_s=10.0))
    if not windows:
        raise RuntimeError("No MIT-BIH windows were produced")

    print(f"Extracted {len(windows)} windows. Building beat dataset around annotated R-peaks...")
    X_beats: list[np.ndarray] = []
    y_beats: list[str] = []
    symbol_counter: Counter[str] = Counter()

    for window in windows:
        ecg_rec = window.signal("ecg")
        if ecg_rec is None:
            continue
        ecg_vals = ecg_rec.values
        samples = window.labels.get("beat_annotation_samples", [])
        symbols = window.labels.get("beat_annotation_symbols", [])

        for sample_idx, sym in zip(samples, symbols):
            if sym in {"+", "~", "|", "x"}:
                continue  # Skip non-beat markers
            symbol_counter[sym] += 1
            feat = MitBihArrhythmiaClassifier.extract_beat_features(ecg_vals, sample_idx)
            label = map_mitbih_symbol(sym)
            X_beats.append(feat)
            y_beats.append(label)

    X = np.asarray(X_beats, dtype=float)
    y = np.asarray(y_beats)
    print(f"Total labeled beats extracted: {len(y)}. Distribution: {dict(Counter(y))}")

    counts = Counter(y)
    strat = y if all(c >= 2 for c in counts.values()) else None
    # Train / Test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=strat
    )

    print("Training MitBihArrhythmiaClassifier (Random Forest)...")
    clf = MitBihArrhythmiaClassifier()
    clf.fit(X_train, y_train)

    # Evaluate
    y_pred = clf.predict(X_test)
    acc = float(accuracy_score(y_test, y_pred))
    report_dict = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    unique_labels = sorted(list(set(y)))
    cm = confusion_matrix(y_test, y_pred, labels=unique_labels).tolist()

    # Save model
    model_output_path = ROOT / "mitbih_arrhythmia_model.joblib"
    clf.save(model_output_path)
    print(f"Model saved to: {model_output_path}")

    report = {
        "dataset": "PhysioNet MIT-BIH Arrhythmia Database",
        "records_evaluated": list(RECORDS),
        "total_windows": len(windows),
        "total_beats_extracted": len(y),
        "raw_symbols_observed": dict(symbol_counter),
        "beat_class_distribution": dict(Counter(y)),
        "train_samples": len(y_train),
        "test_samples": len(y_test),
        "model_architecture": "StandardScaler + RandomForest (100 estimators, max_depth=12)",
        "test_accuracy": round(acc, 4),
        "labels": unique_labels,
        "confusion_matrix": cm,
        "classification_report": report_dict,
        "saved_model_path": str(model_output_path),
        "scope": "real ECG beat morphology and arrhythmia classification; not syncope or driver crisis",
    }

    report_path = ROOT / "mitbih_real_pipeline_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report saved to: {report_path}")
    return report


def main() -> None:
    install_dependencies()
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
