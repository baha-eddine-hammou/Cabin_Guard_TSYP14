"""Inertial features for clonic-motion detection, shared by runtime and experiments.

Input is a tri-axial acceleration window in units of g. Each axis is
detrended, the per-axis Welch power spectra are summed, and six features are
read off the spectrum and the autocorrelation:

* ``ser``: share of 0.5-20 Hz power that falls in the 2-6 Hz band;
* ``band_rms_g``: RMS acceleration in the 2-6 Hz band (an absolute gate: a
  nearly still body has a noisy ratio but no energy);
* ``peak_hz``: frequency of the largest spectral peak in 0.5-20 Hz;
* ``total_rms_g``: RMS acceleration over 0.5-20 Hz;
* ``rhythmicity``: largest normalised autocorrelation at lags of 0.15-0.5 s
  (2-6.7 Hz periods), power-weighted across axes. Clonic jerks repeat; road
  vibration is broadband and does not;
* ``peakiness``: peak over mean of the 2-6 Hz spectrum.

The motion branch sees every window through ``branch_features``: a causal
fourth-order Butterworth low-pass at ``BRANCH_LOWPASS_HZ`` first, so that the
training recordings (sampled at 16, 25, 50 and 100 Hz) and the 100 Hz headrest
sensor present the same bandwidth; the clonic band, 2-6 Hz, loses at most
1.1 dB.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

G = 9.80665
BAND = (2.0, 6.0)
TOTAL = (0.5, 20.0)
BRANCH_LOWPASS_HZ = 7.0
FEATURE_NAMES = ("ser", "log_band_rms", "peak_hz", "log_total_rms", "rhythmicity", "peakiness")


@dataclass(frozen=True)
class MotionFeatures:
    ser: float
    band_rms_g: float
    peak_hz: float
    total_rms_g: float
    rhythmicity: float = 0.0
    peakiness: float = 0.0

    def vector(self) -> np.ndarray:
        return np.array([self.ser, np.log10(self.band_rms_g + 1e-4), self.peak_hz,
                         np.log10(self.total_rms_g + 1e-4), self.rhythmicity, self.peakiness])


EMPTY = MotionFeatures(0.0, 0.0, 0.0, 0.0)


def _rhythmicity(x: np.ndarray, fs: float) -> float:
    lags = np.arange(int(0.15 * fs), int(0.5 * fs) + 1)
    num, den = 0.0, 0.0
    for col in x.T:
        e = float(np.dot(col, col))
        if e <= 1e-12 or col.size <= lags[-1] + 1:
            continue
        r = max(float(np.dot(col[:-k], col[k:])) / e for k in lags)
        num += e * r
        den += e
    return num / den if den else 0.0


def motion_features(acc_g: np.ndarray, fs: float) -> MotionFeatures:
    """Features of one window, ``acc_g`` shaped (n, 3) in g."""
    if acc_g is None or len(acc_g) < int(fs) or not np.any(acc_g):
        return EMPTY
    x = signal.detrend(np.asarray(acc_g, float), axis=0)
    nperseg = min(len(x), int(2 * fs))
    f, pxx = signal.welch(x, fs=fs, nperseg=nperseg, axis=0)
    psd = pxx.sum(axis=1)
    df = f[1] - f[0]
    tot = (f >= TOTAL[0]) & (f <= TOTAL[1])
    band = (f >= BAND[0]) & (f <= BAND[1])
    p_tot = float(psd[tot].sum() * df)
    if p_tot <= 1e-12:
        return EMPTY
    p_band = float(psd[band].sum() * df)
    peak = float(f[tot][np.argmax(psd[tot])])
    peakiness = float(psd[band].max() / (psd[band].mean() + 1e-18))
    return MotionFeatures(p_band / p_tot, float(np.sqrt(p_band)), peak, float(np.sqrt(p_tot)),
                          _rhythmicity(x, fs), peakiness)


def clonic_waveform(duration_s: float, fs: float, amplitude_g: float, sp0_s: float,
                    sp_growth: float, rng: np.random.Generator, discharge_s: float = 0.2) -> np.ndarray:
    """Acceleration of a clonic jerk train, after Conradsen et al. (2013).

    Each discharge lasts ``discharge_s`` and is followed by a silent period
    that grows exponentially, ``sp_k = sp0 * exp(sp_growth * k)``. A jerk is
    modelled as one full sine cycle of acceleration (net velocity change zero)
    along a random direction that stays roughly constant within a seizure.
    """
    n = int(duration_s * fs)
    out = np.zeros((n, 3))
    direction = rng.normal(size=3)
    direction /= np.linalg.norm(direction)
    t, k = 0.0, 0
    m = int(discharge_s * fs)
    pulse = np.sin(2 * np.pi * np.arange(m) / m)
    while t < duration_s:
        i = int(t * fs)
        seg = pulse[: max(0, min(m, n - i))]
        d = direction + rng.normal(scale=0.15, size=3)
        out[i:i + seg.size] += amplitude_g * rng.uniform(0.8, 1.2) * np.outer(seg, d / np.linalg.norm(d))
        t += discharge_s + sp0_s * np.exp(sp_growth * k)
        k += 1
    return out


def lowpass(acc_g: np.ndarray, fs: float, cutoff_hz: float = BRANCH_LOWPASS_HZ) -> np.ndarray:
    """Causal low-pass of an (n, 3) window, started from its first sample (no step transient)."""
    x = np.asarray(acc_g, float)
    sos = signal.butter(4, cutoff_hz, fs=fs, output="sos")
    zi = signal.sosfilt_zi(sos)[:, :, None] * x[0][None, None, :]
    return signal.sosfilt(sos, x, axis=0, zi=zi)[0]


def branch_features(acc_g: np.ndarray, fs: float) -> MotionFeatures:
    """Features as the motion branch sees them: low-passed, then ``motion_features``."""
    if acc_g is None or len(acc_g) < int(fs) or not np.any(acc_g):
        return EMPTY
    return motion_features(lowpass(acc_g, fs), fs)


def branch_windows(acc_g: np.ndarray, fs: float, win_s: float = 2.0, step_s: float = 0.5) -> np.ndarray:
    """Branch feature vectors of every ``win_s`` window every ``step_s``, each filtered on its own as at runtime."""
    win, step = int(win_s * fs), int(step_s * fs)
    return np.array([branch_features(acc_g[i:i + win], fs).vector()
                     for i in range(0, len(acc_g) - win + 1, step)]).reshape(-1, len(FEATURE_NAMES))
