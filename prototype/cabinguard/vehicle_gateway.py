"""Actuator-side gateway model: the last line of defence for vehicle commands.

The gateway trusts nothing it receives. Every 0x120 frame must pass SecOC
verification and a plausibility gate before it can move an actuator, and the
cyclic frame doubles as the ECU alive signal:

* no valid frame for ``ALIVE_TIMEOUT_S`` while the driver is still in control
  raises a fault telltale and actuates nothing (fail-silent, the driver drives);
* no valid frame while an automated manoeuvre is already under way continues
  the stop with the last plausible deceleration (fail-operational), because a
  driver judged incapacitated cannot take the vehicle back.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .can_messages import MRMCommand, MRMCommandRx

ALIVE_TIMEOUT_S = 0.3          # three missed 100 ms cycles
DECEL_LIMIT_MSS = -4.0         # most negative deceleration the gateway will forward
FALLBACK_DECEL_MSS = -3.2
ALLOWED_NEXT_PHASE = {0: {0, 1}, 1: {0, 1, 2}, 2: {0, 2, 3}, 3: {3, 4}, 4: {4}}


@dataclass
class GatewayState:
    phase: int = 0
    decel_mss: float = 0.0
    hazards: bool = False
    epb: bool = False
    ecu_fault: bool = False
    fail_operational: bool = False
    ecall_requested: bool = False
    log: list = field(default_factory=list)


class VehicleGateway:
    def __init__(self, key: bytes):
        self.rx = MRMCommandRx(key)
        self.state = GatewayState()
        self.last_valid_t: float | None = None
        self.rejected_implausible = 0

    def _plausible(self, cmd: MRMCommand, driver_override: bool) -> bool:
        if not DECEL_LIMIT_MSS <= cmd.decel_mss <= 0.0:
            return False
        if cmd.phase not in ALLOWED_NEXT_PHASE.get(self.state.phase, set()):
            # Leaving an active manoeuvre is only legitimate when the gateway
            # itself sees the driver act (brake pedal), never on ECU say-so.
            return driver_override and cmd.phase == 0
        if cmd.phase >= 3 and not cmd.active:
            return False
        return True

    def receive(self, t: float, arb_id: int, data: bytes, driver_override: bool = False) -> bool:
        cmd = self.rx.accept(arb_id, data)
        if cmd is None:
            self.state.log.append((t, "rejected: authentication or freshness"))
            return False
        if not self._plausible(cmd, driver_override):
            self.rejected_implausible += 1
            self.state.log.append((t, f"rejected: implausible command {cmd}"))
            return False
        self.last_valid_t = t
        s = self.state
        s.phase, s.decel_mss, s.hazards, s.epb = cmd.phase, cmd.decel_mss, cmd.hazards, cmd.epb
        s.ecall_requested |= cmd.ecall
        s.ecu_fault = False
        return True

    def tick(self, t: float, speed_ms: float) -> GatewayState:
        """Run alive supervision; returns the state the actuators should apply."""
        s = self.state
        silent = self.last_valid_t is None or t - self.last_valid_t > ALIVE_TIMEOUT_S
        if silent and not s.ecu_fault:
            s.ecu_fault = True
            s.log.append((t, "ECU alive timeout"))
        if silent and s.phase >= 2 and speed_ms > 0.0:
            s.fail_operational = True
            s.hazards = True
            s.ecall_requested = True
            s.decel_mss = s.decel_mss if s.decel_mss < 0.0 else FALLBACK_DECEL_MSS
        elif silent and s.phase < 2:
            s.decel_mss = 0.0       # driver in control: warn, never actuate
        if speed_ms <= 0.0 and s.phase >= 2:
            s.epb = True
            s.decel_mss = 0.0
        return s
