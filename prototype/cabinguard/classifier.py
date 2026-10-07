"""
CabinGuard-ADI: Bayesian Multi-Etiology Classifier & Uncertainty Quantification
Implements Equation 7 to differentiate Normal Driving, Cardiac Syncope, and Epileptic Seizures.
"""
from dataclasses import dataclass
from typing import Dict, Tuple
import math
import numpy as np
from .feature_extraction import ProcessedFeatures
from . import config

@dataclass
class ClassificationResult:
    posteriors: Dict[str, float]      # {"Normal": p0, "Syncope": p1, "Seizure": p2}
    predicted_class: str             # Top candidate class name
    top_confidence: float            # Max posterior probability
    shannon_entropy: float           # Predictive uncertainty in bits
    is_confident: bool               # top_confidence >= Gamma (0.85)

    @property
    def syncope_posterior(self) -> float:
        return float(self.posteriors.get("Syncope", 0.0))

    @property
    def seizure_posterior(self) -> float:
        return float(self.posteriors.get("Seizure", 0.0))

    @property
    def top_class(self) -> str:
        return self.predicted_class

class BayesianEtiologyClassifier:
    """Multi-modal Bayesian classifier with calibrated clinical distributions."""
    def __init__(self):
        # Operational priors (medical emergencies are rare prior events)
        # Using balanced operational priors for real-time edge decision
        self.priors = {
            "Normal": 0.80,
            "Syncope": 0.10,
            "Seizure": 0.10
        }

    def classify(self, feat: ProcessedFeatures, degraded_mode_1: bool = False, degraded_mode_2: bool = False) -> ClassificationResult:
        """
        Computes posterior probabilities P(C_k | x) via Bayes' Theorem (Eq. 7).
        - degraded_mode_1: Camera blinded -> bypasses vision modalities (relies on IMU + FSR + Grip)
        - degraded_mode_2: IMU disconnected -> bypasses IMU SER (relies on Camera + FSR + Grip)
        """
        log_likelihoods = {}

        for c_name in ["Normal", "Syncope", "Seizure"]:
            log_l = 0.0

            # 1. Vision Modalities (Bypassed in Degraded Mode 1)
            if not degraded_mode_1 and feat.face_detected and feat.optical_snr_db > config.MIN_OPTICAL_SNR_DB:
                log_l += self._log_gauss_pdf(feat.ear, *self._ear_params(c_name))
                log_l += self._log_gauss_pdf(feat.pitch_deg, *self._pitch_params(c_name))
                log_l += self._log_gauss_pdf(feat.rppg_hr_bpm, *self._hr_params(c_name))

            # 2. Headrest IMU Clonic Energy Ratio (Bypassed in Degraded Mode 2)
            if not degraded_mode_2 and feat.imu_heartbeat_ok:
                log_l += self._log_gauss_pdf(feat.ser_2_6hz, *self._ser_params(c_name))

            # 3. Seatback Force Postural Slump Index
            log_l += self._log_gauss_pdf(feat.psi, *self._psi_params(c_name))

            # 4. Capacitive Wheel Grip Status
            log_l += math.log(self._grip_prob(feat.wheel_grip, c_name))

            log_likelihoods[c_name] = log_l

        # Clinical Tonic Phase Pre-filter (Clinical Engagement Dossier)
        # Sustained thoracic pressure saturation + clenched grip provides early evidence for Seizure
        priors = dict(self.priors)
        if getattr(feat, 'tonic_detected', False):
            priors["Seizure"] = 0.65
            priors["Normal"] = 0.30
            priors["Syncope"] = 0.05

        # Compute Bayes denominator via Log-Sum-Exp trick for numerical stability
        log_posteriors = {}
        for c_name in log_likelihoods:
            log_prior = math.log(priors[c_name])
            log_posteriors[c_name] = log_likelihoods[c_name] + log_prior

        max_log = max(log_posteriors.values())
        sum_exp = sum(math.exp(lp - max_log) for lp in log_posteriors.values())
        log_denom = max_log + math.log(sum_exp)

        posteriors = {}
        for c_name in log_posteriors:
            posteriors[c_name] = float(math.exp(log_posteriors[c_name] - log_denom))

        # Top class and uncertainty
        predicted_class = max(posteriors, key=posteriors.get)
        top_confidence = posteriors[predicted_class]

        # Shannon Entropy H(X) = -sum(p * log2(p))
        entropy = max(0.0, -sum(p * math.log2(p + 1e-12) for p in posteriors.values()))

        return ClassificationResult(
            posteriors=posteriors,
            predicted_class=predicted_class,
            top_confidence=top_confidence,
            shannon_entropy=entropy,
            is_confident=(top_confidence >= config.CONFIDENCE_THRESHOLD_GAMMA)
        )

    def _log_gauss_pdf(self, val: float, mean: float, std: float) -> float:
        var = std ** 2
        return -0.5 * math.log(2.0 * math.pi * var) - ((val - mean) ** 2) / (2.0 * var)

    def _ear_params(self, c: str) -> Tuple[float, float]:
        if c == "Normal":   return (0.31, 0.04)
        if c == "Syncope":  return (0.07, 0.03)  # Flaccid ptosis / sustained closure
        return (0.16, 0.06)                     # Seizure flutter

    def _pitch_params(self, c: str) -> Tuple[float, float]:
        if c == "Normal":   return (1.0, 5.0)
        if c == "Syncope":  return (-32.0, 6.0) # Forward cranial slump
        return (2.0, 10.0)                      # Jerking / extension

    def _hr_params(self, c: str) -> Tuple[float, float]:
        if c == "Normal":   return (75.0, 8.0)
        if c == "Syncope":  return (35.0, 7.0)  # Severe asystolic bradycardia
        return (128.0, 10.0)                    # Sympathetic tachycardia

    def _ser_params(self, c: str) -> Tuple[float, float]:
        if c == "Normal":   return (0.10, 0.05)
        if c == "Syncope":  return (0.08, 0.04) # Atonic slump (low vibration)
        return (0.76, 0.07)                     # Concentrated clonic tremor resonance

    def _psi_params(self, c: str) -> Tuple[float, float]:
        if c == "Normal":   return (0.12, 0.05)
        if c == "Syncope":  return (0.86, 0.05) # Torso falls forward away from backrest
        return (0.38, 0.10)                     # Rhythmic rebound

    def _grip_prob(self, grip: str, c: str) -> float:
        probs = {
            "Normal":  {"ACTIVE": 0.94, "DISENGAGED": 0.04, "CLENCHED": 0.02},
            "Syncope": {"ACTIVE": 0.03, "DISENGAGED": 0.95, "CLENCHED": 0.02},
            "Seizure": {"ACTIVE": 0.05, "DISENGAGED": 0.03, "CLENCHED": 0.92}
        }
        return probs[c].get(grip, 0.01)

