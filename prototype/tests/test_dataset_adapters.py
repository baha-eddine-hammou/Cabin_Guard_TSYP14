"""Configuration, CMAC vectors, and the public-dataset adapters and auxiliary models.

Run with pytest, or directly: python tests/test_dataset_adapters.py
"""
import sys
import time
import traceback
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_results: list[tuple[str, bool, str]] = []

def _run(name: str, fn):
    global _PASS, _FAIL
    try:
        fn()
        _results.append((name, True, ""))
        _PASS += 1
    except Exception as exc:
        _FAIL += 1
        _results.append((name, False, f"{type(exc).__name__}: {exc}"))

def _assert(condition: bool, message: str = "Assertion failed"):
    if not condition:
        raise AssertionError(message)

def test_1_config_consistency():
    """Test 1: configuration constants match the values the paper reports."""
    from cabinguard import config
    _assert(config.DRIVER_OVERRIDE_TORQUE_NM == 4.0,
            f"Override torque must be 4.0 Nm, got {config.DRIVER_OVERRIDE_TORQUE_NM}")
    _assert(config.CONFIDENCE_THRESHOLD_GAMMA == 0.85,
            f"Gamma must be 0.85, got {config.CONFIDENCE_THRESHOLD_GAMMA}")
    _assert(config.VERIFICATION_DURATION_S == 2.0,
            f"Verification window must be 2.0s, got {config.VERIFICATION_DURATION_S}")
    _assert(config.MEC_PAYLOAD_SIZE_BYTES == 76,
            f"MEC size must be 76 bytes, got {config.MEC_PAYLOAD_SIZE_BYTES}")
    _assert(config.MRM_TARGET_DECEL_MSS == -3.2,
            f"MRM decel must be -3.2 m/s^2, got {config.MRM_TARGET_DECEL_MSS}")
    _assert(config.CAN_MRM_MSG_ID == 0x120,
            f"CAN MRM ID must be 0x120, got {hex(config.CAN_MRM_MSG_ID)}")

def test_2_rfc4493_cmac():
    """Test 2: AES-128-CMAC produces all four RFC 4493 official test vectors."""
    from cabinguard.crypto import aes128_cmac, run_rfc4493_self_test
    ok = run_rfc4493_self_test()
    _assert(ok, "RFC 4493 self-test failed")

    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    # Example 1: zero-length
    tag = aes128_cmac(key, b"")
    _assert(tag.hex() == "bb1d6929e95937287fa37d129b756746",
            f"RFC4493 Example1: {tag.hex()}")
    # Example 2: 16 bytes
    tag = aes128_cmac(key, bytes(range(16)))
    _assert(tag.hex() == "5c7efb43900da87c2b8d87ee066d791b",
            f"RFC4493 Example2: {tag.hex()}")

def test_15_physdrive_adapter_replay():
    """Test 15: PhysDrive CSV rows replay into explicit frame values."""
    from cabinguard.physdrive_adapter import PhysDriveAdapter

    with tempfile.TemporaryDirectory() as directory:
        session_dir = Path(directory) / "RGB and IR (one subject sample)" / "AMH1" / "AS"
        session_dir.mkdir(parents=True)
        (session_dir / "Recording_Physiological_Data.csv").write_text(
            "timestamp,HR\n0.0,72.0\n0.1,73.5\n",
            encoding="utf-8",
        )
        frames = list(PhysDriveAdapter(directory).iter_frames())

    _assert(len(frames) == 2, f"Expected two replay frames, got {len(frames)}")
    _assert(frames[1].rppg_hr_bpm == 73.5, "Heart rate must replay from PhysDrive CSV")
    _assert(not frames[0].imu_heartbeat_ok,
            "Missing PhysDrive IMU must be reported as unavailable")

def test_16_physdrive_hr_mat_fallback():
    """Test 16: an HR.mat-only PhysDrive session is replayable."""
    from scipy.io import savemat
    from cabinguard.physdrive_adapter import PhysDriveAdapter

    with tempfile.TemporaryDirectory() as directory:
        label_dir = Path(directory) / "mmWave" / "AMH1" / "Label"
        label_dir.mkdir(parents=True)
        savemat(label_dir / "HR.mat", {"HR": [[70.0], [71.5], [73.0]]})
        frames = list(PhysDriveAdapter(directory).iter_frames())

    _assert(len(frames) == 3, f"Expected three HR.mat frames, got {len(frames)}")
    _assert(frames[-1].rppg_hr_bpm == 73.0,
            "Heart rate must replay from HR.mat fallback")

def test_17_mhealth_adapter_fixture():
    """Test 17: MHEALTH parses 24 columns into typed measured signals."""
    import numpy as np
    from cabinguard.uci_adapters import MHealthAdapter

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "mHealth_subject1.log"
        rows = np.zeros((100, 24), dtype=float)
        rows[:, 0] = 1.0
        rows[:, 3] = 0.2
        rows[:, 23] = 4
        np.savetxt(path, rows)
        windows = list(MHealthAdapter(directory).iter_windows(window_s=2.0, hop_s=2.0))

    _assert(len(windows) == 1, f"Expected one MHEALTH window, got {len(windows)}")
    window = windows[0]
    _assert(window.subject_id == "1", "MHEALTH subject ID must be preserved")
    _assert(window.labels["activity_label"] == 4, "MHEALTH activity label must be preserved")
    _assert(window.signal("chest_ecg").values.shape == (100, 2),
            "MHEALTH ECG must retain two channels")
    _assert(window.signal("chest_accel").sample_rate_hz == 50.0,
            "MHEALTH native rate must be 50 Hz")

def test_18_uci_har_adapter_fixture():
    """Test 18: UCI HAR preserves windows, labels, and subject IDs."""
    import numpy as np
    from cabinguard.uci_adapters import UciHarAdapter

    with tempfile.TemporaryDirectory() as directory:
        split_dir = Path(directory) / "train"
        signal_dir = split_dir / "Inertial Signals"
        signal_dir.mkdir(parents=True)
        for group in ("body_acc", "body_gyro"):
            for axis in ("x", "y", "z"):
                np.savetxt(signal_dir / f"{group}_{axis}_train.txt", np.zeros((1, 128)))
        np.savetxt(split_dir / "y_train.txt", np.array([[6]]), fmt="%d")
        np.savetxt(split_dir / "subject_train.txt", np.array([[7]]), fmt="%d")
        windows = list(UciHarAdapter(directory).iter_windows())

    _assert(len(windows) == 1, f"Expected one UCI HAR window, got {len(windows)}")
    window = windows[0]
    _assert(window.subject_id == "7", "UCI HAR subject ID must be preserved")
    _assert(window.labels["activity_label"] == 6, "UCI HAR label must be preserved")
    _assert(window.signal("body_accel").values.shape == (128, 3),
            "UCI HAR acceleration window must be 128x3")
    _assert(window.metadata["split"] == "train", "UCI HAR split metadata must be preserved")

def test_19_mitbih_wfdb_fixture():
    """Test 19: MIT-BIH adapter preserves ECG rate and beat annotations."""
    import numpy as np
    try:
        import wfdb
    except ImportError:
        print(" (skipped: wfdb not installed)", end="")
        return
    from cabinguard.mitbih_adapter import MitBihAdapter

    with tempfile.TemporaryDirectory() as directory:
        t = np.arange(3600, dtype=float) / 360.0
        ecg = (0.1 * np.sin(2 * np.pi * 1.2 * t)).reshape(-1, 1)
        wfdb.wrsamp(
            "100", fs=360, units=["mV"], sig_name=["MLII"],
            p_signal=ecg, write_dir=directory,
        )
        wfdb.wrann(
            "100", extension="atr", sample=np.array([100, 400]),
            symbol=["N", "V"], write_dir=directory,
        )
        windows = list(MitBihAdapter(directory).iter_windows(window_s=2.0))

    _assert(len(windows) > 0, "MIT-BIH must produce ECG windows")
    window = windows[0]
    _assert(window.signal("ecg").sample_rate_hz == 360.0,
            "MIT-BIH native rate must be 360 Hz")
    _assert(window.signal("ecg").values.shape[1] == 1,
            "MIT-BIH fixture must retain one ECG channel")
    all_symbols = [symbol for item in windows for symbol in item.labels["beat_annotation_symbols"]]
    _assert("N" in all_symbols and "V" in all_symbols,
            "MIT-BIH beat annotation symbols must be preserved")

def test_20_mitbih_arrhythmia_model_training():
    """Test 20: MitBihArrhythmiaClassifier trains, predicts probabilities, and serializes."""
    import numpy as np
    from cabinguard.dataset_models import MitBihArrhythmiaClassifier

    # 10 mock beats (36 features each)
    X = np.random.randn(12, 36)
    y = ["Normal_N", "Ventricular_V", "Normal_N", "Other_Supraventricular"] * 3
    clf = MitBihArrhythmiaClassifier().fit(X, y)
    probs = clf.predict_proba(X[:2])
    _assert(probs.shape == (2, 3), "predict_proba must return shape (N, 3)")
    _assert(np.allclose(np.sum(probs, axis=1), 1.0), "Probabilities must sum to 1.0")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test_mitbih.joblib"
        clf.save(p)
        loaded = MitBihArrhythmiaClassifier.load(p)
        _assert(loaded.predict(X[:1])[0] in {"Normal_N", "Ventricular_V", "Other_Supraventricular"})

def test_21_mhealth_activity_model_training():
    """Test 21: MHealthActivityClassifier trains on multi-sensor feature vectors."""
    import numpy as np
    from cabinguard.dataset_models import MHealthActivityClassifier
    from cabinguard.dataset_types import DatasetWindow, SignalRecord

    # Create synthetic MHEALTH window fixture
    window = DatasetWindow(
        dataset_name="UCI-MHEALTH", subject_id="1", session_id="s1",
        start_time_s=0.0, end_time_s=2.0,
        signals={
            "chest_accel": SignalRecord(np.random.randn(100, 3), 50.0, "m/s^2"),
            "chest_ecg": SignalRecord(np.random.randn(100, 2), 50.0, "mV"),
        },
        labels={"activity_label": 1},
    )
    feat = MHealthActivityClassifier.extract_window_features(window)
    _assert(len(feat) > 10, "MHEALTH feature vector must be non-empty")

    X = np.random.randn(10, len(feat))
    y = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    clf = MHealthActivityClassifier().fit(X, y)
    preds = clf.predict(X[:2])
    _assert(len(preds) == 2, "predict must return predictions for all inputs")

def test_22_uci_har_activity_model_training():
    """Test 22: UciHarActivityClassifier trains on 128-sample inertial signal windows."""
    import numpy as np
    from cabinguard.dataset_models import UciHarActivityClassifier
    from cabinguard.dataset_types import DatasetWindow, SignalRecord

    window = DatasetWindow(
        dataset_name="UCI-HAR", subject_id="1", session_id="s1",
        start_time_s=0.0, end_time_s=2.56,
        signals={
            "body_accel": SignalRecord(np.random.randn(128, 3), 50.0, "g"),
            "body_gyro": SignalRecord(np.random.randn(128, 3), 50.0, "rad/s"),
        },
        labels={"activity_label": 1},
    )
    feat = UciHarActivityClassifier.extract_window_features(window)
    _assert(len(feat) == 30, f"Expected 30 features from 2x15 descriptors, got {len(feat)}")

    X = np.random.randn(12, 30)
    y = [1, 2, 3, 4, 5, 6] * 2
    clf = UciHarActivityClassifier().fit(X, y)
    preds = clf.predict(X[:3])
    _assert(len(preds) == 3, "predict must classify all test windows")

def test_23_physdrive_quality_model_training():
    """Test 23: PhysDriveQualityModel extracts trajectory features and predicts state."""
    import numpy as np
    from cabinguard.dataset_models import PhysDriveQualityModel

    hr_series = np.array([72.0 + 2.0 * np.sin(i / 10.0) for i in range(100)])
    feat = PhysDriveQualityModel.extract_trajectory_features(hr_series)
    _assert(len(feat) == 6, f"Expected 6 trajectory features, got {len(feat)}")

    X = np.array([feat + np.random.randn(6) * 0.5 for _ in range(8)])
    y = [0, 1, 2, 0, 1, 2, 0, 1]
    model = PhysDriveQualityModel().fit(X, y)
    preds = model.predict(X[:2])
    _assert(len(preds) == 2, "predict must produce predictions")

# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  CabinGuard-ADI Unit Test Suite  (23 Tests)")
    print("=" * 60)

    tests = [
        ("1. Config Consistency (4.0 Nm unified)",         test_1_config_consistency),
        ("2. RFC 4493 AES-128-CMAC Test Vectors",          test_2_rfc4493_cmac),
        ("15. PhysDrive Adapter Replay",                   test_15_physdrive_adapter_replay),
        ("16. PhysDrive HR.mat Fallback",                  test_16_physdrive_hr_mat_fallback),
        ("17. MHEALTH Adapter Fixture",                   test_17_mhealth_adapter_fixture),
        ("18. UCI HAR Adapter Fixture",                   test_18_uci_har_adapter_fixture),
        ("19. MIT-BIH WFDB Fixture",                      test_19_mitbih_wfdb_fixture),
        ("20. MIT-BIH Arrhythmia ML Model Training",      test_20_mitbih_arrhythmia_model_training),
        ("21. MHEALTH Multi-Sensor Activity ML Training",  test_21_mhealth_activity_model_training),
        ("22. UCI HAR Inertial Activity ML Training",      test_22_uci_har_activity_model_training),
        ("23. PhysDrive Physiological Quality ML Training", test_23_physdrive_quality_model_training),
    ]

    for name, fn in tests:
        _run(name, fn)

    print()
    for name, passed, msg in _results:
        status = "OK  " if passed else "FAIL"
        print(f"  [{status}] {name}")
        if msg:
            print(f"        -> {msg}")

    print()
    print(f"  Results: {_PASS}/{len(tests)} passed", end="")
    if _FAIL == 0:
        print("  [ALL PASS]")
    else:
        print(f"  [{_FAIL} FAILED]")
    print("=" * 60)
    sys.exit(0 if _FAIL == 0 else 1)

