"""PhysDrive dataset adapter for physiological replay experiments.

PhysDrive provides in-vehicle RGB/NIR video, mmWave-derived signals, and
physiological labels, but it does not provide CabinGuard's seatback FSR,
steering grip, or headrest IMU channels. Missing channels are therefore marked
explicitly as neutral or unavailable; they are never treated as measured
medical evidence.

Expected official preprocessed layout (one example session)::

    <root>/RGB and IR (one subject sample)/AMH1/AS/
        Recording_Physiological_Data.csv
        Label/HR.mat
        Label/BVP.mat
        Label/ECG.mat

The adapter uses the CSV first and falls back to Label/HR.mat when a heart-rate
column is unavailable. It is intended for feature-pipeline and data-quality
validation, not clinical event classification.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
from scipy.io import loadmat

from .config import FUSION_DT
from .simulator import SensorFrame, SensorMode


_HEART_RATE_KEYS = (
    "hr", "heart_rate", "heartrate", "heart rate", "hr_bpm", "heart_rate_bpm"
)
_TIMESTAMP_KEYS = ("timestamp", "time", "time_s", "time_sec", "seconds")


@dataclass(frozen=True)
class PhysDriveSession:
    """A discovered PhysDrive physiological recording session."""

    csv_path: Path | None
    label_dir: Path


class PhysDriveAdapter:
    """Replay PhysDrive physiological rows as prototype ``SensorFrame`` objects."""

    def __init__(
        self,
        root: str | Path,
        *,
        sample_rate_hz: float = 1.0 / FUSION_DT,
        require_heart_rate: bool = True,
    ) -> None:
        self.root = Path(root)
        self.sample_rate_hz = float(sample_rate_hz)
        self.require_heart_rate = require_heart_rate
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")

    def discover_sessions(self) -> list[PhysDriveSession]:
        """Find official PhysDrive sessions below ``root``."""
        if not self.root.exists():
            raise FileNotFoundError(f"PhysDrive root does not exist: {self.root}")
        sessions = []
        for csv_path in sorted(self.root.rglob("Recording_Physiological_Data.csv")):
            sessions.append(PhysDriveSession(csv_path, csv_path.parent / "Label"))
        if not sessions:
            for hr_path in sorted(self.root.rglob("HR.mat")):
                sessions.append(PhysDriveSession(None, hr_path.parent))
        if not sessions:
            raise FileNotFoundError(
                f"No Recording_Physiological_Data.csv or Label/HR.mat found below {self.root}"
            )
        return sessions

    def iter_session(self, session: PhysDriveSession) -> Iterator[SensorFrame]:
        """Yield frames for one PhysDrive session."""
        rows = list(self._read_csv_rows(session.csv_path)) if session.csv_path else []
        if not rows and session.csv_path:
            return

        first_row = rows[0] if rows else {}
        hr_key = self._find_key(first_row, _HEART_RATE_KEYS) if rows else None
        time_key = self._find_key(first_row, _TIMESTAMP_KEYS) if rows else None
        hr_values = None
        if hr_key is None:
            hr_values = self._load_mat_signal(session.label_dir / "HR.mat")
            if hr_values is None and self.require_heart_rate:
                source = session.csv_path or session.label_dir
                raise ValueError(f"No heart-rate column or Label/HR.mat in {source}")

        row_count = len(rows) if rows else int(hr_values.size if hr_values is not None else 0)

        for index in range(row_count):
            row = rows[index] if rows else {}
            timestamp = self._numeric(row.get(time_key)) if time_key else None
            if timestamp is None:
                timestamp = index / self.sample_rate_hz

            if hr_key is not None:
                heart_rate = self._numeric(row.get(hr_key))
            else:
                heart_rate = self._value_at(hr_values, index)
            if heart_rate is None or not np.isfinite(heart_rate):
                heart_rate = 74.0

            yield SensorFrame(
                timestamp=float(timestamp),
                mode=SensorMode.NORMAL,
                ear=0.30,
                pitch_deg=0.0,
                optical_snr_db=0.0,
                face_detected=True,
                rppg_hr_bpm=float(max(0.0, heart_rate)),
                # PhysDrive has no headrest IMU. Make that limitation explicit.
                imu_accel_window=np.zeros((100, 3), dtype=float),
                imu_gyro_window=np.zeros((100, 3), dtype=float),
                imu_heartbeat_ok=False,
                # These channels are unavailable in PhysDrive and are neutral only.
                fsr_pressure=0.85,
                wheel_grip="ACTIVE",
                steering_torque_nm=0.0,
                brake_pedal_pressed=False,
            )

    def iter_frames(self) -> Iterator[SensorFrame]:
        """Yield frames from all discovered sessions in deterministic order."""
        for session in self.discover_sessions():
            yield from self.iter_session(session)

    @staticmethod
    def _read_csv_rows(path: Path) -> Iterable[Mapping[str, str]]:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"CSV has no header: {path}")
            yield from reader

    @staticmethod
    def _find_key(row: Mapping[str, str], candidates: Sequence[str]) -> str | None:
        def normalize(value: str) -> str:
            return "_".join(value.strip().lower().replace("-", "_").split())

        normalized = {normalize(key): key for key in row}
        for candidate in candidates:
            key = normalized.get(normalize(candidate))
            if key is not None:
                return key
        for normalized_key, original_key in normalized.items():
            if "heart" in normalized_key and "rate" in normalized_key:
                return original_key
            if normalized_key.startswith("hr_") or normalized_key == "hr":
                return original_key
        return None

    @staticmethod
    def _numeric(value: object) -> float | None:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    @staticmethod
    def _load_mat_signal(path: Path) -> np.ndarray | None:
        if not path.exists():
            return None
        values = loadmat(path)
        arrays = [
            np.asarray(value).squeeze()
            for key, value in values.items()
            if not key.startswith("__") and np.issubdtype(np.asarray(value).dtype, np.number)
        ]
        arrays = [array.reshape(-1) for array in arrays if array.size]
        return arrays[0] if arrays else None

    @staticmethod
    def _value_at(values: np.ndarray | None, index: int) -> float | None:
        if values is None or index >= values.size:
            return None
        try:
            return float(values[index])
        except (TypeError, ValueError):
            return None


__all__ = ["PhysDriveAdapter", "PhysDriveSession"]
