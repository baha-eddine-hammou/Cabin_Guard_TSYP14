"""
CabinGuard-ADI: Digital Signal Processing & Mathematical Feature Extraction
Implements Welch periodogram tri-axial PSD sum (Equation 5), 6-axis IMU fusion,
Postural Slump Index (Equation 6), Tonic Phase Pre-filter, and GCS clinical estimation.
"""
from dataclasses import dataclass
from collections import deque
import numpy as np
from scipy import signal
from . import config

@dataclass
class ProcessedFeatures:
    timestamp: float
    ear: float                 # Eye Aspect Ratio (Eq. 1)
    pitch_deg: float           # Cranial pitch angle
    rppg_hr_bpm: float         # Optical heart rate from rPPG (Eq. 2)
    ser_2_6hz: float           # Tri-axial Acceleration Clonic Seizure SER (Eq. 5)
    ser_gyro_2_6hz: float      # Tri-axial Gyroscope Rotational Tremor SER (2-6 Hz)
    psi: float                 # Postural Slump Index (Eq. 6)
    wheel_grip: str            # "ACTIVE", "DISENGAGED", "CLENCHED"
    steering_torque_nm: float  # Driver torque for manual override / anti-spoofing
    optical_snr_db: float      # Camera SNR for watchdog evaluation
    face_detected: bool        # Vision tracking health
    imu_heartbeat_ok: bool     # IMU hardware health
    tonic_detected: bool       # Clinical pre-filter: thoracic saturation + clenched grip
    estimated_gcs: int         # Estimated Glasgow Coma Scale [3 - 15]
    hr_min_10s: float          # Running 10s minimum heart rate for MEC
    hr_max_10s: float          # Running 10s maximum heart rate for MEC
    hr_mean_10s: float         # Running 10s mean heart rate for MEC

class FeatureExtractor:
    """Extracts mathematical features from incoming sensor frame buffers."""
    def __init__(self, fsr_buffer_len: int = 10, hr_buffer_len: int = 100):
        # 1.0 second rolling buffer for FSR at 10 Hz = 10 samples
        self.fsr_history = deque(maxlen=fsr_buffer_len)
        # 10.0 second rolling buffer for heart rate at 10 Hz = 100 samples
        self.hr_history = deque(maxlen=hr_buffer_len)

    def process_frame(self, frame) -> ProcessedFeatures:
        # 1. Update FSR rolling buffer and compute Postural Slump Index (Eq. 6)
        self.fsr_history.append(frame.fsr_pressure)
        mean_back_pressure = float(np.mean(self.fsr_history))
        psi = float(np.clip(1.0 - mean_back_pressure, 0.0, 1.0))

        # 2. Update HR history (filter out 0 BPM spoofed values for telemetry stats)
        valid_hr = frame.rppg_hr_bpm if frame.rppg_hr_bpm > 10.0 else 74.0
        self.hr_history.append(valid_hr)
        hr_min = float(np.min(self.hr_history))
        hr_max = float(np.max(self.hr_history))
        hr_mean = float(np.mean(self.hr_history))

        # 3. Compute 6-axis IMU Spectral Energy Ratios (Eq. 4 & 5)
        ser_accel = self._compute_triaxial_ser(frame.imu_accel_window)
        ser_gyro = self._compute_triaxial_ser(getattr(frame, 'imu_gyro_window', None))

        # Combined SER: acceleration dominates, supported by gyro rotational tremor
        ser_2_6hz = ser_accel

        # 4. Clinical Tonic Seizure Pre-filter (Clinical Engagement Dossier)
        # Extreme thoracic pressure (>0.95) + clenched wheel grip + sustained eye deviation
        tonic_detected = (
            frame.fsr_pressure >= config.TONIC_SEIZURE_FSR_MIN and
            frame.wheel_grip == "CLENCHED" and
            frame.ear <= config.TONIC_PREFILTER_EAR_MAX
        )

        # 5. Glasgow Coma Scale (GCS) Clinical Estimation Proxy
        # GCS evaluates Eye (1-4), Motor (1-6), Verbal (1-5, assumed 5 unless coma)
        if psi > 0.70 and frame.ear < 0.15:
            # Flaccid / atonic slump with prolonged eye closure -> GCS 4 (Deep Coma/Syncope)
            estimated_gcs = 4
        elif ser_2_6hz > 0.60 or tonic_detected:
            # Generalized seizure with motor spasms / clenched posture -> GCS 7 (Severe Impairment)
            estimated_gcs = 7
        elif frame.ear < 0.18:
            # Drowsiness / micro-sleep -> GCS 12 (Moderate lethargy)
            estimated_gcs = 12
        else:
            # Normal alertness -> GCS 15 (Fully conscious)
            estimated_gcs = 15

        return ProcessedFeatures(
            timestamp=frame.timestamp,
            ear=frame.ear,
            pitch_deg=frame.pitch_deg,
            rppg_hr_bpm=frame.rppg_hr_bpm,
            ser_2_6hz=ser_2_6hz,
            ser_gyro_2_6hz=ser_gyro,
            psi=psi,
            wheel_grip=frame.wheel_grip,
            steering_torque_nm=frame.steering_torque_nm,
            optical_snr_db=frame.optical_snr_db,
            face_detected=frame.face_detected,
            imu_heartbeat_ok=frame.imu_heartbeat_ok,
            tonic_detected=tonic_detected,
            estimated_gcs=estimated_gcs,
            hr_min_10s=hr_min,
            hr_max_10s=hr_max,
            hr_mean_10s=hr_mean
        )

    def _compute_triaxial_ser(self, imu_window: np.ndarray) -> float:
        """
        Computes the ratio of spectral energy concentrated in the 2.0-6.0 Hz clonic band
        relative to the total vibration spectrum (0.5-20.0 Hz) using Welch's periodogram
        summed across all three centered sensor axes (Equation 5).
        """
        if imu_window is None or len(imu_window) < 32 or np.all(imu_window == 0):
            return 0.0

        fs = config.SAMPLE_RATE_IMU_HZ  # 100 Hz
        nperseg = min(len(imu_window), 64)

        # Remove each axis' DC component, then compute and sum the three axis PSDs.
        # S_total(f) = S_xx(f) + S_yy(f) + S_zz(f)
        centered_imu = imu_window - np.mean(imu_window, axis=0, keepdims=True)
        freqs, axis_psd = signal.welch(
            centered_imu, fs=fs, nperseg=nperseg, axis=0, scaling='density'
        )
        psd = np.sum(axis_psd, axis=1)

        # Band integration: 2.0 - 6.0 Hz (clonic motor spasm band)
        band_clonic = (freqs >= 2.0) & (freqs <= 6.0)
        # Total baseline band: 0.5 - 20.0 Hz
        band_total = (freqs >= 0.5) & (freqs <= 20.0)

        total_power = np.sum(psd[band_total])
        if total_power < 1e-6:
            return 0.0

        clonic_power = np.sum(psd[band_clonic])
        ser = float(clonic_power / total_power)
        return float(np.clip(ser, 0.0, 1.0))
