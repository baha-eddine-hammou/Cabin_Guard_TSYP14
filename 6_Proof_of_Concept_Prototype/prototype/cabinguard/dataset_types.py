"""Provenance-aware records shared by real-dataset adapters.

These records deliberately do not force every dataset into CabinGuard's
``SensorFrame``. Dataset-native labels and modalities remain separate so that
activity, ECG, and physiological replay cannot be mistaken for syncope or
seizure evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class SignalStatus(StrEnum):
    """How a signal entered a normalized dataset record."""

    MEASURED = "measured"
    DERIVED = "derived"
    MISSING = "missing"
    IMPUTED = "imputed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SignalRecord:
    """One measured or derived signal and its provenance metadata."""

    values: np.ndarray
    sample_rate_hz: float
    units: str
    status: SignalStatus = SignalStatus.MEASURED
    channels: tuple[str, ...] = ()
    source_path: Path | None = None

    def __post_init__(self) -> None:
        if self.values.ndim == 0:
            raise ValueError("Signal values must be an array with at least one dimension")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")


@dataclass(frozen=True)
class DatasetWindow:
    """A subject/session window with explicit labels and signal availability."""

    dataset_name: str
    subject_id: str
    session_id: str
    start_time_s: float
    end_time_s: float
    signals: Mapping[str, SignalRecord] = field(default_factory=dict)
    labels: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def signal(self, name: str) -> SignalRecord | None:
        return self.signals.get(name)

    @property
    def measured_modalities(self) -> tuple[str, ...]:
        return tuple(
            name for name, signal in self.signals.items()
            if signal.status == SignalStatus.MEASURED
        )

    @property
    def unavailable_modalities(self) -> tuple[str, ...]:
        return tuple(
            name for name, signal in self.signals.items()
            if signal.status in {SignalStatus.MISSING, SignalStatus.NOT_APPLICABLE}
        )
