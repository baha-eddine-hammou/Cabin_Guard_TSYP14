"""Controlled failure and attack scenarios through the full pipeline (synthetic sensors).

Each row of the matrix runs ``--seeds`` simulator seeds and records whether
the system reached the safe outcome the design requires. The sensor signals
are synthetic: this checks the safety and security logic end to end, not
detection accuracy, which ``realdata/evaluate_fusion.py`` measures.
Writes ``results/fault_matrix.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cabinguard.fusion import FusionClassifier  # noqa: E402
from cabinguard.pipeline import run_scenario  # noqa: E402
from cabinguard.simulator import EVENT_ONSET_S, MultimodalSensorSimulator, ScenarioType  # noqa: E402

T = ScenarioType


def _final(r):
    return r.records[-1]


CASES = {
    # name: (scenario, duration, kwargs, check(result) -> bool, expected behaviour)
    "normal driving": (T.NORMAL_DRIVING, 60, {}, lambda r: r.triggered_class == "Normal" and _final(r).speed_kmh > 99,
                       "no manoeuvre"),
    "cardiac syncope": (T.CARDIAC_SYNCOPE, 70, {}, lambda r: r.triggered_class == "Syncope"
                        and _final(r).mrm_state == "PHASE_4_STANDSTILL" and len(r.vehicle.received_mec) == 1 and _final(r).lateral_m < -6.5,
                        "stop on shoulder, verified MEC at PSAP"),
    "convulsive seizure": (T.EPILEPTIC_SEIZURE, 70, {}, lambda r: r.triggered_class == "Seizure"
                           and _final(r).mrm_state == "PHASE_4_STANDSTILL" and len(r.vehicle.received_mec) == 1 and _final(r).lateral_m < -6.5,
                           "stop on shoulder, verified MEC at PSAP"),
    "sensor failure: IMU disconnect": (T.IMU_HARDWARE_FAULT, 40, {}, lambda r: r.triggered_class == "Normal"
                                       and any("IMU lost" in x.mode for x in r.records), "Degraded 2, no manoeuvre"),
    "missing data: seat sensor stale": (T.SEAT_SENSOR_STALE, 40, {}, lambda r: r.triggered_class == "Normal",
                                        "seat branch dropped, no manoeuvre"),
    "tampered data: optical blinding": (T.OPTICAL_BLINDING_ATTACK, 40, {}, lambda r: r.triggered_class == "Normal"
                                        and any(x.spoof for x in r.records), "camera distrusted, no manoeuvre"),
    "processing failure, driver driving": (T.NORMAL_DRIVING, 30, {"ecu_hang_at": 10.0},
                                           lambda r: r.vehicle.gateway.state.ecu_fault
                                           and not r.vehicle.gateway.state.fail_operational
                                           and _final(r).speed_kmh > 99, "fail silent, driver warned"),
    "processing failure during MRM": (T.EPILEPTIC_SEIZURE, 80, {"ecu_hang_at": 32.0},
                                      lambda r: r.vehicle.gateway.state.fail_operational and _final(r).speed_kmh == 0,
                                      "gateway completes the stop"),
    "tampered CAN frames": (T.NORMAL_DRIVING, 20, {"attack": "tamper"},
                            lambda r: r.vehicle.gateway.rx.secoc.rejected["mac"] > 0 and _final(r).speed_kmh > 99,
                            "frames rejected, alive timeout flagged"),
    "replayed CAN frames": (T.NORMAL_DRIVING, 20, {"attack": "replay"},
                            lambda r: r.vehicle.gateway.rx.secoc.rejected["mac"] == r.attack_frames
                            and _final(r).speed_kmh > 99, "every replay rejected"),
    "unauthorized key": (T.NORMAL_DRIVING, 20, {"attack": "forge"},
                         lambda r: r.vehicle.gateway.rx.secoc.rejected["mac"] == r.attack_frames
                         and _final(r).speed_kmh > 99, "every forged frame rejected"),
    "unauthorized command, valid MAC": (T.NORMAL_DRIVING, 20, {"attack": "implausible"},
                                        lambda r: r.vehicle.gateway.rejected_implausible == r.attack_frames
                                        and _final(r).speed_kmh > 99, "plausibility gate rejects"),
    "communication failure: cellular down": (T.CARDIAC_SYNCOPE, 70, {"bearer_outage": (0.0, 1e9, False)},
                                             lambda r: len(r.vehicle.received_mec) == 1
                                             and any(b == "sms" and ok for _, b, ok in r.vehicle.notifier.log),
                                             "MEC delivered by SMS fallback"),
    "communication failure: all bearers 60 s": (T.CARDIAC_SYNCOPE, 110, {"bearer_outage": (0.0, 60.0, True)},
                                                lambda r: len(r.vehicle.received_mec) == 1
                                                and _final(r).mrm_state == "PHASE_4_STANDSTILL",
                                                "stop unaffected, MEC queued then delivered"),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()
    clf = FusionClassifier()
    out = {"scope": "synthetic sensor signals through the full software pipeline", "seeds": args.seeds, "cases": {}}
    cycle_ms = []
    for name, (sc, dur, kw, check, expect) in CASES.items():
        ok, lat = 0, []
        for seed in range(args.seeds):
            r = run_scenario(MultimodalSensorSimulator(sc, dur, seed), classifier=clf, seed=seed, **kw)
            ok += bool(check(r))
            cycle_ms += [x.compute_ms for x in r.records if x.ecu_alive]
            if r.detection_time is not None and sc in (T.CARDIAC_SYNCOPE, T.EPILEPTIC_SEIZURE):
                lat.append(r.detection_time - EVENT_ONSET_S)
        out["cases"][name] = {"expected": expect, "passed": ok, "runs": args.seeds,
                              "median_detection_latency_s": float(np.median(lat)) if lat else None}
        print(f"{name:42s} {ok}/{args.seeds}  {expect}")
    out["cycle_compute_ms"] = {"median": float(np.median(cycle_ms)), "p99": float(np.percentile(cycle_ms, 99)),
                               "max": float(np.max(cycle_ms)), "deadline": 100.0}
    print("cycle compute ms", out["cycle_compute_ms"])
    path = Path(__file__).resolve().parents[1] / "results" / "fault_matrix.json"
    path.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
