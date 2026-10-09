"""Demo engine: the CabinGuard pipeline at 10 Hz with switchable inputs, events, faults and attacks.

The engine runs exactly the code the paper evaluates (``CabinGuardECU`` and
``VehicleSide``: detection, MRM state machine, SecOC gateway, eCall, DENM) and
adds only what a demonstration needs:

* four input channels (pulse, face, headrest IMU, seat and wheel), each fed by
  the scenario simulator or by a live device (webcam, ESP32 sensor node);
* operator commands: start an event (seizure or syncope), inject a CAN attack,
  inject a sensor or processing fault, reset;
* one JSON-serialisable record per 100 ms cycle for the dashboard, carrying
  an evidence tag per channel that the engine computes, never typed by hand.

Evidence tags: ``SYNTHETIC`` (MultimodalSensorSimulator signals: they exercise
the software, they are not detection performance), ``LIVE`` (a device now),
``INJECTED`` (an operator fault or attack). The vehicle is a point mass on an
in-process bus with simulated bearers, and is tagged so.
"""
from __future__ import annotations

import hashlib
import json
import queue
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import config
from ..can_messages import HEALTH_ID, MRM_CMD_ID, MRMCommand, MRMCommandTx, decode_health, decode_payload
from ..pipeline import Bus, CabinGuardECU, VehicleSide
from ..simulator import EVENT_ONSET_S, MultimodalSensorSimulator, ScenarioType, SensorSnapshot
from ..watchdog import DISTRUST_S

DEMO_KEY = bytes(range(16))
CHANNELS = ("pulse", "face", "imu", "seat")
EVENT_LEAD_S = 1.0                 # event onset this long after the operator presses the button
ATTACK_S = 2.0                     # each injected attack lasts this long, one frame per cycle
BASE_DURATION_S = 900.0            # normal-driving stream length before it restarts
EVENTS = {"seizure": ScenarioType.EPILEPTIC_SEIZURE, "syncope": ScenarioType.CARDIAC_SYNCOPE}
ATTACKS = ("forge", "replay", "tamper", "implausible")
FAULTS = ("blind", "imu_drop", "seat_freeze", "ecu_hang", "cellular_down")
ROOT = Path(__file__).resolve().parents[2]


def to_json(rec: dict) -> str:
    """Strict JSON (no NaN, which the browser's parser rejects); numpy scalars become Python ones."""
    def plain(o):
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(f"{type(o).__name__} is not JSON serialisable")
    return json.dumps(rec, default=plain, allow_nan=False)


class TapBus(Bus):
    """In-process bus that also keeps every frame of the current cycle with its sender."""

    def __init__(self):
        super().__init__()
        self.cycle: list[tuple[int, bytes, str]] = []

    def send(self, arb_id: int, data: bytes, sender: str = "ECU") -> None:
        super().send(arb_id, data)
        self.cycle.append((arb_id, bytes(data), sender))


def restamp(snap: SensorSnapshot, now: float) -> SensorSnapshot:
    """Move a simulator snapshot onto engine time, keeping every age unchanged."""
    d = now - snap.t
    snap.t = now
    for name in ("camera_t", "imu_t", "seat_t"):
        v = getattr(snap, name)
        if v is not None:
            setattr(snap, name, v + d)
    snap.new_beats = [b + d for b in snap.new_beats]
    return snap


class SimStream:
    """One simulator scenario played from ``start_s``, re-stamped onto engine time."""

    def __init__(self, scenario: ScenarioType, seed: int, start_s: float = 0.0, duration_s: float = 120.0):
        self.scenario = scenario
        self.sim = iter(MultimodalSensorSimulator(scenario, duration_s, seed))
        for _ in range(int(round(start_s / config.FUSION_DT))):
            next(self.sim)

    def next(self, now: float) -> SensorSnapshot | None:
        snap = next(self.sim, None)
        return None if snap is None else restamp(snap, now)


@dataclass
class Command:
    name: str
    arg: str | None = None


@dataclass
class DemoState:
    modes: dict = field(default_factory=lambda: {c: "sim" for c in CHANNELS})
    event: str | None = None
    event_onset_t: float | None = None
    faults: set = field(default_factory=set)
    attack: str | None = None
    attack_until: float = 0.0
    staged: bool = False


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "missing"


class DemoEngine:
    """Owns one ECU and one vehicle side; ``step(now)`` runs one 100 ms cycle.

    ``camera`` (``CameraFrontEnd``) and ``node`` (``SerialSensorNode``) are
    optional live devices. ``key`` defaults to the public demo key, and the
    record says so.
    """

    def __init__(self, key: bytes = DEMO_KEY, camera=None, node=None, seed: int = 1, record_path: Path | None = None):
        self.key, self.camera, self.node, self.seed = key, camera, node, seed
        self.commands: queue.Queue = queue.Queue()
        self.record_path = record_path
        self._rec = None
        self.provenance_static = {
            "vehicle": "SIM point-mass (kinematic lateral model)", "bus": "SIM in-process",
            "comms": "SIM bearers + PSAP", "key": "DEMO KEY" if key == DEMO_KEY else "provisioned key",
            "git": _git_commit(),
            "models": {p.name: _sha256(p) for p in sorted((ROOT / "models").glob("*_branch.joblib"))},
        }
        self.reset()

    # ------------------------------------------------------------ control ---
    def submit(self, name: str, arg: str | None = None) -> None:
        """Thread-safe: queue an operator command; it is applied at the start of the next cycle."""
        self.commands.put(Command(name, arg))

    def reset(self) -> None:
        """Rebuild ECU, gateway, plant and notifier together, so no stale freshness or phase survives."""
        self.state = DemoState()
        if self.camera is not None:
            self.state.modes["face"] = "live"         # rPPG on a webcam is not reliable enough: pulse stays sim
        if self.node is not None:
            self.state.modes["imu"] = self.state.modes["seat"] = "live"
        self.bus = TapBus()
        self.ecu = CabinGuardECU(self.key)
        self.vehicle = VehicleSide(self.key, seed=self.seed)
        self.attacker = MRMCommandTx(b"\xA5" * 16)
        self.base = SimStream(ScenarioType.NORMAL_DRIVING, self.seed, 0.0, BASE_DURATION_S)
        self.event_stream: SimStream | None = None
        self.genuine: list[bytes] = []
        self.k = 0
        self.t0: float | None = None
        self.can_rows: list[dict] = []
        self._gw_log_seen = 0
        self._sec_log_seen = 0
        self.distance_m = 0.0

    def _apply(self, cmd: Command, now: float) -> None:
        s = self.state
        if cmd.name == "reset":
            self.reset()
        elif cmd.name == "event" and cmd.arg in EVENTS and s.event is None:
            s.event = cmd.arg
            s.event_onset_t = now + EVENT_LEAD_S
            self.event_stream = SimStream(EVENTS[cmd.arg], self.seed + 7, EVENT_ONSET_S - EVENT_LEAD_S,
                                          EVENT_ONSET_S + 120.0)
            if not s.staged:      # the event's signals come from the scenario on every channel
                s.modes = {c: "sim" for c in CHANNELS}
        elif cmd.name == "attack" and cmd.arg in ATTACKS:
            s.attack, s.attack_until = cmd.arg, now + ATTACK_S
        elif cmd.name == "fault" and cmd.arg in FAULTS:
            s.faults.symmetric_difference_update({cmd.arg})      # toggles
        elif cmd.name == "mode" and cmd.arg:
            ch, _, mode = cmd.arg.partition(":")
            if ch in CHANNELS and mode in ("sim", "live") and (mode == "sim" or self._device_for(ch)):
                s.modes[ch] = mode
        elif cmd.name == "staged":
            s.staged = cmd.arg == "on"

    def _device_for(self, ch: str):
        return self.camera if ch in ("pulse", "face") else self.node

    # -------------------------------------------------------------- input ---
    def _snapshot(self, now: float) -> tuple[SensorSnapshot, str]:
        s = self.state
        base = self.base.next(now)
        if base is None:
            self.base = SimStream(ScenarioType.NORMAL_DRIVING, self.seed + self.k, 0.0, BASE_DURATION_S)
            base = self.base.next(now)
        src = base
        if self.event_stream is not None:
            ev = self.event_stream.next(now)
            src = ev if ev is not None else base
        snap = SensorSnapshot(t=now, camera_t=src.camera_t, imu_t=src.imu_t, seat_t=src.seat_t)
        snap.face_detected, snap.optical_snr_db = src.face_detected, src.optical_snr_db
        snap.ear, snap.pitch_deg, snap.new_beats = src.ear, src.pitch_deg, list(src.new_beats)
        snap.imu_window_g = src.imu_window_g
        snap.fsr_pressure, snap.grip = src.fsr_pressure, src.grip
        snap.steering_torque_nm, snap.brake_pedal = src.steering_torque_nm, src.brake_pedal
        snap.truth = src.truth
        if self.camera is not None and (s.modes["face"] == "live" or s.modes["pulse"] == "live"):
            live = SensorSnapshot(t=now, camera_t=None, imu_t=None, seat_t=None)
            self.camera.fill(live)
            if s.modes["face"] == "live":
                snap.camera_t, snap.face_detected = live.camera_t, live.face_detected
                snap.optical_snr_db, snap.ear, snap.pitch_deg = live.optical_snr_db, live.ear, live.pitch_deg
            if s.modes["pulse"] == "live":
                snap.new_beats = live.new_beats
        if self.node is not None and (s.modes["imu"] == "live" or s.modes["seat"] == "live"):
            live = SensorSnapshot(t=now, camera_t=None, imu_t=None, seat_t=None)
            self.node.fill(live)
            if s.modes["imu"] == "live":
                snap.imu_t, snap.imu_window_g = live.imu_t, live.imu_window_g
            if s.modes["seat"] == "live":
                snap.seat_t, snap.fsr_pressure, snap.grip = live.seat_t, live.fsr_pressure, live.grip
                snap.steering_torque_nm = live.steering_torque_nm
        # operator-injected faults, applied last
        if "blind" in s.faults:
            # A laser saturates the camera: the face is still found but over-exposed, the pulse
            # disappears and the eyes read closed, while the driver keeps steering (as in the
            # simulator's blinding scenario, unless the seat channel is live).
            snap.optical_snr_db, snap.ear, snap.new_beats = -5.0, 0.05, []
            if s.modes["seat"] == "sim":
                snap.steering_torque_nm = 2.1
        if "imu_drop" in s.faults:
            snap.imu_t, snap.imu_window_g = (snap.imu_t or now) - 1.0, None
        if "seat_freeze" in s.faults:
            snap.seat_t, snap.fsr_pressure, snap.grip = (snap.seat_t or now) - 1.0, None, None
        return snap, src.truth

    # --------------------------------------------------------------- cycle ---
    def step(self, now: float) -> dict:
        """One 100 ms cycle at engine time ``now`` (seconds, any monotonic origin)."""
        while not self.commands.empty():
            self._apply(self.commands.get_nowait(), now)
        if self.t0 is None:
            self.t0 = now
        s = self.state
        self.k += 1
        snap, truth = self._snapshot(now)
        self.vehicle.notifier.primary.up = "cellular_down" not in s.faults
        self.bus.cycle = []
        d = self.ecu.step(snap, self.vehicle.speed_ms, self.bus, hang="ecu_hang" in s.faults)
        if self.bus.cycle and self.bus.cycle[-1][0] == MRM_CMD_ID:
            self.genuine.append(self.bus.cycle[-1][1])
            del self.genuine[:-200]
        self._inject_attack(now)
        frames = list(self.bus.cycle)
        gw = self.vehicle.gateway
        n_before = gw.n_verdicts
        g = self.vehicle.step(now, self.bus, self.ecu, driver_brake=snap.brake_pedal)
        n_new = gw.n_verdicts - n_before
        new_verdicts = list(gw.verdicts)[-n_new:] if n_new else []
        self.distance_m += self.vehicle.speed_ms * config.FUSION_DT
        # the gateway reads frames in bus order, so the i-th new verdict belongs to the i-th frame
        verdicts = [v[2] for v in new_verdicts] + ["-"] * (len(frames) - len(new_verdicts))
        rel = now - self.t0
        rows = [self._can_row(rel, arb, data, sender, verdict) for (arb, data, sender), verdict in zip(frames, verdicts)]
        if self.k % 10 == 0:
            rows.append(self._telematics_row(rel))
        rec = self._record(now, snap, truth, d, g, rows)
        if self.record_path is not None:
            self._write(rec)
        return rec

    def _inject_attack(self, now: float) -> None:
        s = self.state
        if s.attack is None or now > s.attack_until:
            s.attack = None
            return
        stop = MRMCommand(phase=3, active=True, hazards=True, decel_mss=-4.0, etiology="Seizure", shoulder=True)
        if s.attack == "forge":                        # an attacker without the key
            self.bus.send(MRM_CMD_ID, self.attacker.frame(stop), "ATTACKER")
        elif s.attack == "replay" and len(self.genuine) > 30:
            self.bus.send(MRM_CMD_ID, self.genuine[-30], "ATTACKER")        # a frame captured 3 s ago
        elif s.attack == "tamper" and self.genuine:
            g = bytearray(self.genuine[-1])
            g[0] ^= 0x0B                                 # flip phase/active bits of a copied frame
            g[4] = (g[4] + 1) & 0xFF                     # claim the next freshness value
            self.bus.send(MRM_CMD_ID, bytes(g), "ATTACKER")
        elif s.attack == "implausible":                # a compromised ECU: valid key, impossible command
            self.bus.send(MRM_CMD_ID, self.ecu.tx.frame(stop), "ECU (compromised)")

    # ------------------------------------------------------------- record ---
    @staticmethod
    def _can_row(t: float, arb: int, data: bytes, sender: str, verdict: str) -> dict:
        row = {"t": round(t, 2), "id": f"0x{arb:03X}", "sender": sender, "fv": data[4] if len(data) == 8 else None,
               "mac": data[5:8].hex().upper() if len(data) == 8 else "", "verdict": verdict}
        if arb == MRM_CMD_ID and len(data) == 8:
            c = decode_payload(data[:4])
            row["name"] = "MRM_Cmd"
            row["signals"] = (f"phase={c.phase} decel={c.decel_mss:+.1f} haz={int(c.hazards)} epb={int(c.epb)} "
                              f"shoulder={int(c.shoulder)} etio={c.etiology}")
        elif arb == HEALTH_ID and len(data) == 8:
            h = decode_health(data[:4])
            row["name"] = "Health"
            row["signals"] = (f"cam={int(h.camera_ok)} imu={int(h.imu_ok)} seat={int(h.fsr_ok)} "
                              f"degraded={h.degraded_level} overruns={h.deadline_overruns}")
        else:
            row["name"], row["signals"] = "?", data.hex().upper()
        return row

    def _telematics_row(self, t: float) -> dict:
        n = self.vehicle.notifier
        last = n.log[-1][1] if n.log else "None"
        return {"t": round(t, 2), "id": "0x122", "sender": "Telematics", "fv": None, "mac": "",
                "name": "Telematics_Status", "verdict": "status (not authenticated)",
                "signals": f"DENM cause={93 if self.vehicle.denm_sent else 0} sub=0 MEC={n.state} "
                           f"attempts={n.attempts} bearer={last}"}

    def _provenance(self) -> dict:
        s, tags = self.state, {}
        for ch in CHANNELS:
            if s.modes[ch] == "live":
                tags[ch] = {"class": "LIVE", "detail": "webcam" if ch in ("pulse", "face") else "ESP32 sensor node"}
            else:
                scen = (EVENTS[s.event].value if s.event else ScenarioType.NORMAL_DRIVING.value)
                tags[ch] = {"class": "SYNTHETIC", "detail": scen}
        injected = sorted(s.faults) + ([f"attack:{s.attack}"] if s.attack else [])
        return {"channels": tags, "injected": injected, **self.provenance_static}

    def _record(self, now, snap, truth, d, g, rows) -> dict:
        ecu, veh, s = self.ecu, self.vehicle, self.state
        f = getattr(ecu, "features", None)
        card = f.cardiac if f else None
        mot = f.motion if f else None
        imu = snap.imu_window_g
        rec = {
            "k": self.k, "t": round(now - self.t0, 2),
            "provenance": self._provenance(),
            "event": {"kind": s.event, "onset_in_s": None if s.event_onset_t is None else round(s.event_onset_t - now, 1),
                      "truth": truth},
            "inputs": {
                "face": bool(snap.face_detected), "ear": snap.ear, "pitch": snap.pitch_deg,
                "snr_db": snap.optical_snr_db,
                "hr_bpm": None if card is None else round(card.hr_bpm, 1),
                "pulse_absent": None if card is None else round(card.pulse_absent, 2),
                "imu_rms_g": None if imu is None else round(float(np.sqrt(np.mean((imu - imu.mean(0)) ** 2))), 4),
                "imu_band_g": None if mot is None else round(mot.band_rms_g, 4),
                "psi": None if not f or f.fusion.psi is None else round(f.fusion.psi, 2),
                "grip": snap.grip, "torque_nm": round(snap.steering_torque_nm, 2), "brake": snap.brake_pedal,
            },
            "health": {"camera": bool(f and f.camera_ok), "imu": bool(f and f.imu_ok), "seat": bool(f and f.seat_ok)},
            "decision": None,
            "ecu": {"alive": not ecu.failed, "compute_ms": round(getattr(ecu, "last_compute_ms", 0.0), 2),
                    "overruns": ecu.overruns},
            "mrm": {"state": ecu.controller.state.name if not ecu.failed else "ECU_FAILED",
                    "timer_s": round(ecu.controller.mrm_timer, 1), "etiology": ecu.controller.confirmed_etiology},
            "vehicle": {"speed_kmh": round(veh.speed_ms * 3.6, 1), "decel": round(g.decel_mss, 2),
                        "lateral_m": round(veh.lateral_m, 2), "distance_m": round(self.distance_m, 1),
                        "hazards": g.hazards, "epb": g.epb, "shoulder": g.shoulder, "phase": g.phase,
                        "ecu_fault": g.ecu_fault, "fail_operational": g.fail_operational,
                        "doors_unlock": bool(getattr(ecu, "last_dyn", None) and ecu.last_dyn.doors_unlocked)},
            "can": rows,
            "counters": {**veh.gateway.rx.secoc.rejected, "implausible": veh.gateway.rejected_implausible},
            "telematics": self._telematics(),
            "log": self._new_log_lines(),
        }
        if d is not None:
            llr = {b: {c: round(v.get(c, 0.0), 2) for c in ("Syncope", "Seizure")} for b, v in d.raw.branch_llr.items()}
            rec["decision"] = {
                "posteriors": {c: round(p, 3) for c, p in d.raw.posteriors.items()},
                "candidate": d.candidate_class, "confidence": round(d.top_confidence, 3),
                "gamma": config.CONFIDENCE_THRESHOLD_GAMMA,
                "persistence_s": round(d.persistence_seconds, 1), "persistence_needed_s": config.VERIFICATION_DURATION_S,
                "trigger": bool(d.mrm_trigger_flag), "mode": d.mode, "degraded": int(d.degraded_level),
                "spoof": bool(d.spoofing_detected), "distrust_s": DISTRUST_S,
                "override_suppressed": bool(d.override_suppressed),
                "corroborating": list(d.corroborating_sensors), "branch_llr": llr,
            }
        return rec

    def _telematics(self) -> dict:
        veh = self.vehicle
        n = veh.notifier
        out = {"state": n.state, "attempts": n.attempts,
               "bearer_log": [(round(t - (self.t0 or 0), 1), b, ok) for t, b, ok in n.log[-8:]],
               "sealed_hex": veh.sealed_mec.hex().upper() if veh.sealed_mec else None,
               "sealed_len": len(veh.sealed_mec) if veh.sealed_mec else 0,
               "mec": None, "denm_sent": len(veh.denm_sent),
               "denm": {"cause": 93, "sub_cause": 0} if veh.denm_sent else None}
        if veh.received_mec:
            m = veh.received_mec[-1]
            out["mec"] = {"etiology": m.etiology, "confidence": round(m.confidence, 2),
                          "latency_ms": m.latency_ms, "sensors_ok": list(m.sensors_ok),
                          "hr_bpm": m.hr_bpm, "seq": m.seq,
                          "not_included": ["identity", "location (in the eCall MSD)", "raw signals or video"]}
        return out

    def _new_log_lines(self) -> list[str]:
        lines = []
        gw = self.vehicle.gateway.state.log
        for t, msg in gw[self._gw_log_seen:]:
            lines.append(f"[gateway {t - (self.t0 or 0):6.1f}] {msg}")
        self._gw_log_seen = len(gw)
        sec = self.ecu.watchdog.security_log
        for line in sec[self._sec_log_seen:]:
            lines.append(f"[watchdog] {line}")
        self._sec_log_seen = len(sec)
        return lines[-20:]

    def _write(self, rec: dict) -> None:
        if self._rec is None:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)
            self._rec = open(self.record_path, "a", encoding="utf-8")
            self._rec.write(to_json({"session": self.provenance_static, "seed": self.seed}) + "\n")
        self._rec.write(to_json(rec) + "\n")
