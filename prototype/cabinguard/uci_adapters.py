"""Adapters for the UCI MHEALTH and Human Activity Recognition datasets."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

from .dataset_types import DatasetWindow, SignalRecord, SignalStatus


class MHealthAdapter:
    """Read UCI MHEALTH ``mHealth_subject<N>.log`` files at 50 Hz."""

    SAMPLE_RATE_HZ = 50.0
    COLUMN_NAMES = (
        "chest_acc_x", "chest_acc_y", "chest_acc_z", "chest_ecg_1",
        "chest_ecg_2", "ankle_acc_x", "ankle_acc_y", "ankle_acc_z",
        "ankle_gyro_x", "ankle_gyro_y", "ankle_gyro_z", "ankle_mag_x",
        "ankle_mag_y", "ankle_mag_z", "arm_acc_x", "arm_acc_y", "arm_acc_z",
        "arm_gyro_x", "arm_gyro_y", "arm_gyro_z", "arm_mag_x", "arm_mag_y",
        "arm_mag_z", "activity_label",
    )

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(f"MHEALTH root does not exist: {self.root}")

    def discover_files(self) -> list[Path]:
        files = sorted(self.root.rglob("mHealth_subject*.log"))
        if not files:
            raise FileNotFoundError(f"No mHealth_subject*.log files below {self.root}")
        return files

    def iter_windows(
        self, window_s: float = 2.0, hop_s: float = 1.0
    ) -> Iterator[DatasetWindow]:
        if window_s <= 0 or hop_s <= 0:
            raise ValueError("window_s and hop_s must be positive")
        window = int(round(window_s * self.SAMPLE_RATE_HZ))
        hop = int(round(hop_s * self.SAMPLE_RATE_HZ))
        if window < 1 or hop < 1:
            raise ValueError("window_s and hop_s are too short for 50 Hz data")

        for path in self.discover_files():
            data = np.loadtxt(path, dtype=float)
            if data.ndim == 1:
                data = data.reshape(1, -1)
            if data.shape[1] < len(self.COLUMN_NAMES):
                raise ValueError(
                    f"Expected {len(self.COLUMN_NAMES)} MHEALTH columns in {path}, "
                    f"got {data.shape[1]}"
                )
            subject_id = path.stem.removeprefix("mHealth_subject")
            for start in range(0, data.shape[0] - window + 1, hop):
                block = data[start:start + window, :]
                label_values = block[:, 23].astype(int)
                labels, counts = np.unique(label_values, return_counts=True)
                activity = int(labels[np.argmax(counts)])
                end = start + window
                yield DatasetWindow(
                    dataset_name="UCI-MHEALTH",
                    subject_id=subject_id,
                    session_id=path.stem,
                    start_time_s=start / self.SAMPLE_RATE_HZ,
                    end_time_s=end / self.SAMPLE_RATE_HZ,
                    signals={
                        "chest_accel": SignalRecord(
                            block[:, 0:3], self.SAMPLE_RATE_HZ, "m/s^2",
                            channels=("x", "y", "z"), source_path=path,
                        ),
                        "chest_ecg": SignalRecord(
                            block[:, 3:5], self.SAMPLE_RATE_HZ, "mV",
                            channels=("lead_1", "lead_2"), source_path=path,
                        ),
                        "ankle_accel": SignalRecord(
                            block[:, 5:8], self.SAMPLE_RATE_HZ, "m/s^2",
                            channels=("x", "y", "z"), source_path=path,
                        ),
                        "ankle_gyro": SignalRecord(
                            block[:, 8:11], self.SAMPLE_RATE_HZ, "deg/s",
                            channels=("x", "y", "z"), source_path=path,
                        ),
                        "arm_accel": SignalRecord(
                            block[:, 14:17], self.SAMPLE_RATE_HZ, "m/s^2",
                            channels=("x", "y", "z"), source_path=path,
                        ),
                        "arm_gyro": SignalRecord(
                            block[:, 17:20], self.SAMPLE_RATE_HZ, "deg/s",
                            channels=("x", "y", "z"), source_path=path,
                        ),
                    },
                    labels={"activity_label": activity},
                    metadata={"source_format": "whitespace log", "native_columns": self.COLUMN_NAMES},
                )


class UciHarAdapter:
    """Read standard UCI HAR train/test inertial-signal window files."""

    SAMPLE_RATE_HZ = 50.0
    WINDOW_SAMPLES = 128

    def __init__(self, root: str | Path, split: str = "train"):
        self.root = Path(root)
        self.split = split
        if split not in {"train", "test"}:
            raise ValueError("split must be 'train' or 'test'")
        if not self.root.exists():
            raise FileNotFoundError(f"UCI HAR root does not exist: {self.root}")

    def _find(self, relative: str) -> Path:
        path = self.root / self.split / relative
        if not path.exists():
            raise FileNotFoundError(f"Missing UCI HAR file: {path}")
        return path

    @staticmethod
    def _load_rows(path: Path) -> np.ndarray:
        data = np.loadtxt(path, dtype=float)
        return data.reshape(1, -1) if data.ndim == 1 else data

    def iter_windows(self) -> Iterator[DatasetWindow]:
        signal_root = "Inertial Signals"
        accel_paths = [
            self._find(f"{signal_root}/body_acc_{axis}_{self.split}.txt")
            for axis in ("x", "y", "z")
        ]
        gyro_paths = [
            self._find(f"{signal_root}/body_gyro_{axis}_{self.split}.txt")
            for axis in ("x", "y", "z")
        ]
        accel = np.stack([self._load_rows(path) for path in accel_paths], axis=-1)
        gyro = np.stack([self._load_rows(path) for path in gyro_paths], axis=-1)
        labels = self._load_rows(self._find(f"y_{self.split}.txt")).reshape(-1).astype(int)
        subjects = self._load_rows(self._find(f"subject_{self.split}.txt")).reshape(-1).astype(int)
        if not (len(accel) == len(gyro) == len(labels) == len(subjects)):
            raise ValueError("UCI HAR signal, label, and subject row counts differ")

        for index in range(len(labels)):
            subject_id = str(subjects[index])
            yield DatasetWindow(
                dataset_name="UCI-HAR",
                subject_id=subject_id,
                session_id=f"{self.split}-{index:05d}",
                start_time_s=0.0,
                end_time_s=self.WINDOW_SAMPLES / self.SAMPLE_RATE_HZ,
                signals={
                    "body_accel": SignalRecord(
                        accel[index], self.SAMPLE_RATE_HZ, "normalized_g",
                        channels=("x", "y", "z"),
                        source_path=accel_paths[0],
                    ),
                    "body_gyro": SignalRecord(
                        gyro[index], self.SAMPLE_RATE_HZ, "rad/s",
                        channels=("x", "y", "z"),
                        source_path=gyro_paths[0],
                    ),
                },
                labels={"activity_label": int(labels[index])},
                metadata={
                    "source_format": "UCI HAR inertial window",
                    "window_samples": self.WINDOW_SAMPLES,
                    "split": self.split,
                },
            )
