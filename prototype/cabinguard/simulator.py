"""
CabinGuard-ADI: Multimodal In-Cabin Sensor Stream Simulator
Simulates realistic time-series signals for camera, headrest IMU, seatback FSR,
and steering wheel grip across normal driving, clinical crises, and attack scenarios.
"""
from dataclasses import dataclass
from enum import Enum
import math
import numpy as np
from . import config

class ScenarioType(Enum):
    NORMAL_DRIVING = "Normal Highway Driving"
    CARDIAC_SYNCOPE = "Sudden Cardiac Syncope (Atonic Slump)"
    EPILEPTIC_SEIZURE = "Convulsive Epileptic Seizure (Clonic Spasms)"
    OPTICAL_BLINDING_ATTACK = "Adversarial Optical Blinding / Spoofing Attack"
    IMU_HARDWARE_FAULT = "Headrest IMU Disconnect / Hardware Fault"

class SensorMode(Enum):
    NORMAL = "Normal"
    SYNCOPE = "Syncope"
    SEIZURE = "Seizure"
    ATTACK = "Attack"
    FAULT = "Fault"

@dataclass
class SensorFrame:
    timestamp: float              # Current time in simulation (seconds)
    mode: SensorMode             # Clinical / fault mode tag for each synthetic frame
    ear: float                    # Eye Aspect Ratio [0.0 - 0.45]
    pitch_deg: float              # Cranial pitch angle in degrees [-90 to +90]
    optical_snr_db: float         # Camera signal-to-noise ratio in dB
    face_detected: bool           # Face landmark tracking status
    rppg_hr_bpm: float            # Contactless optical heart rate estimation
    imu_accel_window: np.ndarray  # Raw headrest tri-axial acceleration window (Nx3, 100 Hz)
    imu_gyro_window: np.ndarray | None = None
    imu_heartbeat_ok: bool = True # I2C communication heartbeat status
    fsr_pressure: float = 0.0    # Instantaneous normalized seatback pressure [0.0 - 1.0]
    wheel_grip: str = "ACTIVE"    # "ACTIVE", "DISENGAGED", "CLENCHED"
    steering_torque_nm: float = 0.0 # Driver manual steering torque in Nm
    brake_pedal_pressed: bool = False # Manual brake override pedal status

class MultimodalSensorSimulator:
    """Generates time-aligned multimodal frames at 10 Hz for edge processing."""
    def __init__(self, scenario: ScenarioType, duration_s: float = 35.0, seed: int = 42):
        self.scenario = scenario
        self.duration_s = duration_s
        self.dt = config.FUSION_DT
        self.total_steps = int(duration_s / self.dt)
        self.rng = np.random.default_rng(seed)
        self.step_idx = 0

    def __iter__(self):
        self.step_idx = 0
        return self

    def __next__(self) -> SensorFrame:
        if self.step_idx >= self.total_steps:
            raise StopIteration

        t = self.step_idx * self.dt
        frame = self._generate_frame_at_time(t)
        self.step_idx += 1
        return frame

    def _generate_frame_at_time(self, t: float) -> SensorFrame:
        event_onset_t = 4.0  # Acute event initiates at t = 4.0s
        is_event_active = (t >= event_onset_t)

        # Baseline Road Vibration for Headrest IMU (100 Hz buffer for 1.0 second = 100 samples)
        n_samples = int(config.SAMPLE_RATE_IMU_HZ * 1.0)
        t_imu = np.linspace(t - 1.0, t, n_samples)
        # Low frequency chassis rumble (0.5 - 2 Hz) + broad dispersion
        chassis_rumble_x = 0.25 * np.sin(2 * np.pi * 1.2 * t_imu) + self.rng.normal(0, 0.15, n_samples)
        chassis_rumble_y = 0.20 * np.cos(2 * np.pi * 1.5 * t_imu) + self.rng.normal(0, 0.12, n_samples)
        chassis_rumble_z = 9.81 + 0.30 * np.sin(2 * np.pi * 0.8 * t_imu) + self.rng.normal(0, 0.20, n_samples)
        imu_window = np.column_stack([chassis_rumble_x, chassis_rumble_y, chassis_rumble_z])

        # Default Normal Driving parameters
        # Natural spontaneous eye blinks (every ~3-4 seconds, lasting 150-250ms)
        is_blinking = (math.fmod(t, 3.5) < 0.20)
        ear = 0.10 if is_blinking else float(self.rng.normal(0.31, 0.02))
        pitch_deg = float(self.rng.normal(1.5, 3.0))
        optical_snr_db = float(self.rng.normal(8.5, 1.5))
        face_detected = True
        rppg_hr_bpm = float(self.rng.normal(74.0, 2.5))
        imu_heartbeat_ok = True
        fsr_pressure = float(np.clip(self.rng.normal(0.85, 0.03), 0.0, 1.0)) # Normal back contact
        wheel_grip = "ACTIVE"
        steering_torque_nm = float(self.rng.normal(0.4, 0.15))
        brake_pedal_pressed = False

        # Apply Scenario Injections
        if self.scenario == ScenarioType.NORMAL_DRIVING:
            pass  # Retain normal driving baseline throughout

        elif self.scenario == ScenarioType.CARDIAC_SYNCOPE:
            if is_event_active:
                progress = min(1.0, (t - event_onset_t) / 2.0) # Complete slump within 2.0s
                # Loss of consciousness: permanent eye closure
                ear = float(0.31 * (1.0 - progress) + 0.06 * progress + self.rng.normal(0, 0.01))
                # Severe forward cranial slump
                pitch_deg = float(1.5 * (1.0 - progress) - 34.0 * progress + self.rng.normal(0, 1.0))
                # Cardiogenic bradycardia / asystolic collapse
                rppg_hr_bpm = float(74.0 * (1.0 - progress) + 32.0 * progress + self.rng.normal(0, 1.5))
                # Torso falls forward away from seatback
                fsr_pressure = float(0.85 * (1.0 - progress) + 0.08 * progress + self.rng.normal(0, 0.02))
                # Hands slip completely off the steering wheel
                wheel_grip = "DISENGAGED" if progress > 0.4 else "ACTIVE"
                steering_torque_nm = float(0.4 * (1.0 - progress) + self.rng.normal(0, 0.02))

        elif self.scenario == ScenarioType.EPILEPTIC_SEIZURE:
            if is_event_active:
                progress = min(1.0, (t - event_onset_t) / 1.5)
                # Rapid erratic eyelid flutter / gaze elevation
                flutter = 0.12 + 0.14 * np.abs(np.sin(2 * np.pi * 5.0 * t))
                ear = float(0.31 * (1.0 - progress) + flutter * progress)
                # Cranial tremor oscillation
                pitch_deg = float(1.5 + 12.0 * progress * np.sin(2 * np.pi * 3.8 * t) + self.rng.normal(0, 1.5))
                # Autonomic sympathetic tachycardia
                rppg_hr_bpm = float(74.0 * (1.0 - progress) + 128.0 * progress + self.rng.normal(0, 2.0))
                # Convulsive 3.5 Hz clonic motor spasms injected directly into Headrest Accelerometer
                clonic_spasm_x = 3.2 * progress * np.sin(2 * np.pi * 3.6 * t_imu)
                clonic_spasm_y = 2.8 * progress * np.cos(2 * np.pi * 3.6 * t_imu)
                imu_window[:, 0] += clonic_spasm_x
                imu_window[:, 1] += clonic_spasm_y
                # Spasmodic torso contact
                fsr_pressure = float(0.85 - 0.45 * progress + 0.15 * np.sin(2 * np.pi * 3.6 * t))
                # Clenched motor lock on steering wheel
                wheel_grip = "CLENCHED" if progress > 0.3 else "ACTIVE"
                steering_torque_nm = float(0.4 + 1.2 * progress + self.rng.normal(0, 0.1))

        elif self.scenario == ScenarioType.OPTICAL_BLINDING_ATTACK:
            if is_event_active:
                # Adversarial optical blinding / direct laser attack
                optical_snr_db = -22.5 + float(self.rng.normal(0, 1.0)) # SNR drops far below -15 dB
                face_detected = False
                # Attacker injects a synthetic optical pulse of 0 BPM (spoofed cardiac standstill)
                rppg_hr_bpm = 0.0
                ear = 0.0
                # BUT Driver is completely healthy: actively steering and gripping the wheel!
                wheel_grip = "ACTIVE"
                steering_torque_nm = 2.1 + float(self.rng.normal(0, 0.2)) # Active driver counter-steering
                fsr_pressure = 0.88 # Firm torso support
                pitch_deg = 2.0

        elif self.scenario == ScenarioType.IMU_HARDWARE_FAULT:
            if is_event_active:
                # Headrest accelerometer I2C bus wiring failure
                imu_heartbeat_ok = False
                imu_window = np.zeros_like(imu_window) # Frozen / zero sensor output

        # Clamp physical values
        ear = float(np.clip(ear, 0.0, 0.45))
        fsr_pressure = float(np.clip(fsr_pressure, 0.0, 1.0))
        rppg_hr_bpm = float(max(0.0, rppg_hr_bpm))

        mode = SensorMode.NORMAL
        if self.scenario == ScenarioType.CARDIAC_SYNCOPE:
            mode = SensorMode.SYNCOPE
        elif self.scenario == ScenarioType.EPILEPTIC_SEIZURE:
            mode = SensorMode.SEIZURE
        elif self.scenario == ScenarioType.OPTICAL_BLINDING_ATTACK:
            mode = SensorMode.ATTACK
        elif self.scenario == ScenarioType.IMU_HARDWARE_FAULT:
            mode = SensorMode.FAULT

        return SensorFrame(
            timestamp=t,
            mode=mode,
            ear=ear,
            pitch_deg=pitch_deg,
            optical_snr_db=optical_snr_db,
            face_detected=face_detected,
            rppg_hr_bpm=rppg_hr_bpm,
            imu_accel_window=imu_window,
            imu_gyro_window=np.zeros_like(imu_window),
            imu_heartbeat_ok=imu_heartbeat_ok,
            fsr_pressure=fsr_pressure,
            wheel_grip=wheel_grip,
            steering_torque_nm=steering_torque_nm,
            brake_pedal_pressed=brake_pedal_pressed
        )

