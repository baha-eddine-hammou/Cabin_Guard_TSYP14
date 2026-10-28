"""Cycle timing of a recorded demo session, on the machine that ran it.

Run the demo with ``--record`` (and the webcam and ESP32 as on stage), play the
scripted run, close it, then:

    python experiments/demo_timing.py                 # newest file in data/demo_sessions/
    python experiments/demo_timing.py path/to/session.jsonl

Reports the ECU compute time per 100 ms cycle (median, p99, max), the cycle
period on the wall clock and how often it ran late, and writes
``results/demo_timing.json`` with the host it was measured on.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT.parent / "data" / "demo_sessions"
DEADLINE_MS = 100.0
WARMUP_CYCLES = 3                  # first cycles after a start or reset load the models: reported apart


def summarise(lines: list[str]) -> dict:
    head = json.loads(lines[0])
    recs = [json.loads(x) for x in lines[1:] if x.strip()]
    # a reset restarts the cycle counter; time differences are only valid inside one run
    t = np.array([r["t"] for r in recs])
    k = np.array([r["k"] for r in recs])
    period = np.diff(t)[np.diff(k) == 1] * 1000.0
    timed = [(r["k"], r["ecu"]["compute_ms"]) for r in recs if r["ecu"]["compute_ms"] is not None]
    comp = np.array([c for kk, c in timed if kk > WARMUP_CYCLES])
    warm = [c for kk, c in timed if kk <= WARMUP_CYCLES]
    live = sorted({ch for r in recs for ch, v in r["provenance"]["channels"].items() if v["live"]})
    return {
        "session": head.get("session", {}),
        "cycles": len(recs), "live_channels": live,
        "compute_ms": {"median": float(np.median(comp)), "p99": float(np.percentile(comp, 99)),
                       "max": float(comp.max()), "over_deadline": int((comp > DEADLINE_MS).sum()),
                       "warmup_max": float(max(warm)) if warm else None, "warmup_cycles_excluded": WARMUP_CYCLES},
        "period_ms": {"median": float(np.median(period)), "p99": float(np.percentile(period, 99)),
                      "max": float(period.max()), "late_over_150ms": int((period > 150.0).sum())},
        "deadline_ms": DEADLINE_MS,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session", nargs="?", help="session .jsonl (default: newest in data/demo_sessions)")
    a = ap.parse_args()
    path = Path(a.session) if a.session else max(SESSIONS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, default=None)
    if path is None:
        sys.exit(f"no session file in {SESSIONS}; run the demo with --record first")
    out = summarise(path.read_text(encoding="utf-8").splitlines())
    out["file"] = path.name
    out["host"] = {"system": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "python": platform.python_version()}
    c, p = out["compute_ms"], out["period_ms"]
    print(f"{path.name}: {out['cycles']} cycles, live: {', '.join(out['live_channels']) or 'none'}")
    print(f"ECU compute  median {c['median']:.1f} ms  p99 {c['p99']:.1f} ms  max {c['max']:.1f} ms  "
          f"(over {DEADLINE_MS:.0f} ms: {c['over_deadline']}; first cycles after start, up to {c['warmup_max']:.0f} ms, excluded)")
    print(f"cycle period median {p['median']:.1f} ms  p99 {p['p99']:.1f} ms  max {p['max']:.1f} ms  "
          f"(late by over 50 ms: {p['late_over_150ms']})")
    (ROOT / "results" / "demo_timing.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
