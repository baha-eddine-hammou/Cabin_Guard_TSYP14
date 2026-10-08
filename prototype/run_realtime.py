"""Real-time CabinGuard ECU loop (Phase 2 entry point).

    # all-software, wall-clock paced, gateway in the same process
    python run_realtime.py --source sim --scenario seizure

    # bench: ESP32 node + webcam, ECU frames on a real CAN interface; run
    # run_gateway.py on the actuator side of the same bus
    python run_realtime.py --source hardware --serial /dev/ttyUSB0 --camera 0 \
        --can socketcan:can0 --key-file secrets/secoc.key

The loop runs every 100 ms, measures each cycle's compute time against that
deadline and reports latency percentiles at exit. The ECU goes fail-silent
after three consecutive overruns, exactly as in the simulated fault tests.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np

from cabinguard import config
from cabinguard.pipeline import Bus, CabinGuardECU, VehicleSide
from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType

DEMO_KEY = bytes(range(16))
SCENARIOS = {"normal": ScenarioType.NORMAL_DRIVING, "syncope": ScenarioType.CARDIAC_SYNCOPE,
             "seizure": ScenarioType.EPILEPTIC_SEIZURE, "blinding": ScenarioType.OPTICAL_BLINDING_ATTACK,
             "imu-fault": ScenarioType.IMU_HARDWARE_FAULT}


def load_key(path: str | None) -> bytes:
    if path:
        key = bytes.fromhex(Path(path).read_text().strip())
        if len(key) != 16:
            raise SystemExit("key file must hold 32 hex characters (AES-128)")
        return key
    print("WARNING: using the public demo SecOC key; provision a real key with --key-file")
    return DEMO_KEY


def make_bus(spec: str):
    if spec == "internal":
        b = Bus()
        return b, b
    from cabinguard.hardware import CanBus
    iface, _, chan = spec.partition(":")
    ecu = CanBus(iface, chan or "cabinguard")
    veh = CanBus(iface, chan or "cabinguard") if iface == "virtual" else None
    return ecu, veh


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=["sim", "hardware"], default="sim")
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--serial", help="ESP32 sensor node port, e.g. /dev/ttyUSB0 or COM5")
    ap.add_argument("--camera", type=int, default=None, help="OpenCV camera index")
    ap.add_argument("--can", default="internal", help="internal | virtual | socketcan:can0 | pcan:PCAN_USBBUS1 ...")
    ap.add_argument("--key-file", default=os.environ.get("CABINGUARD_KEY_FILE"))
    ap.add_argument("--fast", action="store_true", help="do not pace to wall clock (simulation only)")
    args = ap.parse_args()

    key = load_key(args.key_file)
    ecu_bus, veh_bus = make_bus(args.can)
    ecu = CabinGuardECU(key)
    vehicle = VehicleSide(key) if veh_bus is not None else None

    if args.source == "sim":
        frames = iter(MultimodalSensorSimulator(SCENARIOS[args.scenario], args.duration, seed=1))
        source = None
    else:
        from cabinguard.hardware import CameraFrontEnd, HardwareSource, SerialSensorNode
        source = HardwareSource(SerialSensorNode(args.serial) if args.serial else None,
                                CameraFrontEnd(args.camera) if args.camera is not None else None)
        time.sleep(2.5)                                  # fill the 2 s IMU window

    compute_ms, t0, k = [], time.monotonic(), 0
    speed = config.HIGHWAY_CRUISE_SPEED_MS
    try:
        while True:
            k += 1
            if source is None:
                snap = next(frames, None)
                if snap is None:
                    break
            else:
                snap = source.snapshot()
                if snap.t - t0 > args.duration:
                    break
            c0 = time.perf_counter()
            d = ecu.step(snap, vehicle.speed_ms if vehicle else speed, ecu_bus)
            if d is not None:
                compute_ms.append((time.perf_counter() - c0) * 1000)
            if vehicle is not None:
                g = vehicle.step(snap.t, veh_bus, ecu, driver_brake=snap.brake_pedal)
            if k % 10 == 0:
                state = ecu.controller.state.name if not ecu.failed else "ECU_FAILED"
                post = d.raw.posteriors if d else {}
                print(f"t={snap.t - (t0 if source else 0):6.1f}  {d.mode if d else '-':26s} "
                      f"P(N/Sy/Sz)={post.get('Normal', 0):.2f}/{post.get('Syncope', 0):.2f}/{post.get('Seizure', 0):.2f}"
                      f"  {state:18s}" + (f" v={vehicle.speed_ms * 3.6:5.1f} km/h decel={g.decel_mss:+.1f}" if vehicle else ""))
            if not args.fast:
                time.sleep(max(0.0, t0 + k * config.FUSION_DT - time.monotonic()))
    except KeyboardInterrupt:
        pass
    for b in {id(ecu_bus): ecu_bus, id(veh_bus): veh_bus}.values():
        if hasattr(b, "close"):
            b.close()
    ms = np.array(compute_ms or [0.0])
    print(f"\ncycles={ms.size}  compute ms: median={np.median(ms):.2f} p99={np.percentile(ms, 99):.2f} "
          f"max={ms.max():.2f}  deadline={config.FUSION_DT * 1000:.0f}  overruns={ecu.overruns}")
    if vehicle is not None:
        print(f"MEC at PSAP: {[(m.etiology, m.confidence) for m in vehicle.received_mec]}")


if __name__ == "__main__":
    main()
