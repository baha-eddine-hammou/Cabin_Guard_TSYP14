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
    """Replay PhysDrive in-vehicle heart rate through the trained cardiac branch.

    PhysDrive provides a reference heart-rate series per session, not beat
    times, so beats are synthesised by integrating the rate; beat-to-beat
    variability is therefore underestimated. The report gives how often the
    cardiac branch on its own would exceed Gamma on real in-vehicle heart
    rate (a standalone false-alarm indicator), not seizure or syncope
    performance.
    """
    sys.path.insert(0, str(project))
    import numpy as np
    from cabinguard.cardiac_features import features_for_record
    from cabinguard.fusion import FusionClassifier
    from cabinguard.physdrive_adapter import PhysDriveAdapter

    clf = FusionClassifier(enabled=("cardiac",), cap=50.0)
    adapter = PhysDriveAdapter(dataset)
    sessions, windows, alarms, hr_all = 0, 0, Counter(), []
    for session in adapter.discover_sessions():
        frames = list(adapter.iter_session(session))
        if len(frames) < 20:
            continue
        t = np.array([f.timestamp for f in frames], float)
        hr = np.clip(np.array([f.rppg_hr_bpm for f in frames], float), 30, 220)
        phase = np.concatenate([[0.0], np.cumsum(np.diff(t) * hr[:-1] / 60.0)])
        beats = np.interp(np.arange(np.ceil(phase[-1])), phase, t)
        times = np.arange(t[0] + 10.0, t[-1], 1.0)
        if times.size == 0:
            continue
        feats = features_for_record(beats, times)
        post, _ = clf.combine(clf.batch_evidence(cardiac=feats), len(feats))
        top = post.argmax(1)
        for k in np.flatnonzero((top != 0) & (post.max(1) >= 0.85)):
            alarms[("Normal", "Syncope", "Seizure")[top[k]]] += 1
        sessions += 1
        windows += len(feats)
        hr_all.append(hr)
    if windows == 0:
        raise RuntimeError("No PhysDrive sessions long enough to replay were found")
    hr_cat = np.concatenate(hr_all)
    summary = {
        "sessions": sessions,
        "windows_1s": windows,
        "hours": round(windows / 3600, 3),
        "heart_rate_bpm": {"mean": round(float(hr_cat.mean()), 2), "min": round(float(hr_cat.min()), 2),
                           "max": round(float(hr_cat.max()), 2)},
        "cardiac_branch_alone_confident_event_windows": dict(alarms),
        "cardiac_branch_alone_confident_event_fraction": round(sum(alarms.values()) / windows, 5),
        "scope": "real PhysDrive in-vehicle heart rate through the cardiac branch only; beats synthesised "
                 "from the rate series; no seizure or syncope performance claim",
    }
    (ROOT / "physdrive_cardiac_branch_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    install_dependencies()
    project = upload_project_if_needed()
    dataset = download_physdrive()
    run_replay(project, dataset)


if __name__ == "__main__":
    main()
