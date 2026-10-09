"""Bounded-evidence multimodal fusion of four sensing branches.

Branches and where their likelihoods come from:

* ``cardiac`` (camera rPPG pulse rhythm): logistic regression trained on
  PhysioNet recordings (``models/cardiac_branch.joblib``);
* ``motion`` (headrest IMU): gradient-boosted trees trained on recorded motion
  only: UEA Epilepsy seizure mimics against driving, everyday activities and
  the mimics' own non-seizure series (``models/motion_branch.joblib``);
* ``vision`` (camera EAR and head pitch) and ``posture`` (seatback FSR and
  wheel grip): expert-set class-conditional densities, to be refitted on
  Phase 2 recordings.

A discriminative branch model's posterior is turned into a likelihood ratio by
dividing out its training prior. Each branch's log-likelihood ratio against
Normal is bounded above by ``c`` (shifting both event classes together, so
the branch's syncope-versus-seizure preference survives) and below by ``-c``,
before the branches are summed with the operational prior. With prior log-odds ``l0`` and decision threshold
``Gamma``, any ``c`` with ``l0 + c < logit(Gamma) < l0 + 2c`` means one branch
alone can never reach ``Gamma`` and two agreeing branches can. Missing
branches (failed or stale sensors) contribute nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np

from . import config
from .cardiac_features import CardiacFeatures
from .motion_features import MotionFeatures

CLASSES = ("Normal", "Syncope", "Seizure")
# Physical sensor behind each branch: the camera feeds two branches, so two
# camera branches agreeing is still one sensor's word.
SENSOR_OF = {"cardiac": "camera", "vision": "camera", "motion": "imu", "posture": "seat"}
CORROBORATION_LLR = 1.0
PRIORS = {"Normal": 0.80, "Syncope": 0.10, "Seizure": 0.10}
MODELS = Path(__file__).resolve().parents[1] / "models"


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


# Cap that satisfies the single-branch / two-branch condition for Gamma = 0.85
# and the priors above: l0 = ln(0.1/0.8) = -2.08, logit(0.85) = 1.73, so the
# admissible interval is (1.91, 3.81); 3.0 sits inside it with margin.
BRANCH_CAP = 3.0
assert _logit(config.CONFIDENCE_THRESHOLD_GAMMA) > math.log(PRIORS["Seizure"] / PRIORS["Normal"]) + BRANCH_CAP
assert _logit(config.CONFIDENCE_THRESHOLD_GAMMA) < math.log(PRIORS["Seizure"] / PRIORS["Normal"]) + 2 * BRANCH_CAP


# Expert-set densities (mean, sd) for the camera-geometry and seat channels.
VISION = {
    "ear": {"Normal": (0.30, 0.06), "Syncope": (0.08, 0.05), "Seizure": (0.17, 0.08)},
    "pitch_deg": {"Normal": (0.0, 8.0), "Syncope": (-30.0, 10.0), "Seizure": (0.0, 14.0)},
}
POSTURE_PSI = {"Normal": (0.15, 0.10), "Syncope": (0.80, 0.12), "Seizure": (0.40, 0.15)}
GRIP = {
    "Normal": {"ACTIVE": 0.90, "DISENGAGED": 0.08, "CLENCHED": 0.02},
    "Syncope": {"ACTIVE": 0.05, "DISENGAGED": 0.93, "CLENCHED": 0.02},
    "Seizure": {"ACTIVE": 0.10, "DISENGAGED": 0.15, "CLENCHED": 0.75},
}


@dataclass
class FusionInput:
    cardiac: CardiacFeatures | None = None
    motion: MotionFeatures | None = None
    ear: float | None = None
    pitch_deg: float | None = None
    psi: float | None = None
    grip: str | None = None


@dataclass
class FusionResult:
    posteriors: dict
    predicted_class: str
    top_confidence: float
    shannon_entropy: float
    branch_llr: dict = field(default_factory=dict)

    @property
    def branches_used(self) -> list[str]:
        return list(self.branch_llr)

    @property
    def is_confident(self) -> bool:
        return self.top_confidence >= config.CONFIDENCE_THRESHOLD_GAMMA

    def corroborating_sensors(self, cls: str | None = None) -> set[str]:
        """Physical sensors whose evidence favours ``cls`` over Normal by e^1 or more."""
        cls = cls or self.predicted_class
        return {SENSOR_OF[b] for b, llr in self.branch_llr.items() if llr.get(cls, 0.0) >= CORROBORATION_LLR}


class FusionClassifier:
    def __init__(self, cardiac_model=None, motion_model=None, cap: float = BRANCH_CAP,
                 enabled: tuple[str, ...] = ("cardiac", "motion", "vision", "posture")):
        self.cardiac = cardiac_model if cardiac_model is not None else _load("cardiac_branch.joblib")
        self.motion = motion_model if motion_model is not None else _load("motion_branch.joblib")
        self.cap = cap
        self.enabled = set(enabled)

    # Each branch returns an (n, 3) array of log p(x|C) - log p(x|Normal),
    # columns in CLASSES order. The runtime calls these with n = 1.
    def _cardiac_llr(self, X: np.ndarray) -> np.ndarray:
        m = self.cardiac
        p = m["model"].predict_proba(X)
        col = {c: i for i, c in enumerate(m["classes"])}
        prior = m["train_prior"]
        lik = np.stack([p[:, col["Normal"]] / prior["Normal"],
                        p[:, col["Cardiac"]] / prior["Cardiac"],
                        p[:, col["Seizure"]] / prior["Seizure"]], axis=1)
        ll = np.log(np.maximum(lik, 1e-9))
        return ll - ll[:, :1]

    def _motion_llr(self, X: np.ndarray) -> np.ndarray:
        m = self.motion
        p = m["model"].predict_proba(X)[:, 1]
        pi = m["train_prior_clonic"]
        lr = np.log(np.maximum(p / pi, 1e-9)) - np.log(np.maximum((1 - p) / (1 - pi), 1e-9))
        # The motion branch only separates clonic motion from everything else;
        # it carries no syncope-versus-normal information.
        return np.stack([np.zeros_like(lr), np.zeros_like(lr), lr], axis=1)

    @staticmethod
    def _vision_llr(ear, pitch) -> np.ndarray:
        n = len(ear if ear is not None else pitch)
        ll = np.zeros((n, 3))
        for name, x in (("ear", ear), ("pitch_deg", pitch)):
            if x is None:
                continue
            x = np.asarray(x, float)
            for i, c in enumerate(CLASSES):
                mu, sd = VISION[name][c]
                ll[:, i] += -0.5 * np.log(2 * np.pi * sd * sd) - (x - mu) ** 2 / (2 * sd * sd)
        return ll - ll[:, :1]

    @staticmethod
    def _posture_llr(psi, grip) -> np.ndarray:
        n = len(psi if psi is not None else grip)
        ll = np.zeros((n, 3))
        for i, c in enumerate(CLASSES):
            if psi is not None:
                mu, sd = POSTURE_PSI[c]
                x = np.asarray(psi, float)
                ll[:, i] += -0.5 * np.log(2 * np.pi * sd * sd) - (x - mu) ** 2 / (2 * sd * sd)
            if grip is not None:
                ll[:, i] += np.log([GRIP[c].get(str(g), 0.01) for g in grip])
        return ll - ll[:, :1]

    def batch_evidence(self, cardiac=None, motion=None, ear=None, pitch=None, psi=None, grip=None) -> dict:
        """Clipped per-branch evidence for arrays of inputs (None = branch unavailable)."""
        ev = {}
        if "cardiac" in self.enabled and cardiac is not None and self.cardiac is not None:
            ev["cardiac"] = self._cardiac_llr(np.asarray(cardiac, float))
        if "motion" in self.enabled and motion is not None and self.motion is not None:
            ev["motion"] = self._motion_llr(np.asarray(motion, float))
        if "vision" in self.enabled and (ear is not None or pitch is not None):
            ev["vision"] = self._vision_llr(ear, pitch)
        if "posture" in self.enabled and (psi is not None or grip is not None):
            ev["posture"] = self._posture_llr(psi, grip)
        return {b: self._bound(v) for b, v in ev.items()}

    def _bound(self, v: np.ndarray) -> np.ndarray:
        """Limit a branch's evidence for any event over Normal to ``cap``.

        Both event columns are shifted down by the same excess, so the branch
        still says which event it favours; clipping each column on its own
        would let a saturated branch vote equally for syncope and seizure.
        """
        v = v.copy()
        excess = np.maximum(0.0, v[:, 1:].max(axis=1) - self.cap)
        v[:, 1:] -= excess[:, None]
        return np.maximum(v, -self.cap)

    @staticmethod
    def combine(ev: dict, n: int):
        """Posteriors (n, 3) and per-class count of corroborating sensors (n, 3)."""
        logp = np.tile(np.log([PRIORS[c] for c in CLASSES]), (n, 1))
        sensors = {}
        for b, v in ev.items():
            logp = logp + v
            s = SENSOR_OF[b]
            sensors[s] = sensors.get(s, np.zeros((n, 3), bool)) | (v >= CORROBORATION_LLR)
        logp -= logp.max(axis=1, keepdims=True)
        post = np.exp(logp)
        post /= post.sum(axis=1, keepdims=True)
        corro = sum(sensors.values()) if sensors else np.zeros((n, 3), int)
        return post, np.asarray(corro, int)

    def classify(self, x: FusionInput) -> FusionResult:
        ev = self.batch_evidence(
            cardiac=None if x.cardiac is None else x.cardiac.vector()[None],
            motion=None if x.motion is None else x.motion.vector()[None],
            ear=None if x.ear is None else [x.ear], pitch=None if x.pitch_deg is None else [x.pitch_deg],
            psi=None if x.psi is None else [x.psi], grip=None if x.grip is None else [x.grip])
        post, _ = self.combine(ev, 1)
        posteriors = dict(zip(CLASSES, map(float, post[0])))
        top = max(posteriors, key=posteriors.get)
        ent = -sum(p * math.log2(p) for p in posteriors.values() if p > 0)
        llr = {b: dict(zip(CLASSES, map(float, v[0]))) for b, v in ev.items()}
        return FusionResult(posteriors, top, posteriors[top], ent, llr)


def _load(name: str):
    path = MODELS / name
    return joblib.load(path) if path.exists() else None
