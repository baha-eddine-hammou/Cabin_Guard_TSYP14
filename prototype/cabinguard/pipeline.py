"""End-to-end loop: sensors -> detection -> safety decision -> CAN -> vehicle -> eCall.

``CabinGuardECU`` is everything that runs on the edge host. Its only output to
the vehicle is the authenticated 0x120 frame. ``VehicleSide`` is everything
the ECU does not control: the gateway (authentication, plausibility, alive
supervision), a point-mass vehicle, and the telematics unit with its bearers
and the PSAP. The two halves meet on a ``Bus``, which is an in-process list
here and a python-can bus on hardware (``cabinguard.hardware.CanBus``).

Fault injection covers each failure the challenge lists: sensor failure and
missing data (simulator scenarios), processing failure (``ecu_hang_at``),
tampered, replayed, forged and implausible commands (``attack``), and
communication failure (``bearer_outage``).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from . import config
from .can_messages import MRM_CMD_ID, MRMCommand, MRMCommandTx
from .emergency_link import MEC, Bearer, EmergencyNotifier, PSAPReceiver, PseudonymSigner, build_denm, seal_for_psap
from .feature_extraction import FeatureExtractor
from .safety_controller import MRMState, VehicleSafetyController
from .vehicle_gateway import VehicleGateway
from .watchdog import CrossSensorWatchdog

PHASE_CODE = {MRMState.NORMAL: 0, MRMState.PHASE_1_PRE_ALERT: 1, MRMState.PHASE_2_ESCALATION: 2,
              MRMState.PHASE_3_ACTIVE_MRM: 3, MRMState.PHASE_4_STANDSTILL: 4}
DEADLINE_S = config.FUSION_DT
MAX_OVERRUNS = 3


class Bus:
    """In-process stand-in for a CAN bus: frames sent in a cycle are read in the same cycle."""

    def __init__(self):
        self.frames: list[tuple[int, bytes]] = []

    def send(self, arb_id: int, data: bytes) -> None:
        self.frames.append((arb_id, bytes(data)))

    def drain(self) -> list[tuple[int, bytes]]:
        out, self.frames = self.frames, []
        return out


@dataclass
class CycleRecord:
    t: float
    mode: str
    posterior: dict
    candidate: str
    trigger: bool
    mrm_state: str
    speed_kmh: float
    gateway_decel: float
    spoof: bool
    ecu_alive: bool
    compute_ms: float


class CabinGuardECU:
    def __init__(self, key: bytes, classifier=None, initial_speed_kmh: float = 100.0):
        self.extractor = FeatureExtractor()
        self.watchdog = CrossSensorWatchdog(classifier)
        self.controller = VehicleSafetyController(initial_speed_kmh)
        self.tx = MRMCommandTx(key)
        self.overruns = 0
        self.consecutive_overruns = 0
        self.failed = False
        self.event_t: float | None = None
        self.decision = None
        self._warm_up()

    def _warm_up(self) -> None:
        """Pin inference to one thread and run the models before the deadline applies.

        Multi-threaded tree inference on a single sample spends its time
        waiting for the thread pool, and stalls whenever another process holds
        the cores; one thread gives a short, predictable cycle.
        """
        from threadpoolctl import threadpool_limits
        self._threads = threadpool_limits(limits=1)
        from .cardiac_features import CardiacFeatures
        from .fusion import FusionInput
        from .motion_features import EMPTY
        for _ in range(3):
            self.watchdog.classifier.classify(FusionInput(CardiacFeatures(70, 0, 0.05, 0), EMPTY, 0.3, 0, 0.1, "ACTIVE"))

    def step(self, snap, speed_ms: float, bus: Bus, hang: bool = False):
        """One 100 ms cycle. Returns the decision, or None once the ECU has failed silent."""
        if self.failed:
            return None
        t0 = time.perf_counter()
        f = self.extractor.process(snap)
        self.features = f
        d = self.watchdog.evaluate(f)
        self.controller.speed_ms = speed_ms          # plan from the measured speed
        dyn = self.controller.step(d.mrm_trigger_flag, d.active_class, f.steering_torque_nm, f.brake_pedal,
                                   d.override_suppressed)
        if dyn.mrm_state != MRMState.NORMAL and self.event_t is None:
            self.event_t = snap.t
        elapsed = time.perf_counter() - t0 + (1.0 if hang else 0.0)
        if elapsed > DEADLINE_S:
            self.overruns += 1
            self.consecutive_overruns += 1
            if self.consecutive_overruns >= MAX_OVERRUNS:
                self.failed = True                  # fail silent: the gateway takes over
                return None
        else:
            self.consecutive_overruns = 0
        phase = PHASE_CODE[dyn.mrm_state]
        cmd = MRMCommand(
            phase=phase, active=phase >= 1, hazards=dyn.hazard_flashers_active, epb=dyn.epb_clamped,
            doors_unlock=dyn.doors_unlocked, decel_mss=dyn.longitudinal_accel_mss,
            etiology=dyn.confirmed_etiology if phase else "None", degraded_level=d.degraded_level,
            spoof_interlock=d.spoofing_detected, ecall=phase >= 2, denm=phase >= 3,
            confidence=d.top_confidence)
        bus.send(MRM_CMD_ID, self.tx.frame(cmd))
        self.decision = d
        self.last_dyn = dyn
        self.last_compute_ms = (time.perf_counter() - t0) * 1000
        return d


@dataclass
class VehicleSide:
    key: bytes
    speed_ms: float = config.HIGHWAY_CRUISE_SPEED_MS
    seed: int = 0
    gateway: VehicleGateway = field(init=False)
    signer: PseudonymSigner = field(init=False)
    psap: PSAPReceiver = field(init=False)
    notifier: EmergencyNotifier = field(init=False)
    received_mec: list = field(default_factory=list)
    denm_sent: list = field(default_factory=list)

    def __post_init__(self):
        self.gateway = VehicleGateway(self.key)
        self.signer = PseudonymSigner()
        self.psap = PSAPReceiver()
        self.psap.trusted.append(self.signer.public_key)
        self.notifier = EmergencyNotifier(Bearer("cellular"), Bearer("sms"))
        self.rng = random.Random(self.seed)
        self._mec_submitted = False

    def step(self, t: float, bus: Bus, ecu: CabinGuardECU, driver_brake: bool = False):
        for arb_id, data in bus.drain():
            self.gateway.receive(t, arb_id, data, driver_override=driver_brake)
        g = self.gateway.tick(t, self.speed_ms)
        self.speed_ms = max(0.0, self.speed_ms + g.decel_mss * config.FUSION_DT)
        if g.ecall_requested and not self._mec_submitted:
            d = ecu.decision
            etiology = ecu.controller.confirmed_etiology if not ecu.failed else "Unspecified"
            card = getattr(ecu, "features", None) and ecu.features.cardiac
            hr = card.hr_bpm if card else None
            mec = MEC(etiology, d.top_confidence if d else 0.0,
                      int(1000 * (t - (ecu.event_t or t))), _sensor_names(d), hr,
                      self.signer.next_seq(), int(time.time()))
            self.notifier.submit(seal_for_psap(self.signer.sign(mec), self.psap.public_key), t)
            self._mec_submitted = True
        if g.phase >= 3 and not self.denm_sent:
            self.denm_sent.append(build_denm(0x5A88B1, self.speed_ms * 3.6, self.signer))
        self.notifier.step(t, self.rng, self._deliver)
        return g

    def _deliver(self, sealed: bytes) -> bool:
        mec = self.psap.receive(sealed, int(time.time()))
        if mec is not None:
            self.received_mec.append(mec)
        return mec is not None


def _sensor_names(d) -> tuple:
    if d is None:
        return ()
    names = {0: ("camera", "imu", "fsr", "grip"), 1: ("imu", "fsr", "grip"), 2: ("camera", "fsr", "grip"),
             3: ()}
    return names[d.degraded_level]


@dataclass
class RunResult:
    records: list
    ecu: CabinGuardECU
    vehicle: VehicleSide
    attack_frames: int = 0

    @property
    def triggered_class(self) -> str:
        c = self.ecu.controller.confirmed_etiology
        return c if c not in ("None", None) else "Normal"

    @property
    def detection_time(self) -> float | None:
        return self.ecu.event_t


def run_scenario(simulator, key: bytes = bytes(range(16)), classifier=None, ecu_hang_at: float | None = None,
                 attack: str | None = None, attack_at: float = 5.0, bearer_outage: tuple | None = None,
                 seed: int = 0) -> RunResult:
    """Drive one simulator scenario through the full pipeline with optional faults.

    ``attack`` is one of ``tamper``, ``replay``, ``forge`` or ``implausible``;
    ``bearer_outage`` is ``(t_start, t_end, include_sms)``.
    """
    bus = Bus()
    ecu = CabinGuardECU(key, classifier)
    veh = VehicleSide(key, seed=seed)
    attacker = MRMCommandTx(b"\xA5" * 16)
    captured: list[bytes] = []
    records, n_attack = [], 0
    for snap in simulator:
        t = snap.t
        if bearer_outage:
            a, b, sms = bearer_outage
            down = a <= t < b
            veh.notifier.primary.up = not down
            veh.notifier.fallback.up = not (down and sms)
        hang = ecu_hang_at is not None and t >= ecu_hang_at
        d = ecu.step(snap, veh.speed_ms, bus, hang=hang)
        frames = bus.frames
        if frames and len(captured) < 5:
            captured.append(frames[-1][1])
        if attack and t >= attack_at:
            n_attack += 1
            stop = MRMCommand(phase=3, active=True, hazards=True, decel_mss=-6.0, etiology="Seizure")
            if attack == "tamper" and frames:
                arb, data = frames.pop()
                frames.append((arb, bytes([data[0] ^ 0x0B]) + data[1:]))
            elif attack == "replay" and captured:
                bus.send(MRM_CMD_ID, captured[0])
            elif attack == "forge":
                bus.send(MRM_CMD_ID, attacker.frame(stop))
            elif attack == "implausible":
                # Even a frame with a valid MAC must not jump straight to braking.
                bus.send(MRM_CMD_ID, ecu.tx.frame(stop))
        g = veh.step(t, bus, ecu, driver_brake=snap.brake_pedal)
        records.append(CycleRecord(
            t, d.mode if d else "ECU failed", d.raw.posteriors if d else {}, d.candidate_class if d else "-",
            bool(d and d.mrm_trigger_flag), ecu.controller.state.name if not ecu.failed else "ECU_FAILED",
            veh.speed_ms * 3.6, g.decel_mss, bool(d and d.spoofing_detected), not ecu.failed,
            getattr(ecu, "last_compute_ms", 0.0)))
    return RunResult(records, ecu, veh, n_attack)
