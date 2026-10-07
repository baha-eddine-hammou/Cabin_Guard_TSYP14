"""
CabinGuard-ADI: Configuration and System Constants
Aligned with UNECE R157, ISO 26262 ASIL-D, and IEEE Challenge Specifications.
"""
from dataclasses import dataclass

# Sampling Frequencies (Hz)
SAMPLE_RATE_CAMERA_HZ = 60.0       # Near-Infrared Video (60 FPS)
SAMPLE_RATE_IMU_HZ = 100.0         # Headrest MPU6050 Accelerometer
SAMPLE_RATE_FSR_HZ = 50.0          # Seatback Force-Sensing Resistors
SAMPLE_RATE_FUSION_HZ = 10.0       # Edge AI Bayesian Decision Loop (100 ms period)
FUSION_DT = 1.0 / SAMPLE_RATE_FUSION_HZ  # 0.100 seconds

# Algorithm 1: Watchdog & Decision Thresholds
CONFIDENCE_THRESHOLD_GAMMA = 0.85   # Posterior probability threshold for confirmation
VERIFICATION_DURATION_S = 2.0      # Required persistence time before safety action (seconds)
VERIFICATION_CYCLES = int(VERIFICATION_DURATION_S / FUSION_DT) # 20 consecutive cycles

# Optical / Camera Fault Thresholds
MIN_OPTICAL_SNR_DB = -15.0         # Below -15 dB: switch to Degraded Mode 1 (bypasses vision)
SPOOF_HR_MIN_TORQUE_NM = 1.0       # Anti-spoofing: torque > 1.0 Nm with HR=0 triggers laser interlock

# Medical Classification Decision Boundaries (Table I in Paper)
# Class 0: Normal Driving
NORMAL_EAR_MIN = 0.20
NORMAL_EAR_MAX = 0.40
NORMAL_PITCH_MIN_DEG = -15.0
NORMAL_PITCH_MAX_DEG = 15.0
NORMAL_SER_MAX = 0.20
NORMAL_HR_MIN_BPM = 50.0
NORMAL_HR_MAX_BPM = 105.0
NORMAL_PSI_MAX = 0.25

# Class 1: Cardiac Syncope
SYNCOPE_EAR_MAX = 0.15             # Sustained eye closure
SYNCOPE_PITCH_MAX_DEG = -25.0      # Severe cranial forward slump
SYNCOPE_SER_MAX = 0.18             # Atonic (no motor tremors)
SYNCOPE_BRADYCARDIA_BPM = 40.0     # Severe bradycardia (<40 BPM)
SYNCOPE_TACHYCARDIA_BPM = 150.0    # Ventricular tachycardia (>150 BPM)
SYNCOPE_PSI_MIN = 0.75             # Severe postural collapse / backrest separation

# Class 2: Epileptic Seizure
SEIZURE_SER_MIN = 0.65             # Concentrated power in 2-6 Hz clonic band
SEIZURE_HR_MIN_BPM = 100.0         # Autonomic sympathetic activation
SEIZURE_HR_MAX_BPM = 150.0
TONIC_SEIZURE_FSR_MIN = 0.95       # Saturated thoracic pressure onset for tonic prefilter
TONIC_PREFILTER_EAR_MAX = 0.18      # Eye closure threshold for tonic seizure prefilter
SEIZURE_OVERRIDE_SUPPRESSION_SER = 0.65

# Vehicle Dynamics & UNECE R157 MRM Parameters
HIGHWAY_CRUISE_SPEED_KMH = 100.0   # 100 km/h initial speed
HIGHWAY_CRUISE_SPEED_MS = HIGHWAY_CRUISE_SPEED_KMH / 3.6  # 27.78 m/s
MRM_TARGET_DECEL_MSS = -3.2        # Controlled deceleration (-3.2 m/s^2, limit <= -4.0)
LANE_WIDTH_M = 3.5                 # Standard highway lane width (meters)
SHOULDER_OFFSET_M = -7.0           # Right emergency shoulder (2 lanes across = -7.0 m)

# UNECE R157 Phase Timings (seconds from t_event_verified)
PHASE_1_DURATION_S = 3.0           # Pre-alert: 0 to 3s (chime, haptic pulse, override allowed)
PHASE_2_START_S = 4.0              # Escalation: 4s (autonomous takeover, hazards active)
PHASE_3_START_S = 10.0             # Active MRM: 10s (controlled decel -3.2 m/s^2, lateral lane change)
DRIVER_OVERRIDE_TORQUE_NM = 4.0    # Manual torque > 4.0 Nm cancels MRM during Phase 1

# Telematics & CAN-FD Specifications
CAN_MRM_MSG_ID = 0x120             # CAN-FD Arb ID for CabinGuard MRM Command
CAN_STATUS_MSG_ID = 0x121          # CAN-FD Arb ID for Sensor Telemetry Stream
ETSI_DENM_CAUSE_CODE = 6           # Emergency Stop
ETSI_DENM_SUBCAUSE_CODE = 1        # Human Problem / Medical Incapacitation
MEC_PAYLOAD_SIZE_BYTES = 76        # Anonymized 76-byte Medical Extension Container

