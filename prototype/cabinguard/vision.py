"""Camera-side signal processing: rPPG pulse beats, eye aspect ratio, head pitch.

Pure numpy/scipy so it runs and is tested without a camera. On the vehicle,
``CameraFrontEnd`` (in ``cabinguard.hardware``) feeds it face-ROI colour
means and facial landmarks from OpenCV + MediaPipe Face Mesh.

* POS rPPG (Wang et al., IEEE TBME 2017): overlap-added projections of the
  temporally normalised RGB trace onto the plane orthogonal to the skin tone.
* Eye aspect ratio (Soukupova and Cech, CVWW 2016) from six eyelid landmarks.
* Head pitch from three Face Mesh landmarks (forehead, nose tip, chin) as the
  angle of the face's vertical axis out of the image plane; a coarse proxy
  for the PnP solution, adequate to flag forward head drop.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from scipy import signal

POS_WINDOW_S = 1.6
PULSE_BAND_HZ = (0.7, 3.5)
# MediaPipe Face Mesh indices for the six EAR landmarks of each eye.
LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
FOREHEAD, NOSE_TIP, CHIN = 10, 1, 152


def pos_pulse(rgb: np.ndarray, fs: float) -> np.ndarray:
    """POS pulse signal from an (n, 3) array of mean skin RGB values."""
    n = rgb.shape[0]
    w = max(2, int(POS_WINDOW_S * fs))
    h = np.zeros(n)
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for start in range(0, n - w + 1):
        c = rgb[start:start + w].T
        cn = c / (c.mean(axis=1, keepdims=True) + 1e-9)
        s = proj @ cn
        p = s[0] + (s[0].std() / (s[1].std() + 1e-9)) * s[1]
        h[start:start + w] += p - p.mean()
    b, a = signal.butter(2, [PULSE_BAND_HZ[0] / (fs / 2), PULSE_BAND_HZ[1] / (fs / 2)], "bandpass")
    return signal.filtfilt(b, a, h) if n > 3 * max(len(a), len(b)) else h


def pulse_peaks(pulse: np.ndarray, fs: float) -> np.ndarray:
    """Sample indices of pulse peaks, at most one per 0.33 s (180 bpm)."""
    if pulse.size < fs:
        return np.array([], int)
    prom = 0.3 * np.std(pulse)
    peaks, _ = signal.find_peaks(pulse, distance=max(1, int(0.33 * fs)), prominence=prom)
    return peaks


def pulse_snr_db(pulse: np.ndarray, fs: float) -> float:
    """Power within +-0.1 Hz of the spectral peak (and harmonic) vs the rest of 0.7-3.5 Hz."""
    if pulse.size < 2 * fs:
        return -np.inf
    f, p = signal.periodogram(pulse, fs)
    band = (f >= PULSE_BAND_HZ[0]) & (f <= PULSE_BAND_HZ[1])
    if not band.any() or p[band].sum() <= 0:
        return -np.inf
    f0 = f[band][np.argmax(p[band])]
    sig = (np.abs(f - f0) <= 0.1) | (np.abs(f - 2 * f0) <= 0.1)
    s, nz = p[band & sig].sum(), p[band & ~sig].sum()
    return float(10 * np.log10(s / nz)) if nz > 0 else 30.0


def eye_aspect_ratio(pts: np.ndarray) -> float:
    """EAR from six (x, y) landmarks ordered p1..p6."""
    p1, p2, p3, p4, p5, p6 = pts
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2.0 * np.linalg.norm(p1 - p4) + 1e-9))


def head_pitch_deg(forehead: np.ndarray, nose: np.ndarray, chin: np.ndarray) -> float:
    """Pitch from 3-D landmarks (x, y, z); negative when the head drops forward."""
    axis = chin - forehead
    return float(-np.degrees(np.arctan2(axis[2], axis[1])))


class RPPGTracker:
    """Streaming rPPG: push face-ROI colour means, read new beat times."""

    def __init__(self, fs: float, buffer_s: float = 10.0):
        self.fs = fs
        self.buf: deque = deque(maxlen=int(buffer_s * fs))
        self.times: deque = deque(maxlen=int(buffer_s * fs))
        self._last_beat = -np.inf

    def push(self, t: float, rgb_mean: np.ndarray) -> None:
        self.buf.append(np.asarray(rgb_mean, float))
        self.times.append(t)

    def new_beats(self) -> tuple[list[float], float]:
        """Beat times not reported before, plus the current pulse SNR in dB."""
        if len(self.buf) < 3 * self.fs:
            return [], -np.inf
        pulse = pos_pulse(np.array(self.buf), self.fs)
        peaks = pulse_peaks(pulse, self.fs)
        t = np.array(self.times)
        beats = [float(t[i]) for i in peaks if t[i] > self._last_beat and i < len(t) - 2]
        if beats:
            self._last_beat = beats[-1]
        return beats, pulse_snr_db(pulse, self.fs)
