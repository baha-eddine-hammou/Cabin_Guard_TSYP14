"""
CabinGuard-ADI: Vehicle Safety Response & UNECE R157 Minimum Risk Maneuver Controller
Executes Phase 1-4 safety state machine, driver override interlocks, and closed-loop vehicle physics.
"""
from dataclasses import dataclass
from enum import Enum
import math
from . import config

class MRMState(Enum):
    NORMAL = "Normal Monitoring"
    PHASE_1_PRE_ALERT = "Phase 1: Pre-Alert (Chime & Haptic Pulse)"
    PHASE_2_ESCALATION = "Phase 2: Escalation (Autonomous Takeover & Hazards)"
    PHASE_3_ACTIVE_MRM = "Phase 3: Active MRM (Decel -3.2 m/s² & Shoulder Pull)"
    PHASE_4_STANDSTILL = "Phase 4: Standstill (EPB Clamped, Doors Unlocked, eCall Sent)"

@dataclass
class VehicleDynamicsState:
    timestamp: float
    mrm_state: MRMState
    speed_kmh: float
    speed_ms: float
    longitudinal_accel_mss: float
    longitudinal_dist_m: float
    lateral_pos_m: float           # 0.0m = Lane 2, -3.5m = Lane 1, -7.0m = Shoulder
    hazard_flashers_active: bool
    doors_unlocked: bool
    epb_clamped: bool
    acoustic_chime_active: bool
    haptic_pulse_active: bool
    denm_broadcast_active: bool
    ecall_transmitted: bool
    confirmed_etiology: str

class VehicleSafetyController:
    """Implements the deterministic UNECE R157 MRM safety state machine."""
    def __init__(self, initial_speed_kmh: float = config.HIGHWAY_CRUISE_SPEED_KMH):
        self.dt = config.FUSION_DT
        self.state = MRMState.NORMAL
        self.mrm_timer = 0.0       # Elapsed time since MRM triggered
        self.confirmed_etiology = "None"

        # Physical states
        self.speed_ms = initial_speed_kmh / 3.6
        self.accel_mss = 0.0
        self.dist_m = 0.0
        self.lateral_pos_m = 0.0   # Starts in center of Lane 2

        # Actuator command flags
        self.hazard_flashers = False
        self.doors_unlocked = False
        self.epb_clamped = False
        self.acoustic_chime = False
        self.haptic_pulse = False
        self.denm_broadcast = False
        self.ecall_sent = False

    def step(self, mrm_trigger: bool, etiology: str, steering_torque: float, brake_pressed: bool, override_suppressed: bool = False) -> VehicleDynamicsState:
        # Check transition from NORMAL to PHASE 1
        if self.state == MRMState.NORMAL:
            if mrm_trigger:
                self.state = MRMState.PHASE_1_PRE_ALERT
                self.mrm_timer = 0.0
                self.confirmed_etiology = etiology

        # Execute State Machine
        if self.state == MRMState.PHASE_1_PRE_ALERT:
            self.mrm_timer += self.dt
            self.acoustic_chime = True
            self.haptic_pulse = True
            self.accel_mss = 0.0   # Speed held during alert

            # Driver Manual Override Check: torque > 4.0 Nm or brake pedal cancels MRM
            # Involuntary seizure spasms (override_suppressed=True) cannot cancel MRM via steering torque
            manual_override = (steering_torque > config.DRIVER_OVERRIDE_TORQUE_NM and not override_suppressed) or brake_pressed
            if manual_override:
                self.state = MRMState.NORMAL
                self.mrm_timer = 0.0
                self.acoustic_chime = False
                self.haptic_pulse = False
                self.confirmed_etiology = "None"
            elif self.mrm_timer >= config.PHASE_1_DURATION_S:
                self.state = MRMState.PHASE_2_ESCALATION

        elif self.state == MRMState.PHASE_2_ESCALATION:
            self.mrm_timer += self.dt
            self.acoustic_chime = False
            self.haptic_pulse = False
            self.hazard_flashers = True
            self.accel_mss = 0.0   # Coast / prepare lane clearance

            if self.mrm_timer >= config.PHASE_3_START_S:
                self.state = MRMState.PHASE_3_ACTIVE_MRM
                self.denm_broadcast = True

        elif self.state == MRMState.PHASE_3_ACTIVE_MRM:
            self.mrm_timer += self.dt
            self.accel_mss = config.MRM_TARGET_DECEL_MSS # -3.2 m/s^2 controlled braking

            # Smooth lateral lane shift to right shoulder (-7.0 m) over 8.0 seconds
            t_lane_change = self.mrm_timer - config.PHASE_3_START_S
            lane_change_duration = 8.0
            if t_lane_change < lane_change_duration:
                progress = 0.5 * (1.0 - math.cos(math.pi * t_lane_change / lane_change_duration))
                self.lateral_pos_m = float(config.SHOULDER_OFFSET_M * progress)
            else:
                self.lateral_pos_m = config.SHOULDER_OFFSET_M

            # Check if vehicle reached full standstill
            if self.speed_ms <= 0.05:
                self.speed_ms = 0.0
                self.accel_mss = 0.0
                self.state = MRMState.PHASE_4_STANDSTILL
                self.epb_clamped = True
                self.doors_unlocked = True
                self.ecall_sent = True

        elif self.state == MRMState.PHASE_4_STANDSTILL:
            self.mrm_timer += self.dt
            self.speed_ms = 0.0
            self.accel_mss = 0.0
            self.epb_clamped = True
            self.doors_unlocked = True
            self.ecall_sent = True

        # Integrate Vehicle Physics
        self.speed_ms = max(0.0, self.speed_ms + self.accel_mss * self.dt)
        self.dist_m += self.speed_ms * self.dt

        return VehicleDynamicsState(
            timestamp=self.mrm_timer,
            mrm_state=self.state,
            speed_kmh=self.speed_ms * 3.6,
            speed_ms=self.speed_ms,
            longitudinal_accel_mss=self.accel_mss,
            longitudinal_dist_m=self.dist_m,
            lateral_pos_m=self.lateral_pos_m,
            hazard_flashers_active=self.hazard_flashers,
            doors_unlocked=self.doors_unlocked,
            epb_clamped=self.epb_clamped,
            acoustic_chime_active=self.acoustic_chime,
            haptic_pulse_active=self.haptic_pulse,
            denm_broadcast_active=self.denm_broadcast,
            ecall_transmitted=self.ecall_sent,
            confirmed_etiology=self.confirmed_etiology
        )

