"""Cross-sensor watchdog: degraded modes, anti-spoofing, and the MRM decision.

Every 100 ms cycle:

1. Mode from sensor availability: Nominal; Degraded 1 (camera lost: no rPPG,
   no eyelid or head data); Degraded 2 (IMU lost); Degraded 3, Minimum (fewer
   than two physical sensors), in which no automated manoeuvre may start and
   the driver is warned instead.
2. Contradiction interlock: the camera reporting no pulse or closed eyes
   while the seat and wheel show an upright driver actively steering is
   physically implausible (optical blinding, spoofing, or rPPG failure). The
   camera is distrusted for ``DISTRUST_S`` and the event is logged.
3. Branch evidence is averaged over ``SMOOTH_S`` (brief confounders such as
   a glance down or a pothole fade, sustained events do not) and fused.
4. An MRM is requested when one event class holds posterior >= Gamma for
   ``VERIFICATION_DURATION_S`` with evidence from at least two physical
   sensors.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import config
from .feature_extraction import CycleFeatures
from .fusion import CLASSES, FusionClassifier, FusionResult

SMOOTH_S = 2.0
DISTRUST_S = 10.0
SPOOF_PULSE_ABSENT = 0.8
SPOOF_EAR_CLOSED = 0.12
UPRIGHT_PSI = 0.35
MODES = ("Nominal", "Degraded 1 (camera lost)", "Degraded 2 (IMU lost)", "Degraded 3 (minimum)")


@dataclass
class WatchdogDecision:
    mode: str
    degraded_level: int
    active_class: str
    mrm_trigger_flag: bool
    spoofing_detected: bool
    override_suppressed: bool
    persistence_seconds: float
    candidate_class: str
    top_confidence: float
    shannon_entropy: float
    corroborating_sensors: tuple
    raw: FusionResult

    @property
    def operational_mode(self) -> str:
        return self.mode


class CrossSensorWatchdog:
    def __init__(self, classifier: FusionClassifier | None = None, smooth_s: float = SMOOTH_S):
        self.classifier = classifier or FusionClassifier()
        self.window = max(1, int(round(smooth_s / config.FUSION_DT)))
        self.hist: dict[str, deque] = {}
        self.t_persist = 0.0
        self.candidate = "Normal"
        self.distrust_camera_until = -1.0
        self.security_log: list[str] = []

    def _spoof_check(self, f: CycleFeatures) -> bool:
        if not f.camera_ok or not f.seat_ok:
            return False
        camera_says_down = ((f.cardiac is not None and f.cardiac.pulse_absent >= SPOOF_PULSE_ABSENT)
                            or (f.fusion.ear is not None and f.fusion.ear <= SPOOF_EAR_CLOSED
                                and f.fusion.pitch_deg is not None and f.fusion.pitch_deg > -10))
        seat_says_driving = (f.grip == "ACTIVE" and abs(f.steering_torque_nm) > config.SPOOF_HR_MIN_TORQUE_NM
                             and f.fusion.psi is not None and f.fusion.psi < UPRIGHT_PSI)
        return camera_says_down and seat_says_driving

    def evaluate(self, f: CycleFeatures) -> WatchdogDecision:
        spoof = self._spoof_check(f)
        if spoof:
            if f.t >= self.distrust_camera_until:
                self.security_log.append(
                    f"t={f.t:.1f}s camera contradicts seat and wheel (no pulse or closed eyes while steering "
                    f"{f.steering_torque_nm:.1f} Nm upright); camera distrusted for {DISTRUST_S:.0f} s")
            self.distrust_camera_until = f.t + DISTRUST_S
        camera_ok = f.camera_ok and f.t >= self.distrust_camera_until
        sensors = [n for n, ok in (("camera", camera_ok), ("imu", f.imu_ok), ("seat", f.seat_ok)) if ok]
        if len(sensors) < 2:
            level = 3
        elif not camera_ok:
            level = 1
        elif not f.imu_ok:
            level = 2
        else:
            level = 0

        x = f.fusion
        if not camera_ok:
            x = type(x)(cardiac=None, motion=x.motion, ear=None, pitch_deg=None, psi=x.psi, grip=x.grip)
        clf = self.classifier
        ev = clf.batch_evidence(
            cardiac=None if x.cardiac is None else x.cardiac.vector()[None],
            motion=None if x.motion is None else x.motion.vector()[None],
            ear=None if x.ear is None else [x.ear], pitch=None if x.pitch_deg is None else [x.pitch_deg],
            psi=None if x.psi is None else [x.psi], grip=None if x.grip is None else [x.grip])
        # Smooth each branch over the recent window; a branch that drops out
        # loses its history so stale evidence cannot linger.
        for b in list(self.hist):
            if b not in ev:
                del self.hist[b]
        smoothed = {}
        for b, v in ev.items():
            h = self.hist.setdefault(b, deque(maxlen=self.window))
            h.append(v[0])
            smoothed[b] = np.mean(h, axis=0)[None]
        post, corro = clf.combine(smoothed, 1)
        k = int(post[0].argmax())
        top, conf = CLASSES[k], float(post[0, k])
        n_sensors = int(corro[0, k])
        result = FusionResult(dict(zip(CLASSES, map(float, post[0]))), top, conf,
                              float(-sum(p * np.log2(p) for p in post[0] if p > 0)),
                              {b: dict(zip(CLASSES, map(float, v[0]))) for b, v in smoothed.items()})
        corroborating = tuple(sorted(result.corroborating_sensors(top)))

        qualifies = top != "Normal" and conf >= config.CONFIDENCE_THRESHOLD_GAMMA and n_sensors >= 2 and level < 3
        if qualifies and top == self.candidate:
            self.t_persist = min(config.VERIFICATION_DURATION_S, self.t_persist + config.FUSION_DT)
        elif qualifies:
            self.candidate, self.t_persist = top, config.FUSION_DT
        else:
            self.candidate, self.t_persist = "Normal", 0.0
        trigger = self.t_persist >= config.VERIFICATION_DURATION_S - 1e-9
        active = self.candidate if trigger else "Normal"

        # An involuntary clonic jerk or a clenched grip must not count as the
        # driver taking the wheel back.
        seizure_motion = "motion" in smoothed and smoothed["motion"][0, CLASSES.index("Seizure")] >= 1.0
        suppress = abs(f.steering_torque_nm) > config.DRIVER_OVERRIDE_TORQUE_NM and (seizure_motion or f.grip == "CLENCHED")
        return WatchdogDecision(MODES[level], level, active, trigger, spoof, suppress, self.t_persist,
                                self.candidate, conf, result.shannon_entropy, corroborating, result)
