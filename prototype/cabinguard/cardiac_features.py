"""Pulse-rhythm features shared by the real-data experiments and the runtime.

Whatever sensor produces the pulse (ECG R-peaks in the public recordings,
camera rPPG peaks on the vehicle), the detector only sees a sequence of beat
times. Features are computed over a 10 s window ending at time ``t``:

* ``hr_bpm``: 60 divided by the median inter-beat interval, 0 when no pulse;
* ``hr_delta``: ``hr_bpm`` minus the driver's own running baseline, so an
  ictal rise from 70 to 110 bpm is visible even though 110 bpm is normal for
  someone else;
* ``ibi_cv``: coefficient of variation of the inter-beat intervals;
* ``pulse_absent``: fraction of the window not covered by a plausible beat
  interval (an interval longer than ``MAX_IBI_S`` counts as absent pulse).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

WINDOW_S = 10.0
MIN_IBI_S = 0.2       # 300 bpm
MAX_IBI_S = 2.0       # 30 bpm; longer gaps are treated as absent pulse
BASELINE_S = 300.0

FEATURE_NAMES = ("hr_bpm", "hr_delta", "ibi_cv", "pulse_absent")


@dataclass(frozen=True)
class CardiacFeatures:
    hr_bpm: float
    hr_delta: float
    ibi_cv: float
    pulse_absent: float

    def vector(self) -> np.ndarray:
        return np.array([self.hr_bpm, self.hr_delta, self.ibi_cv, self.pulse_absent])


def window_features(beats: np.ndarray, t: float, baseline_bpm: float | None) -> CardiacFeatures:
    """Features of the 10 s window ending at ``t`` from sorted beat times (s)."""
    lo = t - WINDOW_S
    inside = beats[(beats > lo) & (beats <= t)]
    # Coverage: time spanned by consecutive beats with a plausible interval.
    ibis = np.diff(inside)
    good = ibis[(ibis >= MIN_IBI_S) & (ibis <= MAX_IBI_S)]
    covered = float(good.sum())
    if inside.size:
        # Partial intervals at both window edges count when short enough.
        if inside[0] - lo <= MAX_IBI_S:
            covered += inside[0] - lo
        if t - inside[-1] <= MAX_IBI_S:
            covered += t - inside[-1]
    pulse_absent = float(np.clip(1.0 - covered / WINDOW_S, 0.0, 1.0))
    if good.size >= 2:
        hr = 60.0 / float(np.median(good))
        cv = float(np.std(good) / np.mean(good))
    else:
        hr, cv = 0.0, 0.0
    delta = hr - baseline_bpm if (baseline_bpm is not None and hr > 0) else 0.0
    return CardiacFeatures(hr, delta, cv, pulse_absent)


class CardiacFeatureTracker:
    """Streaming version: feed beat times, ask for features every cycle."""

    def __init__(self):
        self.beats: deque[float] = deque()
        self._hr_hist: deque[tuple[float, float]] = deque()

    def add_beat(self, t_beat: float) -> None:
        if not self.beats or t_beat > self.beats[-1]:
            self.beats.append(t_beat)

    def baseline(self) -> float | None:
        return float(np.median([h for _, h in self._hr_hist])) if len(self._hr_hist) >= 10 else None

    def features(self, t: float) -> CardiacFeatures:
        while self.beats and self.beats[0] < t - BASELINE_S:
            self.beats.popleft()
        f = window_features(np.fromiter(self.beats, float), t, self.baseline())
        # Only clean, pulse-present windows update the personal baseline, and
        # only while nothing alarming is happening, so an event cannot drag
        # its own baseline along with it.
        if f.pulse_absent < 0.1 and f.hr_bpm > 0 and abs(f.hr_delta) < 20:
            self._hr_hist.append((t, f.hr_bpm))
        while self._hr_hist and self._hr_hist[0][0] < t - BASELINE_S:
            self._hr_hist.popleft()
        return f


def features_for_record(beats: np.ndarray, times: np.ndarray, absent: list[tuple[float, float]] = ()) -> np.ndarray:
    """Batch features at ``times`` for an offline record.

    ``absent`` lists intervals with no perfusing pulse (VF, flutter, asystole);
    beats detected inside them are electrical activity, not pulse, and are
    removed before the features are computed.
    """
    keep = np.ones(beats.size, bool)
    for a, b in absent:
        keep &= ~((beats >= a) & (beats <= b))
    beats = beats[keep]
    tracker = CardiacFeatureTracker()
    out, j = [], 0
    for t in times:
        while j < beats.size and beats[j] <= t:
            tracker.add_beat(float(beats[j]))
            j += 1
        out.append(tracker.features(float(t)).vector())
    return np.array(out)
