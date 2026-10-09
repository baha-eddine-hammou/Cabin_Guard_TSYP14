"""Bench vehicle gateway: listens on CAN, verifies and supervises CabinGuard commands.

Runs on the actuator side of the bus (a second laptop, a Raspberry Pi with an
MCP2515 hat, or the same PC on a virtual channel):

    python run_gateway.py --can socketcan:can0 --key-file secrets/secoc.key

It prints what it would command the brakes, hazards and parking brake to do,
every rejected frame, and the ECU alive-timeout behaviour, using exactly the
``VehicleGateway`` logic the tests exercise.
"""
from __future__ import annotations

import argparse
import time

from cabinguard import config
from cabinguard.hardware import CanBus, clock
from cabinguard.vehicle_gateway import VehicleGateway
from run_realtime import load_key


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--can", default="socketcan:can0")
    ap.add_argument("--key-file")
    ap.add_argument("--speed-kmh", type=float, default=100.0)
    args = ap.parse_args()
    iface, _, chan = args.can.partition(":")
    bus = CanBus(iface, chan or "cabinguard")
    gw = VehicleGateway(load_key(args.key_file))
    speed, t0, k, logged = args.speed_kmh / 3.6, clock(), 0, 0
    try:
        while True:
            k += 1
            t = clock() - t0
            for arb, data in bus.drain():
                gw.receive(t, arb, data)
            s = gw.tick(t, speed)
            speed = max(0.0, speed + s.decel_mss * config.FUSION_DT)
            for when, msg in s.log[logged:]:
                print(f"[{when:7.2f}] {msg}")
            logged = len(s.log)
            if k % 10 == 0:
                print(f"t={t:6.1f} phase={s.phase} decel={s.decel_mss:+.2f} hazards={s.hazards} epb={s.epb} "
                      f"ecu_fault={s.ecu_fault} fail_op={s.fail_operational} v={speed * 3.6:5.1f} km/h "
                      f"rejected={gw.rx.secoc.rejected} implausible={gw.rejected_implausible}")
            time.sleep(max(0.0, t0 + k * config.FUSION_DT - clock()))
    except KeyboardInterrupt:
        bus.close()


if __name__ == "__main__":
    main()
