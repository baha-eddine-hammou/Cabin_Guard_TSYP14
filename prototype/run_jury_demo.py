"""CabinGuard-ADI jury demo: the live dashboard on http://127.0.0.1:8765.

    python run_jury_demo.py                       # everything synthetic, no hardware
    python run_jury_demo.py --camera 0            # live webcam face channel
    python run_jury_demo.py --camera 1 --serial COM5   # USB webcam + ESP32 sensor node
    python run_jury_demo.py --record              # also write data/demo_sessions/<time>.jsonl

Keys in the browser: P scripted 2-minute run, S seizure, Y syncope, F/R/T/I CAN
attacks (forge, replay, tamper, compromised ECU), B/U/H/C faults (blind
camera, IMU unplugged, ECU hang, cellular down), Esc reset, L light/dark.
"""
from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser
from pathlib import Path

from run_realtime import load_key

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--camera", type=int, default=None, help="OpenCV camera index for the live face channel")
    ap.add_argument("--serial", default=None, help="ESP32 sensor node port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--key-file", default=os.environ.get("CABINGUARD_KEY_FILE"))
    ap.add_argument("--record", action="store_true", help="write every cycle to data/demo_sessions/")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    import uvicorn

    from cabinguard.demo.engine import DEMO_KEY, DemoEngine
    from cabinguard.demo.runner import DemoRunner
    from cabinguard.demo.server import create_app

    key = load_key(args.key_file) if args.key_file else DEMO_KEY
    camera = node = None
    if args.camera is not None:
        from cabinguard.hardware import CameraFrontEnd
        camera = CameraFrontEnd(args.camera)
    if args.serial:
        from cabinguard.hardware import SerialSensorNode
        node = SerialSensorNode(args.serial)
    if camera or node:
        time.sleep(2.5)                                   # fill the 2 s IMU window and the camera warm-up
    record = None
    if args.record:
        record = ROOT.parent / "data" / "demo_sessions" / time.strftime("%Y%m%d-%H%M%S.jsonl")
    runner = DemoRunner(DemoEngine(key, camera=camera, node=node, record_path=record)).start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"CabinGuard demo on {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(create_app(runner), host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        runner.stop()
        for dev in (camera, node):
            if dev is not None:
                dev.close()


if __name__ == "__main__":
    main()
