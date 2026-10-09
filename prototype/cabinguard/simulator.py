"""Synthetic multimodal cabin signals for demonstrations and regression tests.

The simulator emits exactly what the hardware front ends emit (``SensorSnapshot``):
pulse beat times from the camera, a 100 Hz acceleration window in g from the
headrest IMU, eyelid and head angles, seatback pressure, grip and steering
torque, each with its own timestamp. Physiology follows the same models as
the real-data evaluation:

* syncope: a pulseless ventricular arrhythmia at ``EVENT_ONSET_S``, loss of
  consciousness ``LOC_DELAY_S`` later (head drop, eye closure, hands off);
* seizure: a tonic phase (clenched grip, eyes half open) followed by clonic
  jerks after Conradsen et al. (2013), with ictal tachycardia.

These signals are synthetic. They exercise the software path; they are not
evidence of detection performance, which comes from the PhysioNet experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from . import config
from .motion_features import clonic_waveform

EVENT_ONSET_S = 8.0
LOC_DELAY_S = 7.0
TONIC_S = 8.0
IMU_FS = 100.0
IMU_WINDOW_S = 2.0


class ScenarioType(Enum):
    NORMAL_DRIVING = "Normal driving"
    CARDIAC_SYNCOPE = "Cardiac syncope (pulseless arrhythmia)"
    EPILEPTIC_SEIZURE = "Convulsive seizure (tonic-clonic)"
    OPTICAL_BLINDING_ATTACK = "Optical blinding / spoofed pulse loss"
    IMU_HARDWARE_FAULT = "Headrest IMU disconnect"
    SEAT_SENSOR_STALE = "Seat sensor data stops arriving"


@dataclass
class SensorSnapshot:
    t: float
    # camera
    camera_t: float | None = None
    face_detected: bool = True
    optical_snr_db: float = 10.0
    ear: float | None = None
    pitch_deg: float | None = None
    new_beats: list = field(default_factory=list)
    # headrest IMU (window in g, ending at imu_t)
    imu_t: float | None = None
    imu_window_g: np.ndarray | None = None
    # seat and wheel
    seat_t: float | None = None
    fsr_pressure: float | None = None
    grip: str | None = None
    steering_torque_nm: float = 0.0
    brake_pedal: bool = False
    truth: str = "Normal"


class MultimodalSensorSimulator:
    def __init__(self, scenario: ScenarioType, duration_s: float = 40.0, seed: int = 42):
        self.scenario = scenario
        self.duration_s = duration_s
        self.dt = config.FUSION_DT
        self.rng = np.random.default_rng(seed)
        self.total_steps = int(round(duration_s / self.dt))
        self._beats = self._make_beats()
        self._imu = self._make_imu()
        self._beat_idx = 0
        self.step_idx = 0

    def __len__(self) -> int:
        return self.total_steps

    def __iter__(self):
        self.step_idx = 0
        self._beat_idx = 0
        return self

    def __next__(self) -> SensorSnapshot:
        if self.step_idx >= self.total_steps:
            raise StopIteration
        t = (self.step_idx + 1) * self.dt
        self.step_idx += 1
        return self._snapshot(t)

    # --------------------------------------------------------- signals ---
    def _make_beats(self) -> np.ndarray:
        """Pulse beat times as an rPPG front end would report them."""
        rng, beats, t = self.rng, [], -12.0
        while t < self.duration_s + 1:
            hr = 72.0 + 3.0 * np.sin(2 * np.pi * t / 20.0)
            if self.scenario == ScenarioType.EPILEPTIC_SEIZURE and t >= EVENT_ONSET_S:
                hr = 72.0 + min(1.0, (t - EVENT_ONSET_S) / 10.0) * 50.0      # ictal tachycardia
            if self.scenario == ScenarioType.CARDIAC_SYNCOPE and t >= EVENT_ONSET_S:
                break                                                      # no perfusing pulse
            if self.scenario == ScenarioType.OPTICAL_BLINDING_ATTACK and t >= EVENT_ONSET_S:
                t += 60.0 / hr                                             # pulse exists, camera cannot see it
                continue
            t += 60.0 / hr * (1 + rng.normal(0, 0.03))
            if rng.random() > 0.03:                                        # rPPG misses ~3 % of beats
                beats.append(t + rng.normal(0, 0.02))
        return np.array(beats)

    def _make_imu(self) -> np.ndarray:
        """Road vibration plus event motion, 100 Hz, in g, from t = -2 s."""
        n = int((self.duration_s + IMU_WINDOW_S) * IMU_FS)
        rng = self.rng
        white = rng.normal(0, 1, (n, 3))
        # broadband seat vibration with most energy above 8 Hz, plus slow sway
        k = np.ones(3) / 3
        hf = np.stack([np.convolve(white[:, i], k, "same") for i in range(3)], 1) * 0.03
        tt = np.arange(n) / IMU_FS
        sway = 0.02 * np.stack([np.sin(2 * np.pi * 0.3 * tt), np.cos(2 * np.pi * 0.2 * tt), 0 * tt], 1)
        acc = hf + sway
        on = int((EVENT_ONSET_S + IMU_WINDOW_S) * IMU_FS)
        if self.scenario == ScenarioType.EPILEPTIC_SEIZURE:
            c = on + int(TONIC_S * IMU_FS)
            acc[c:] += clonic_waveform((n - c) / IMU_FS, IMU_FS, 0.3, 0.08, np.log(1 / 0.08) / 40, rng)
        if self.scenario == ScenarioType.CARDIAC_SYNCOPE:
            s = on + int(LOC_DELAY_S * IMU_FS)
            slump = np.exp(-np.arange(int(0.6 * IMU_FS)) / 15.0) * np.sin(np.arange(int(0.6 * IMU_FS)) / 4.0)
            acc[s:s + slump.size, 0] += 0.4 * slump                       # one forward slump transient
        return acc

    # -------------------------------------------------------- snapshot ---
    def _snapshot(self, t: float) -> SensorSnapshot:
        rng, sc = self.rng, self.scenario
        ev = t >= EVENT_ONSET_S
        snap = SensorSnapshot(t=t, camera_t=t, imu_t=t, seat_t=t)
        # camera
        blink = (t % 3.7) < 0.2
        snap.ear = 0.10 if blink else float(rng.normal(0.30, 0.02))
        snap.pitch_deg = float(rng.normal(0.0, 3.0))
        snap.optical_snr_db = float(rng.normal(10.0, 1.0))
        while self._beat_idx < self._beats.size and self._beats[self._beat_idx] <= t:
            snap.new_beats.append(float(self._beats[self._beat_idx]))
            self._beat_idx += 1
        # imu
        end = int((t + IMU_WINDOW_S) * IMU_FS)
        snap.imu_window_g = self._imu[end - int(IMU_WINDOW_S * IMU_FS):end]
        # seat and wheel
        snap.fsr_pressure = float(np.clip(rng.normal(0.85, 0.03), 0, 1))
        snap.grip = "ACTIVE"
        snap.steering_torque_nm = float(rng.normal(0.4, 0.15))

        if sc == ScenarioType.CARDIAC_SYNCOPE and ev:
            snap.truth = "Syncope"
            if t >= EVENT_ONSET_S + LOC_DELAY_S:
                p = min(1.0, (t - EVENT_ONSET_S - LOC_DELAY_S) / 1.5)
                snap.ear = float(0.30 * (1 - p) + 0.06 * p + rng.normal(0, 0.01))
                snap.pitch_deg = float(-32.0 * p + rng.normal(0, 2.0))
                snap.fsr_pressure = float(np.clip(0.85 * (1 - p) + 0.15 * p + rng.normal(0, 0.03), 0, 1))
                snap.grip = "DISENGAGED" if p > 0.4 else "ACTIVE"
                snap.steering_torque_nm = float(abs(rng.normal(0.05, 0.03)))
        elif sc == ScenarioType.EPILEPTIC_SEIZURE and ev:
            snap.truth = "Seizure"
            p = min(1.0, (t - EVENT_ONSET_S) / 1.5)
            snap.ear = float(0.30 * (1 - p) + (0.14 + 0.08 * abs(np.sin(2 * np.pi * 3 * t))) * p)
            snap.pitch_deg = float(12.0 * p * np.sin(2 * np.pi * 3.0 * t) + rng.normal(0, 2.0))
            snap.fsr_pressure = float(np.clip(0.85 - 0.4 * p + 0.1 * np.sin(2 * np.pi * 3.0 * t), 0, 1))
            snap.grip = "CLENCHED" if p > 0.3 else "ACTIVE"
            snap.steering_torque_nm = float(0.4 + 4.5 * p * abs(np.sin(2 * np.pi * 3.0 * t)))
        elif sc == ScenarioType.OPTICAL_BLINDING_ATTACK and ev:
            # A laser saturates the sensor: the face is still found (bright,
            # over-exposed) but the pulse disappears and eyes read as closed.
            snap.optical_snr_db = float(rng.normal(-5.0, 1.0))
            snap.ear = 0.05
            snap.steering_torque_nm = float(2.1 + rng.normal(0, 0.2))
        elif sc == ScenarioType.IMU_HARDWARE_FAULT and ev:
            snap.imu_t = EVENT_ONSET_S                                     # last sample ever received
            snap.imu_window_g = None
        elif sc == ScenarioType.SEAT_SENSOR_STALE and ev:
            snap.seat_t = EVENT_ONSET_S
            snap.fsr_pressure, snap.grip = None, None
        snap.ear = float(np.clip(snap.ear, 0.0, 0.45))
        return snap
