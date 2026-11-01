"""
CabinGuard-ADI: Dataset-Specific Machine Learning Models
=========================================================
Implements specialized, trained AI classifiers for public real-world datasets:
  1. MitBihArrhythmiaClassifier:
     Trained on PhysioNet MIT-BIH Arrhythmia Database to differentiate Normal
     sinus rhythm beats ('N') from Ventricular ectopic / arrhythmia beats ('V').
  2. MHealthActivityClassifier:
     Trained on UCI MHEALTH multi-sensor body network (chest accel/ECG, ankle/arm IMU)
     to classify motor activity states (sitting, standing, walking, cycling, etc.).
  3. UciHarActivityClassifier:
     Trained on UCI Human Activity Recognition inertial signals (128-sample tri-axial
     body accel + gyro) to classify human postural & dynamic actions.
  4. PhysDriveQualityModel:
     Trained on PhysDrive in-cabin physiological trajectories to evaluate vital signal
     quality index (SQI) and detect cardiac rate stability vs abrupt anomalies.

Ethical & Clinical Boundary Disclosure:
---------------------------------------
These models are trained strictly on dataset-native labels and modalities.
They validate that real signal ingestion and machine learning pipelines work end-to-end.
They are NOT merged into a single pseudo-clinical detector because public activity
and arrhythmia labels do not represent acute driver syncope or epileptic seizures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import joblib
import numpy as np
from scipy import signal
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .dataset_types import DatasetWindow


# ---------------------------------------------------------------------------
# 1. MIT-BIH ECG Arrhythmia Classifier
# ---------------------------------------------------------------------------

MITBIH_BEAT_CLASSES = ("Normal_N", "Ventricular_V", "Other_Supraventricular")

def map_mitbih_symbol(symbol: str) -> str:
    """Map MIT-BIH beat annotation symbol to AAMI-aligned target class."""
    if symbol in {"N", "L", "R", "B"}:
        return "Normal_N"
    elif symbol in {"V", "E", "!"}:
        return "Ventricular_V"
    else:
        return "Other_Supraventricular"


class MitBihArrhythmiaClassifier:
    """Trained classifier for ECG beat morphology and arrhythmia detection."""

    DATASET_PROVENANCE = "PhysioNet MIT-BIH Arrhythmia Database (mitdb)"

    def __init__(self, model: Optional[Pipeline] = None):
        self.model = model
        self.classes_ = list(MITBIH_BEAT_CLASSES)

    @staticmethod
    def extract_beat_features(ecg_signal: np.ndarray, r_peak_sample: int, window_samples: int = 144) -> np.ndarray:
        """
        Extract morphology & statistical features from a window around an R-peak.
        At 360 Hz, 144 samples = 400 ms (160 ms pre-peak, 240 ms post-peak).
        """
        half_pre = int(window_samples * 0.4)
        half_post = window_samples - half_pre
        start = r_peak_sample - half_pre
        end = r_peak_sample + half_post

        sig_len = len(ecg_signal)
        if start < 0 or end > sig_len:
            # Pad boundary beats
            segment = np.zeros(window_samples, dtype=float)
            v_start = max(0, start)
            v_end = min(sig_len, end)
            p_start = max(0, -start)
            p_end = p_start + (v_end - v_start)
            segment[p_start:p_end] = ecg_signal[v_start:v_end, 0] if ecg_signal.ndim > 1 else ecg_signal[v_start:v_end]
        else:
            segment = ecg_signal[start:end, 0] if ecg_signal.ndim > 1 else ecg_signal[start:end]

        # Resample morphology to 32 normalized points
        resampled = signal.resample(segment, 32)
        norm_factor = np.std(resampled) + 1e-6
        norm_morph = (resampled - np.mean(resampled)) / norm_factor

        # Summary statistics
        feat_stats = np.array([
            float(np.mean(segment)),
            float(np.std(segment)),
            float(np.max(segment) - np.min(segment)),  # peak-to-peak amplitude
            float(np.sum(segment ** 2)),               # energy
        ])

        return np.concatenate([norm_morph, feat_stats])

    def fit(self, X: np.ndarray, y: Sequence[str]) -> "MitBihArrhythmiaClassifier":
        """Train Random Forest classifier on extracted beat feature vectors."""
        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)),
        ])
        self.model.fit(X, np.asarray(y))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict_proba")
        return self.model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict")
        return self.model.predict(X)

    def save(self, path: Union[str, Path]) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "provenance": self.DATASET_PROVENANCE, "classes": self.classes_}, p)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "MitBihArrhythmiaClassifier":
        data = joblib.load(path)
        inst = cls(model=data["model"])
        inst.classes_ = data.get("classes", list(MITBIH_BEAT_CLASSES))
        return inst


# ---------------------------------------------------------------------------
# 2. UCI MHEALTH Multi-Sensor Activity Classifier
# ---------------------------------------------------------------------------

class MHealthActivityClassifier:
    """Trained classifier for UCI MHEALTH multi-sensor body network data."""

    DATASET_PROVENANCE = "UCI MHEALTH Dataset (Chest Accel/ECG, Arm/Ankle IMU)"

    def __init__(self, model: Optional[Pipeline] = None):
        self.model = model

    @staticmethod
    def extract_window_features(window: DatasetWindow) -> np.ndarray:
        """Extract statistical & spectral features across all available MHEALTH modalities."""
        features = []
        for name in ("chest_accel", "chest_ecg", "ankle_accel", "ankle_gyro", "arm_accel", "arm_gyro"):
            rec = window.signal(name)
            if rec is not None and rec.values.shape[0] > 0:
                vals = rec.values
                mean = np.mean(vals, axis=0)
                std = np.std(vals, axis=0)
                rms = np.sqrt(np.mean(vals ** 2, axis=0))
                p2p = np.ptp(vals, axis=0)
                features.extend(mean.tolist())
                features.extend(std.tolist())
                features.extend(rms.tolist())
                features.extend(p2p.tolist())
            else:
                # 3 channels x 4 stats = 12 zeros default
                features.extend([0.0] * 12)

        # Spectral energy in 2-6 Hz band for chest accel
        chest = window.signal("chest_accel")
        if chest is not None and chest.values.shape[0] >= 16:
            centered = chest.values - np.mean(chest.values, axis=0)
            f, pxx = signal.welch(centered, fs=chest.sample_rate_hz, nperseg=min(128, len(centered)), axis=0)
            pxx_sum = np.sum(pxx, axis=1)
            b_mask = (f >= 2.0) & (f <= 6.0)
            tot_mask = (f >= 0.5) & (f <= 20.0)
            tot = np.sum(pxx_sum[tot_mask])
            ser = float(np.sum(pxx_sum[b_mask]) / tot) if tot > 1e-12 else 0.0
            features.append(ser)
        else:
            features.append(0.0)

        return np.array(features, dtype=float)

    def fit(self, X: np.ndarray, y: Sequence[int]) -> "MHealthActivityClassifier":
        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42, n_jobs=-1)),
        ])
        self.model.fit(X, np.asarray(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict_proba")
        return self.model.predict_proba(X)

    def save(self, path: Union[str, Path]) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "provenance": self.DATASET_PROVENANCE}, p)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "MHealthActivityClassifier":
        data = joblib.load(path)
        return cls(model=data["model"])


# ---------------------------------------------------------------------------
# 3. UCI HAR Smartphone Inertial Activity Classifier
# ---------------------------------------------------------------------------

class UciHarActivityClassifier:
    """Trained classifier for UCI HAR tri-axial accelerometer and gyroscope windows."""

    DATASET_PROVENANCE = "UCI Human Activity Recognition Using Smartphones (128-sample windows)"
    ACTIVITY_NAMES = {
        1: "WALKING",
        2: "WALKING_UPSTAIRS",
        3: "WALKING_DOWNSTAIRS",
        4: "SITTING",
        5: "STANDING",
        6: "LAYING",
    }

    def __init__(self, model: Optional[Pipeline] = None):
        self.model = model

    @staticmethod
    def extract_window_features(window: DatasetWindow) -> np.ndarray:
        """Extract multi-axis kinematic descriptors from 128-sample inertial signal arrays."""
        features = []
        for name in ("body_accel", "body_gyro"):
            rec = window.signal(name)
            if rec is not None:
                vals = rec.values  # (128, 3)
                mean = np.mean(vals, axis=0)
                std = np.std(vals, axis=0)
                rms = np.sqrt(np.mean(vals ** 2, axis=0))
                p2p = np.ptp(vals, axis=0)
                features.extend(mean.tolist())
                features.extend(std.tolist())
                features.extend(rms.tolist())
                features.extend(p2p.tolist())
                # Magnitude channel
                mag = np.sqrt(np.sum(vals ** 2, axis=1))
                features.extend([float(np.mean(mag)), float(np.std(mag)), float(np.max(mag))])
            else:
                features.extend([0.0] * 15)

        return np.array(features, dtype=float)

    def fit(self, X: np.ndarray, y: Sequence[int]) -> "UciHarActivityClassifier":
        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42, n_jobs=-1)),
        ])
        self.model.fit(X, np.asarray(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict_proba")
        return self.model.predict_proba(X)

    def save(self, path: Union[str, Path]) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "provenance": self.DATASET_PROVENANCE}, p)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "UciHarActivityClassifier":
        data = joblib.load(path)
        return cls(model=data["model"])


# ---------------------------------------------------------------------------
# 4. PhysDrive Physiological Stability & Quality Model
# ---------------------------------------------------------------------------

class PhysDriveQualityModel:
    """Trained model estimating heart-rate stability and physiological signal quality."""

    DATASET_PROVENANCE = "PhysDrive In-Cabin Multimodal Physiology Benchmark"

    def __init__(self, model: Optional[Pipeline] = None):
        self.model = model

    @staticmethod
    def extract_trajectory_features(hr_window: np.ndarray) -> np.ndarray:
        """
        Extract dynamic stability features over a 100-sample (10s) heart rate window:
          - Mean HR, Standard deviation (HRV proxy)
          - Successive difference RMSSD
          - Slope / acceleration of HR trajectory
          - Min and Max heart rate bounds
        """
        arr = np.asarray(hr_window, dtype=float)
        if len(arr) < 2:
            return np.zeros(6, dtype=float)
        mean_hr = float(np.mean(arr))
        std_hr = float(np.std(arr))
        diffs = np.diff(arr)
        rmssd = float(np.sqrt(np.mean(diffs ** 2))) if len(diffs) > 0 else 0.0
        slope = float((arr[-1] - arr[0]) / len(arr))
        return np.array([mean_hr, std_hr, rmssd, slope, float(np.min(arr)), float(np.max(arr))])

    def fit(self, X: np.ndarray, y: Sequence[int]) -> "PhysDriveQualityModel":
        """
        Train classifier for physiological state:
          0: Stable Baseline (normocardia 60-100 BPM, normal HRV)
          1: Bradycardia Episode (<50 BPM)
          2: Tachycardia Episode (>110 BPM)
          3: Unstable / Noise Artifact
        """
        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ])
        self.model.fit(X, np.asarray(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model must be fitted before predict")
        return self.model.predict(X)

    def save(self, path: Union[str, Path]) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "provenance": self.DATASET_PROVENANCE}, p)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "PhysDriveQualityModel":
        data = joblib.load(path)
        return cls(model=data["model"])
