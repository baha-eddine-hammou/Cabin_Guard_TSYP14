"""Paces the demo engine at 100 ms on wall clock and plays the scripted 2-minute run.

The tick thread owns the engine; front ends read ``latest`` (one record per
cycle) and send commands through ``submit``. Cycles are paced against absolute
targets ``t0 + k * 0.1`` on ``time.perf_counter``, as in ``run_realtime.py``.
"""
from __future__ import annotations

import logging
import threading
import time

from .. import config
from .engine import DemoEngine

log = logging.getLogger("cabinguard.demo")

# The jury run: (seconds after "play", command, argument, cue shown to the presenter).
SCRIPT = (
    (0.0, "reset", None, "Cruising at 100 km/h: every panel says where its data comes from"),
    (6.0, "attack", "forge", "An attacker without the key forges a brake command: rejected, car unaffected"),
    (14.0, "event", None, "Event onset (synthetic scenario signals): watch the evidence build"),
)
# Once the event is running, the cue follows the manoeuvre phase the ECU reports.
PHASE_CUES = {
    "PHASE_1_PRE_ALERT": "Two physical sensors agree: chime and haptic pre-alert, the driver can still cancel",
    "PHASE_2_ESCALATION": "No response: hazards on, sealed eCall goes to the emergency centre",
    "PHASE_3_ACTIVE_MRM": "Minimum-risk manoeuvre: braking at 3.2 m/s\u00B2 and steering to the hard shoulder",
    "PHASE_4_STANDSTILL": "Stopped on the shoulder: parking brake, doors unlocked, DENM to nearby vehicles",
}


class DemoRunner:
    def __init__(self, engine: DemoEngine):
        self.engine = engine
        self.latest: dict | None = None
        self.cue = "Ready"
        self.compute_ms: list[float] = []
        self._script_t0: float | None = None
        self._script_event = "seizure"
        self._script_next = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cabinguard-tick")

    def start(self) -> "DemoRunner":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.engine.close()

    def submit(self, name: str, arg: str | None = None) -> None:
        if name == "script":
            self._script_event = arg if arg in ("seizure", "syncope") else "seizure"
            self._script_t0, self._script_next = time.perf_counter(), 0
            return
        if name == "reset":
            self._script_t0 = None
            self.cue = "Ready"
        self.engine.submit(name, arg)

    def _play_script(self, now: float) -> None:
        if self._script_t0 is None:
            return
        while self._script_next < len(SCRIPT) and now - self._script_t0 >= SCRIPT[self._script_next][0]:
            _, name, arg, cue = SCRIPT[self._script_next]
            self.engine.submit(name, arg if name != "event" else self._script_event)
            self.cue = cue
            self._script_next += 1

    def _loop(self) -> None:
        t0, k = time.perf_counter(), 0
        while not self._stop.is_set():
            k += 1
            now = time.perf_counter()
            self._play_script(now)
            try:
                rec = self.engine.step(now)
            except Exception:              # keep pacing: the dashboard shows the clock stopping, the log says why
                log.exception("engine cycle %d failed", self.engine.k)
                time.sleep(config.FUSION_DT)
                continue
            if self._script_t0 is not None and self._script_next == len(SCRIPT):
                self.cue = PHASE_CUES.get(rec["mrm"]["state"], self.cue)
            rec["cue"] = self.cue
            rec["script_running"] = self._script_t0 is not None
            if rec["k"] == 1:              # engine was reset: timing restarts with it
                self.compute_ms.clear()
            if rec["ecu"]["compute_ms"] is not None:          # None while the ECU is failed silent
                self.compute_ms.append(rec["ecu"]["compute_ms"])
                del self.compute_ms[:-3000]
            xs = sorted(self.compute_ms)
            rec["timing"] = {"loop_ms": round((time.perf_counter() - now) * 1000, 2),
                             "compute_p99_ms": round(xs[int(0.99 * (len(xs) - 1))], 2) if xs else None}
            self.latest = rec
            delay = t0 + k * config.FUSION_DT - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1.0:          # fell far behind (debugger, sleep): re-anchor instead of bursting
                t0, k = time.perf_counter(), 0
