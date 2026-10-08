"""Per-cycle feature extraction and sensor-health assessment.

Turns one ``SensorSnapshot`` into the inputs of the fusion classifier plus the
health of each physical sensor. A sensor is unavailable when its newest data
is older than ``MAX_SENSOR_AGE_S`` (missing data, a dead bus, a frozen
driver) or when its own quality indicator fails; an unavailable sensor's
branches are simply left out of the fusion.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import config
from .cardiac_features import CardiacFeatureTracker, CardiacFeatures
from .fusion import FusionInput
from .motion_features import MotionFeatures, branch_features, motion_features

MAX_SENSOR_AGE_S = 0.3
IMU_FS = 100.0
PSI_WINDOW = 10            # 1 s of seatback samples at 10 Hz


@dataclass
class CycleFeatures:
    t: float
    fusion: FusionInput
    camera_ok: bool
    imu_ok: bool
    seat_ok: bool
    steering_torque_nm: float
    brake_pedal: bool
    grip: str | None
    cardiac: CardiacFeatures | None
    motion: MotionFeatures | None

    @property
    def sensors_ok(self) -> tuple[str, ...]:
        return tuple(n for n, ok in (("camera", self.camera_ok), ("imu", self.imu_ok),
                                     ("fsr", self.seat_ok), ("grip", self.seat_ok)) if ok)


def deployed_motion_input() -> str:
    """Which features the deployed motion model was trained on: ``branch_features`` (low-passed
    windows) or, for models saved before that key existed, ``motion_features``."""
    from .fusion import _load
    model = _load("motion_branch.joblib")
    return (model or {}).get("input", "motion_features")


class FeatureExtractor:
    def __init__(self, motion_input: str | None = None):
        kind = motion_input or deployed_motion_input()
        self._motion = branch_features if kind == "branch_features" else motion_features
        self.cardiac = CardiacFeatureTracker()
        self.fsr_hist: deque = deque(maxlen=PSI_WINDOW)

    @staticmethod
    def _fresh(t: float, ts: float | None) -> bool:
        return ts is not None and t - ts <= MAX_SENSOR_AGE_S

    def process(self, s) -> CycleFeatures:
        t = s.t
        camera_ok = (self._fresh(t, s.camera_t) and s.face_detected
                     and s.optical_snr_db >= config.MIN_OPTICAL_SNR_DB)
        imu_ok = self._fresh(t, s.imu_t) and s.imu_window_g is not None
        seat_ok = self._fresh(t, s.seat_t) and s.fsr_pressure is not None and s.grip is not None

        for b in s.new_beats:
            self.cardiac.add_beat(b)
        cardiac = self.cardiac.features(t) if camera_ok else None
        motion = self._motion(s.imu_window_g, IMU_FS) if imu_ok else None
        psi = None
        if seat_ok:
            self.fsr_hist.append(s.fsr_pressure)
            psi = float(np.clip(1.0 - np.mean(self.fsr_hist), 0.0, 1.0))
        fusion = FusionInput(
            cardiac=cardiac, motion=motion,
            ear=s.ear if camera_ok else None, pitch_deg=s.pitch_deg if camera_ok else None,
            psi=psi, grip=s.grip if seat_ok else None)
        return CycleFeatures(t, fusion, camera_ok, imu_ok, seat_ok, s.steering_torque_nm,
                             s.brake_pedal, s.grip if seat_ok else None, cardiac, motion)
