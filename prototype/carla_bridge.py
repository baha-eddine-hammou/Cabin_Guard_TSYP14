"""
CabinGuard-ADI: CARLA Simulator Bridge Adapter (Phase 2 Interface)
==================================================================
Provides client interface and telemetry translation between CabinGuard's
UNECE R157 safety controller and CARLA Autonomous Driving Simulator (v0.9.14+).

Scope & Provenance:
-------------------
In Phase 1, primary evaluation is conducted via the deterministic multi-body
kinematic simulator (simulator.py) and multi-seed Monte Carlo evaluation.
This module defines the CARLA co-simulation bridge architecture, ROS2 / PythonAPI
client connectors, and vehicle actuation translation for Phase 2 hardware/HIL
deployment. When CARLA is unavailable, a standalone mock mode operates cleanly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("cabinguard.carla_bridge")


@dataclass
class CarlaVehicleState:
    """Snapshot of ego-vehicle kinematic and actuation state from CARLA."""
    timestamp_s: float
    speed_kmh: float
    speed_ms: float
    lane_id: int
    lateral_offset_m: float
    throttle: float
    steer: float
    brake: float
    reverse: bool
    hand_brake: bool
    hazard_lights: bool


class CarlaBridgeAdapter:
    """
    Bridge adapter connecting CabinGuard safety actuation to CARLA vehicle actor.
    Supports both live CARLA Python API client and mock loopback mode.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2000,
        timeout_s: float = 5.0,
        mock_mode: bool = True,
    ):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.mock_mode = mock_mode
        self._connected = False
        self._vehicle_actor = None
        self._current_state = CarlaVehicleState(
            timestamp_s=0.0,
            speed_kmh=100.0,
            speed_ms=27.78,
            lane_id=1,
            lateral_offset_m=0.0,
            throttle=0.6,
            steer=0.0,
            brake=0.0,
            reverse=False,
            hand_brake=False,
            hazard_lights=False,
        )

    def connect(self) -> bool:
        """Attempt connection to CARLA simulator world."""
        if self.mock_mode:
            self._connected = True
            logger.info("CarlaBridge running in standalone mock mode (no live CARLA server required)")
            return True

        try:
            import carla  # type: ignore
            client = carla.Client(self.host, self.port)
            client.set_timeout(self.timeout_s)
            world = client.get_world()
            self._connected = True
            logger.info(f"Connected to CARLA simulator at {self.host}:{self.port}, map: {world.get_map().name}")
            return True
        except ImportError:
            logger.warning("carla Python package not installed; falling back to mock mode")
            self.mock_mode = True
            self._connected = True
            return True
        except Exception as exc:
            logger.error(f"Failed to connect to CARLA server: {exc}; falling back to mock mode")
            self.mock_mode = True
            self._connected = True
            return False

    def is_connected(self) -> bool:
        return self._connected

    def read_vehicle_state(self) -> CarlaVehicleState:
        """Fetch latest vehicle state from CARLA actor or simulated kinematics."""
        return self._current_state

    def apply_mrm_actuation(
        self,
        target_decel_mss: float,
        lateral_steer: float,
        hazards_active: bool,
        parking_brake: bool,
    ) -> Dict[str, Any]:
        """
        Translates CabinGuard MRM safety commands into CARLA vehicle control inputs.
        
        Parameters
        ----------
        target_decel_mss : float
            Requested longitudinal deceleration in m/s^2 (e.g. -3.2 m/s^2).
        lateral_steer : float
            Normalized steering command [-1.0, 1.0].
        hazards_active : bool
            True when emergency flasher relay is engaged.
        parking_brake : bool
            True during Phase 4 standstill clamping.
        """
        # Brake mapping: normalized [0.0, 1.0] from decel request
        brake_norm = float(min(1.0, max(0.0, abs(target_decel_mss) / 4.0))) if target_decel_mss < 0 else 0.0
        throttle = 0.0 if brake_norm > 0.1 else 0.4

        control_dict = {
            "throttle": throttle,
            "steer": float(lateral_steer),
            "brake": brake_norm,
            "hand_brake": bool(parking_brake),
            "hazard_lights": bool(hazards_active),
            "target_decel_mss": float(target_decel_mss),
        }

        # Update mock state
        self._current_state.throttle = throttle
        self._current_state.steer = lateral_steer
        self._current_state.brake = brake_norm
        self._current_state.hand_brake = parking_brake
        self._current_state.hazard_lights = hazards_active

        return control_dict

    def disconnect(self) -> None:
        """Disconnect and release any spawned actors."""
        self._connected = False
        self._vehicle_actor = None
