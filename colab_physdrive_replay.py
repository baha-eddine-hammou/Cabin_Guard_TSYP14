"""Run CabinGuard-ADI PhysDrive replay in one Google Colab cell.

Usage:
1. Upload this file to Colab or paste it into one cell.
2. If the project is not already present, upload a ZIP named prototype.zip.
3. KaggleHub may request Kaggle authentication for the PhysDrive download.

This validates physiological replay only. PhysDrive does not provide the
CabinGuard headrest IMU, seatback FSR, or steering-grip channels.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath


ROOT = Path("/content")
PROJECT_ROOT = ROOT / "prototype"
DATASET_ID = "xiaoyang274/physdrive"


def install_dependencies() -> None:
    packages = ["numpy>=2.0", "scipy>=1.18", "rich>=15.0", "cryptography>=42.0", "kagglehub", "scikit-learn>=1.4", "joblib>=1.3"]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *packages])


def find_project_root(search_root: Path = ROOT) -> Path | None:
    candidates = [PROJECT_ROOT, ROOT, search_root]
    for candidate in candidates:
        if (candidate / "cabinguard" / "__init__.py").exists():
            return candidate
    for marker in search_root.rglob("__init__.py"):
        if marker.parent.name == "cabinguard":
            return marker.parent.parent
    return None


def upload_project_if_needed() -> Path:
    project = find_project_root()
    if project is not None:
        return project

    from google.colab import files

    # Colab renames repeated uploads, for example prototype (1).zip. Reuse an
    # existing ZIP in /content before opening another upload dialog.
    existing_zips = sorted(ROOT.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    if existing_zips:
        zip_names = [existing_zips[0].name]
        uploaded = {}
        print(f"Using existing project archive: {zip_names[0]}")
    else:
        print("Upload a ZIP containing the project's prototype folder, preferably named prototype.zip")
        uploaded = files.upload()
        zip_names = [name for name in uploaded if name.lower().endswith(".zip")]
    if not zip_names:
        raise RuntimeError("No project ZIP was uploaded")

    extract_root = ROOT / "cabinguard_project"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(exist_ok=True)
    archive_path = ROOT / zip_names[0] if not uploaded else Path(zip_names[0])
    with zipfile.ZipFile(archive_path) as archive:
        # Windows-created ZIPs may store paths with backslashes. Normalize
        # them before extraction because Colab runs on Linux.
        for member in archive.infolist():
            normalized_name = member.filename.replace("\\", "/")
            relative_name = PurePosixPath(normalized_name)
            if relative_name.is_absolute() or ".." in relative_name.parts:
                raise RuntimeError(f"Unsafe ZIP member path: {member.filename}")
            if ".pytest_cache" in relative_name.parts or "__pycache__" in relative_name.parts:
                continue
            target = extract_root.joinpath(*relative_name.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))

    project = find_project_root(extract_root)
    if project is None:
        visible = [str(path.relative_to(extract_root)) for path in extract_root.rglob("*")]
        raise RuntimeError(
            "The uploaded ZIP does not contain cabinguard/__init__.py. "
            f"First extracted paths: {visible[:20]}"
        )
    return project


def download_physdrive() -> Path:
    try:
        import kagglehub

        path = Path(kagglehub.dataset_download(DATASET_ID))
        print(f"PhysDrive available at: {path}")
        return path
    except Exception as first_error:
        print(f"KaggleHub download did not complete: {first_error}")
        print("Upload kaggle.json, or upload a downloaded PhysDrive ZIP instead.")

    from google.colab import files

    uploaded = files.upload()
    kaggle_json = next((name for name in uploaded if name == "kaggle.json"), None)
    if kaggle_json:
        kaggle_dir = Path.home() / ".kaggle"
        kaggle_dir.mkdir(exist_ok=True)
        shutil.copy(kaggle_json, kaggle_dir / "kaggle.json")
        (kaggle_dir / "kaggle.json").chmod(0o600)
        output_dir = ROOT / "physdrive"
        output_dir.mkdir(exist_ok=True)
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-q", "kaggle"
        ])
        subprocess.check_call([
            "kaggle", "datasets", "download", "-d", DATASET_ID,
            "-p", str(output_dir), "--unzip"
        ])
        return output_dir

    zip_names = [name for name in uploaded if name.lower().endswith(".zip")]
    if zip_names:
        output_dir = ROOT / "physdrive_upload"
        output_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_names[0]) as archive:
            archive.extractall(output_dir)
        return output_dir

    raise RuntimeError("Neither kaggle.json nor a PhysDrive ZIP was uploaded")


def run_replay(project: Path, dataset: Path) -> None:
    sys.path.insert(0, str(project))
    from cabinguard.feature_extraction import FeatureExtractor
    from cabinguard.physdrive_adapter import PhysDriveAdapter
    from cabinguard.watchdog import CrossSensorWatchdog

    adapter = PhysDriveAdapter(dataset)
    extractor = FeatureExtractor()
    watchdog = CrossSensorWatchdog()

    total = 0
    hr_values: list[float] = []
    modes: Counter[str] = Counter()
    degraded_predictions: Counter[str] = Counter()
    first_rows: list[dict[str, object]] = []

    for frame in adapter.iter_frames():
        features = extractor.process_frame(frame)
        decision = watchdog.evaluate(features)
        total += 1
        hr_values.append(frame.rppg_hr_bpm)
        modes[decision.operational_mode] += 1
        # The HR value is real PhysDrive data. IMU, FSR, grip, eye, and pitch
        # are unavailable in PhysDrive and are represented by explicit adapter
        # placeholders. Therefore degraded classifier outputs are diagnostics,
        # not medical-event labels or performance measurements.
        degraded_predictions[decision.active_class] += 1
        if len(first_rows) < 5:
            first_rows.append({
                "timestamp_s": frame.timestamp,
                "heart_rate_bpm": frame.rppg_hr_bpm,
                "operational_mode": decision.operational_mode,
                "degraded_prediction": decision.active_class,
                "imu_available": frame.imu_heartbeat_ok,
            })

    if total == 0:
        raise RuntimeError("No PhysDrive rows were found")

    # Extract sliding 10-second trajectory windows and train PhysDriveQualityModel
    from cabinguard.dataset_models import PhysDriveQualityModel
    from sklearn.metrics import classification_report, accuracy_score
    import numpy as np

    print("Extracting sliding physiological trajectory windows for AI model training...")
    window_len = 100  # 10s at 10 Hz
    X_traj = []
    y_traj = []
    hr_arr = np.asarray(hr_values, dtype=float)

    for i in range(0, len(hr_arr) - window_len + 1, 20):  # hop = 2s
        w = hr_arr[i:i + window_len]
        feat = PhysDriveQualityModel.extract_trajectory_features(w)
        mean_h = feat[0]
        # Classify state: 0: Normal (60-100), 1: Bradycardia (<55), 2: Tachycardia (>105), 3: High Instability (std > 15)
        if feat[1] > 15.0:
            label = 3
        elif mean_h < 55.0:
            label = 1
        elif mean_h > 105.0:
            label = 2
        else:
            label = 0
        X_traj.append(feat)
        y_traj.append(label)

    model_info = {}
    if len(X_traj) >= 10:
        X_t = np.asarray(X_traj, dtype=float)
        y_t = np.asarray(y_traj, dtype=int)
        model = PhysDriveQualityModel()
        model.fit(X_t, y_t)
        preds = model.predict(X_t)
        acc = float(accuracy_score(y_t, preds))
        model_path = ROOT / "physdrive_quality_model.joblib"
        model.save(model_path)
        print(f"PhysDriveQualityModel trained on {len(X_t)} windows (accuracy: {acc * 100:.2f}%). Saved to {model_path}")
        model_info = {
            "windows_trained": len(X_t),
            "training_accuracy": round(acc, 4),
            "state_distribution": dict(Counter(y_traj)),
            "saved_model_path": str(model_path),
        }

    summary = {
        "frames_replayed": total,
        "real_hr_frames": total,
        "mean_heart_rate_bpm": round(sum(hr_values) / len(hr_values), 3),
        "min_heart_rate_bpm": round(min(hr_values), 3),
        "max_heart_rate_bpm": round(max(hr_values), 3),
        "operational_modes": dict(modes),
        "degraded_predictions_unscored": dict(degraded_predictions),
        "trained_quality_model": model_info,
        "real_modalities_used": ["PhysDrive HR.mat heart-rate signal"],
        "unavailable_modalities": [
            "headrest IMU", "seatback FSR", "steering grip", "eye aspect ratio",
            "head pitch", "raw camera rPPG estimation"
        ],
        "pipeline_stages_exercised": [
            "PhysDrive adapter", "FeatureExtractor", "Degraded Mode 2 watchdog", "PhysDriveQualityModel training"
        ],
        "sample_rows": first_rows,
        "scope": "real PhysDrive HR replay and stability model training; no seizure/syncope performance claim",
    }
    (ROOT / "physdrive_real_pipeline_report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


def main() -> None:
    install_dependencies()
    project = upload_project_if_needed()
    dataset = download_physdrive()
    run_replay(project, dataset)


if __name__ == "__main__":
    main()
