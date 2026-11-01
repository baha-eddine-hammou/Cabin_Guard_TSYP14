"""Paper figure: the Detection panel of the live dashboard during the scripted seizure run.

Starts the demo on synthetic signals (no camera, no ESP32), plays the scripted
seizure run in a headless browser with the light theme, waits until the
seizure is confirmed with all three physical sensors agreeing, and saves the
panel at print resolution to ``figures/dashboard_detection.png``.

Needs the demo extras and Playwright with Chromium:
    pip install -e ".[demo]" playwright && playwright install chromium
    python experiments/dashboard_figure.py
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "figures" / "dashboard_detection.png"


def free_port() -> int:
    """A port nobody holds now (a fixed one can still be closing from the previous run)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, timeout_s: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise TimeoutError(f"demo did not start on port {port}")


def main(executable: str | None = None) -> None:
    from playwright.sync_api import sync_playwright
    port = free_port()
    demo = subprocess.Popen([sys.executable, str(ROOT / "run_jury_demo.py"), "--no-browser", "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_port(port)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
            pg = b.new_page(viewport={"width": 1536, "height": 864}, device_scale_factor=3)
            pg.goto(f"http://127.0.0.1:{port}/?theme=light")
            pg.wait_for_timeout(1500)
            pg.click("text=2-min run: seizure")
            # confirmed seizure, every physical sensor agreeing: the state the figure explains
            pg.wait_for_function("""() => {
                const c = document.getElementById('corro').textContent, l = document.getElementById('persistLabel').textContent;
                return c.includes('Seizure') && c.includes('3 of 3') && l.includes('confirmed'); }""", timeout=90000)
            pg.wait_for_timeout(300)
            OUT.parent.mkdir(exist_ok=True)
            box = pg.locator("section.decision").bounding_box()
            end = pg.locator("#corro").bounding_box()          # crop the panel's empty space under the last line
            pg.screenshot(path=str(OUT), clip={"x": box["x"], "y": box["y"], "width": box["width"],
                                               "height": end["y"] + end["height"] + 10 - box["y"]})
            b.close()
        print("wrote", OUT)
    finally:
        demo.terminate()
        demo.wait(timeout=10)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
