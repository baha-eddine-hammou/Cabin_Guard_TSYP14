"""
CabinGuard-ADI: Cross-Sensor Plausibility & Anti-Spoofing Watchdog (Algorithm 1)
Implements ISO 26262 ASIL-D-oriented fault mitigation, optical anti-spoofing,
Degraded Modes 1 & 2, and Seizure-Aware Override Suppression.
"""
from dataclasses import dataclass
from typing import Optional
from .feature_extraction import ProcessedFeatures
from .classifier import BayesianEtiologyClassifier, ClassificationResult
from . import config

@dataclass
class WatchdogDecision:
    operational_mode: str          # "Nominal Mode", "Degraded Mode 1", "Degraded Mode 2"
    active_class: str              # "Normal", "Syncope", "Seizure"
    mrm_trigger_flag: bool         # True when emergency verified
    laser_spoofing_detected: bool  # Interlock flag suppressing false activation
    override_suppressed: bool      # Involuntary clonic spasm blocked from cancelling MRM
    persistence_seconds: float     # Consecutive time candidate >= Gamma
    candidate_class: str           # Current unverified top class
    top_confidence: float          # Posterior confidence of candidate
    shannon_entropy: float         # Predictive uncertainty
    raw_classification: ClassificationResult

class CrossSensorWatchdog:
    """Algorithm 1 runtime implementation executed on every 100 ms fusion cycle."""
    def __init__(self, classifier: Optional[BayesianEtiologyClassifier] = None):
        self.classifier = classifier or BayesianEtiologyClassifier()
        self.t_persist = 0.0
        self.candidate_class = "Normal"
        self.security_event_log = []

    def evaluate(self, feat: ProcessedFeatures) -> WatchdogDecision:
        operational_mode = "Nominal Mode"
        degraded_mode_1 = False
        degraded_mode_2 = False
        laser_spoofing_detected = False
        override_suppressed = False

        # Line 2-5: Optical signal degradation check
        if feat.optical_snr_db < config.MIN_OPTICAL_SNR_DB or not feat.face_detected:
            operational_mode = "Degraded Mode 1"
            degraded_mode_1 = True

        # Line 6-9: Headrest IMU heartbeat check
        if not feat.imu_heartbeat_ok:
            operational_mode = "Degraded Mode 2"
            degraded_mode_2 = True

        # Compute Bayesian classification with active degraded mode flags
        clf_result = self.classifier.classify(
            feat,
            degraded_mode_1=degraded_mode_1,
            degraded_mode_2=degraded_mode_2
        )

        # Line 10-14: Anti-Spoofing Interlock
        # If camera reports cardiac arrest (0 BPM) but driver has active grip and is counter-steering
        if feat.rppg_hr_bpm < 1.0 and feat.wheel_grip == "ACTIVE" and feat.steering_torque_nm > config.SPOOF_HR_MIN_TORQUE_NM:
            laser_spoofing_detected = True
            log_entry = (
                f"[SECURITY EXCEPTION t={feat.timestamp:.2f}s] Optical Laser Spoofing Intercepted: "
                f"rPPG=0 BPM vs Grip=ACTIVE, Torque={feat.steering_torque_nm:.2f} Nm. MRM Suppressed."
            )
            self.security_event_log.append(log_entry)
            self.t_persist = 0.0
            self.candidate_class = "Normal"

            return WatchdogDecision(
                operational_mode=operational_mode,
                active_class="Normal",
                mrm_trigger_flag=False,
                laser_spoofing_detected=True,
                override_suppressed=False,
                persistence_seconds=0.0,
                candidate_class="Normal",
                top_confidence=clf_result.top_confidence,
                shannon_entropy=clf_result.shannon_entropy,
                raw_classification=clf_result
            )

        # Seizure-Aware Override Suppression Check (Clinical Engagement Consultation 3)
        # If driver steering torque > 4.0 Nm occurs during high-frequency motor tremors (SER > 0.65)
        # or clenched grip, it is an involuntary ictal spasm, not conscious driver intent.
        if feat.steering_torque_nm > config.DRIVER_OVERRIDE_TORQUE_NM:
            if feat.ser_2_6hz >= config.SEIZURE_OVERRIDE_SUPPRESSION_SER or feat.wheel_grip == "CLENCHED":
                override_suppressed = True

        # Line 15-23: Confidence & Persistence Timing Verification Window (T_ver = 2.0s)
        current_top_class = clf_result.predicted_class
        current_top_conf = clf_result.top_confidence

        if current_top_conf >= config.CONFIDENCE_THRESHOLD_GAMMA and current_top_class != "Normal":
            if current_top_class == self.candidate_class:
                self.t_persist = min(
                    config.VERIFICATION_DURATION_S,
                    self.t_persist + config.FUSION_DT,
                )
            else:
                self.candidate_class = current_top_class
                self.t_persist = config.FUSION_DT
        else:
            self.candidate_class = current_top_class
            self.t_persist = 0.0

        # Check if persistence duration reaches T_ver
        if self.t_persist >= config.VERIFICATION_DURATION_S:
            active_class = self.candidate_class
            mrm_trigger = (active_class != "Normal")
        else:
            active_class = "Normal"
            mrm_trigger = False

        return WatchdogDecision(
            operational_mode=operational_mode,
            active_class=active_class,
            mrm_trigger_flag=mrm_trigger,
            laser_spoofing_detected=False,
            override_suppressed=override_suppressed,
            persistence_seconds=self.t_persist,
            candidate_class=self.candidate_class,
            top_confidence=current_top_conf,
            shannon_entropy=clf_result.shannon_entropy,
            raw_classification=clf_result
        )
