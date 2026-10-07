"""WFDB adapter for the PhysioNet MIT-BIH Arrhythmia Database."""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np

from .dataset_types import DatasetWindow, SignalRecord


class MitBihAdapter:
    """Read MIT-BIH ECG records locally or directly from PhysioNet.

    The adapter emits ECG windows with dataset-native beat annotation symbols.
    It does not convert arrhythmia labels into syncope or driver-event labels.
    """

    DATASET_NAME = "PhysioNet-MIT-BIH-Arrhythmia"

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        record_names: Sequence[str] = ("100",),
    ) -> None:
        self.root = Path(root) if root is not None else None
        self.record_names = tuple(str(name) for name in record_names)
        if not self.record_names:
            raise ValueError("record_names must contain at least one record")
        if self.root is not None and not self.root.exists():
            raise FileNotFoundError(f"MIT-BIH root does not exist: {self.root}")

    @staticmethod
    def _wfdb():
        try:
            import wfdb
        except ImportError as exc:
            raise ImportError(
                "MIT-BIH support requires wfdb; install the optional ECG dependency"
            ) from exc
        return wfdb

    def discover_records(self) -> list[str]:
        if self.root is None:
            return list(self.record_names)
        records = sorted(path.stem for path in self.root.glob("*.hea"))
        if not records:
            raise FileNotFoundError(f"No MIT-BIH .hea records below {self.root}")
        return records

    def _record_base(self, name: str) -> str:
        return str(self.root / name) if self.root is not None else name

    def iter_windows(
        self,
        window_s: float = 10.0,
        hop_s: float | None = None,
    ) -> Iterator[DatasetWindow]:
        if window_s <= 0:
            raise ValueError("window_s must be positive")
        hop_s = window_s if hop_s is None else hop_s
        if hop_s <= 0:
            raise ValueError("hop_s must be positive")

        wfdb = self._wfdb()
        for record_name in self.discover_records():
            base = self._record_base(record_name)
            record = wfdb.rdrecord(base, pn_dir="mitdb" if self.root is None else None)
            annotation = wfdb.rdann(
                base, "atr", pn_dir="mitdb" if self.root is None else None
            )
            values = np.asarray(record.p_signal, dtype=float)
            if values.ndim == 1:
                values = values[:, None]
            fs = float(record.fs)
            window_samples = int(round(window_s * fs))
            hop_samples = int(round(hop_s * fs))
            if window_samples < 1 or hop_samples < 1:
                raise ValueError("window_s and hop_s are too short for record sampling rate")

            annotation_samples = np.asarray(annotation.sample, dtype=int)
            annotation_symbols = np.asarray(annotation.symbol, dtype=str)
            for start in range(0, values.shape[0] - window_samples + 1, hop_samples):
                end = start + window_samples
                mask = (annotation_samples >= start) & (annotation_samples < end)
                samples = annotation_samples[mask] - start
                symbols = annotation_symbols[mask].tolist()
                source = Path(base + ".dat") if self.root is not None else None
                yield DatasetWindow(
                    dataset_name=self.DATASET_NAME,
                    subject_id=record_name,
                    session_id=record_name,
                    start_time_s=start / fs,
                    end_time_s=end / fs,
                    signals={
                        "ecg": SignalRecord(
                            values[start:end], fs, "mV",
                            channels=tuple(record.sig_name), source_path=source,
                        )
                    },
                    labels={
                        "beat_annotation_samples": samples.tolist(),
                        "beat_annotation_symbols": symbols,
                    },
                    metadata={
                        "source_format": "WFDB",
                        "record_name": record_name,
                        "native_sample_rate_hz": fs,
                        "annotation_extension": "atr",
                    },
                )
