"""CabinGuard-ADI demonstration: one scenario through the full pipeline, printed live.

    python run_demo.py                       # all scenarios, summary table
    python run_demo.py --scenario seizure    # one scenario, live trace
    python run_demo.py --scenario normal --hang 10      # ECU processing failure at t = 10 s
    python run_demo.py --scenario normal --attack forge # CAN attack from t = 5 s
    python run_demo.py --scenario syncope --no-cellular # cellular bearer down

Sensor signals are synthetic (see cabinguard/simulator.py); the detection
models are the ones trained on PhysioNet recordings in experiments/realdata.
"""
from __future__ import annotations

import argparse

from cabinguard.pipeline import run_scenario
from cabinguard.simulator import EVENT_ONSET_S, MultimodalSensorSimulator, ScenarioType

NAMES = {
    "normal": ScenarioType.NORMAL_DRIVING, "syncope": ScenarioType.CARDIAC_SYNCOPE,
    "seizure": ScenarioType.EPILEPTIC_SEIZURE, "blinding": ScenarioType.OPTICAL_BLINDING_ATTACK,
    "imu-fault": ScenarioType.IMU_HARDWARE_FAULT, "seat-stale": ScenarioType.SEAT_SENSOR_STALE,
}


def trace(name: str, args) -> None:
    sim = MultimodalSensorSimulator(NAMES[name], args.duration, args.seed)
    kw = {}
    if args.hang is not None:
        kw["ecu_hang_at"] = args.hang
    if args.attack:
        kw["attack"] = args.attack
    if args.no_cellular:
        kw["bearer_outage"] = (0.0, 1e9, False)
    r = run_scenario(sim, seed=args.seed, **kw)
    print(f"\n=== {NAMES[name].value} ===  (event onset at t = {EVENT_ONSET_S:.0f} s where applicable)")
    last = ""
    for x in r.records:
        line = (f"{x.mode:26s} cand={x.candidate:8s} P(N/Sy/Sz)="
                + "/".join(f"{x.posterior.get(c, 0):.2f}" for c in ("Normal", "Syncope", "Seizure"))
                + f"  {x.mrm_state:18s} v={x.speed_kmh:5.1f} km/h")
        if x.t % 1.0 < 0.05 or line != last:
            if line != last:
                print(f"t={x.t:5.1f}s  {line}")
            last = line
    v = r.vehicle
    print(f"result: class={r.triggered_class}  final speed={r.records[-1].speed_kmh:.1f} km/h  "
          f"gateway fault={v.gateway.state.ecu_fault} fail-operational={v.gateway.state.fail_operational}")
    print(f"        SecOC rejects={v.gateway.rx.secoc.rejected} implausible={v.gateway.rejected_implausible}")
    print(f"        MEC at PSAP={[(m.etiology, m.confidence, m.hr_bpm) for m in v.received_mec]}  "
          f"bearer log={[(round(t, 1), b, ok) for t, b, ok in v.notifier.log]}  DENM sent={len(v.denm_sent)}")
    for line in r.ecu.watchdog.security_log[:3]:
        print("        security:", line)


def summary(args) -> None:
    print(f"{'scenario':42s} {'class':8s} {'final state':20s} speed")
    for name, sc in NAMES.items():
        r = run_scenario(MultimodalSensorSimulator(sc, args.duration, args.seed), seed=args.seed)
        x = r.records[-1]
        print(f"{sc.value:42s} {r.triggered_class:8s} {x.mrm_state:20s} {x.speed_kmh:5.1f} km/h")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", choices=sorted(NAMES))
    ap.add_argument("--duration", type=float, default=70.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--hang", type=float, default=None, help="ECU stops meeting its deadline at this time")
    ap.add_argument("--attack", choices=["tamper", "replay", "forge", "implausible"])
    ap.add_argument("--no-cellular", action="store_true")
    args = ap.parse_args()
    if args.scenario:
        trace(args.scenario, args)
    else:
        summary(args)


if __name__ == "__main__":
    main()
