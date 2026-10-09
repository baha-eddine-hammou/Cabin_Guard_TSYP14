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
import socket
import threading
import time
import webbrowser
from pathlib import Path

from run_realtime import load_key

ROOT = Path(__file__).resolve().parent
DEVICE_WAIT_S = 6.0          # a Windows camera can take several seconds to deliver its first frame


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_for_devices(camera, node) -> str | None:
    """Wait until every opened device has delivered data; return an error message if one never does."""
    deadline = time.perf_counter() + DEVICE_WAIT_S
    while time.perf_counter() < deadline:
        cam_ok = camera is None or camera.frames > 0
        node_ok = node is None or node.last is not None
        if cam_ok and node_ok:
            time.sleep(2.5 if node is not None else 0.5)      # fill the 2 s IMU window
            return None
        time.sleep(0.1)
    if camera is not None and camera.frames == 0:
        return "no frames from the camera (wrong --camera index, or another app holds it)"
    return "no valid frames from the ESP32 sensor node (wrong --serial port, baud rate or firmware)"


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

    if not port_free(args.port):
        raise SystemExit(f"port {args.port} is in use (another demo still running?); try --port {args.port + 1}")
    key = load_key(args.key_file) if args.key_file else DEMO_KEY
    camera = node = None
    if args.camera is not None:
        from cabinguard.hardware import CameraFrontEnd
        camera = CameraFrontEnd(args.camera)
    if args.serial:
        from cabinguard.hardware import SerialSensorNode
        node = SerialSensorNode(args.serial)
    if camera is not None or node is not None:
        error = wait_for_devices(camera, node)
        if error:
            for dev in (camera, node):
                if dev is not None:
                    dev.close()
            raise SystemExit(error)
    record = None
    if args.record:
        record = ROOT.parent / "data" / "demo_sessions" / time.strftime("%Y%m%d-%H%M%S.jsonl")
    runner = DemoRunner(DemoEngine(key, camera=camera, node=node, record_path=record)).start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"CabinGuard demo on {url}  (Ctrl+C to stop)")
    timer = None
    if not args.no_browser:
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        # the MJPEG stream never ends on its own: bound the graceful shutdown so Ctrl+C always exits
        uvicorn.run(create_app(runner), host="127.0.0.1", port=args.port, log_level="warning",
                    timeout_graceful_shutdown=1)
    finally:
        if timer is not None:
            timer.cancel()
        runner.stop()
        for dev in (camera, node):
            if dev is not None:
                dev.close()


if __name__ == "__main__":
    main()
