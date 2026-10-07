"""Optional trained classifier compatible with the existing watchdog contract.

This model is a learned baseline for the synthetic CabinGuard feature space. It
is intentionally separate from ``BayesianEtiologyClassifier`` and must not be
presented as clinically trained until synchronized real CabinGuard recordings
exist.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .classifier import ClassificationResult
from .feature_extraction import ProcessedFeatures


CLASS_NAMES = ("Normal", "Syncope", "Seizure")


class LearnedEtiologyClassifier:
    """Train/load a probabilistic classifier with the existing classifier API."""

    def __init__(self, model: Pipeline | None = None):
        self.model = model

    @staticmethod
    def feature_names() -> tuple[str, ...]:
        return (
            "ear", "pitch_deg", "rppg_hr_bpm", "ser_2_6hz", "psi",
            "grip_active", "grip_disengaged", "grip_clenched", "tonic_detected",
        )

    @classmethod
    def vectorize(cls, feature: ProcessedFeatures) -> np.ndarray:
        grip = feature.wheel_grip.upper()
        return np.array([
            feature.ear,
            feature.pitch_deg,
            feature.rppg_hr_bpm,
            feature.ser_2_6hz,
            feature.psi,
            float(grip == "ACTIVE"),
            float(grip == "DISENGAGED"),
            float(grip == "CLENCHED"),
            float(feature.tonic_detected),
        ], dtype=float)

    def fit(self, features: np.ndarray, labels: Sequence[str]) -> "LearnedEtiologyClassifier":
        labels_array = np.asarray(labels)
        unknown = set(labels_array.tolist()) - set(CLASS_NAMES)
        if unknown:
            raise ValueError(f"Unsupported etiology labels: {sorted(unknown)}")
        self.model = Pipeline([
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(
                max_iter=1000,
                random_state=42,
            )),
        ])
        self.model.fit(np.asarray(features, dtype=float), labels_array)
        return self

    def save(self, path: str | Path) -> None:
        if self.model is None:
            raise RuntimeError("Cannot save an untrained learned classifier")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, destination)

    @classmethod
    def load(cls, path: str | Path) -> "LearnedEtiologyClassifier":
        return cls(model=joblib.load(path))

    def classify(
        self,
        feat: ProcessedFeatures,
        degraded_mode_1: bool = False,
        degraded_mode_2: bool = False,
    ) -> ClassificationResult:
        del degraded_mode_1, degraded_mode_2
        if self.model is None:
            raise RuntimeError("LearnedEtiologyClassifier must be fitted or loaded first")
        probabilities = self.model.predict_proba(self.vectorize(feat).reshape(1, -1))[0]
        classes = self.model.named_steps["classifier"].classes_
        posteriors = {name: 0.0 for name in CLASS_NAMES}
        for name, probability in zip(classes, probabilities):
            posteriors[str(name)] = float(probability)
        predicted_class = max(posteriors, key=posteriors.get)
        top_confidence = posteriors[predicted_class]
        entropy = max(
            0.0,
            -sum(prob * np.log2(prob + 1e-12) for prob in posteriors.values()),
        )
        return ClassificationResult(
            posteriors=posteriors,
            predicted_class=predicted_class,
            top_confidence=top_confidence,
            shannon_entropy=float(entropy),
            is_confident=top_confidence >= 0.85,
        )
