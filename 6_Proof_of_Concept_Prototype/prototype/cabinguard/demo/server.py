"""Local web server for the jury dashboard: one page, one WebSocket, one MJPEG stream.

Binds to 127.0.0.1 only, so Windows never asks for a firewall exception and no
other machine can drive the demo. The page and its script are served from
``static/``; nothing is loaded from the internet.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .engine import to_json
from .runner import DemoRunner

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED = {"reset", "event", "attack", "fault", "mode", "staged", "script"}
log = logging.getLogger("cabinguard.demo")


def create_app(runner: DemoRunner) -> FastAPI:
    app = FastAPI(title="CabinGuard-ADI demo", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()

        async def push():
            last = None
            while True:
                rec = runner.latest
                if rec is not None and rec is not last:
                    last = rec
                    try:
                        text = to_json(rec)
                    except (TypeError, ValueError):       # skip one bad record, never stop the feed
                        log.exception("record %s not serialisable", rec.get("k"))
                        continue
                    await sock.send_text(text)
                await asyncio.sleep(0.05)

        task = asyncio.create_task(push())
        try:
            while True:
                msg = json.loads(await sock.receive_text())
                arg = msg.get("arg") if isinstance(msg, dict) else None
                if isinstance(msg, dict) and msg.get("cmd") in ALLOWED and (arg is None or isinstance(arg, str)):
                    runner.submit(msg["cmd"], arg)
        except (WebSocketDisconnect, ValueError):
            pass
        finally:
            task.cancel()

    @app.get("/video.mjpg")
    async def video():
        cam = runner.engine.camera
        if cam is None:
            return Response(status_code=404)

        async def frames():
            last = None
            while True:
                jpg = cam.latest_jpeg
                if jpg is not None and jpg is not last:
                    last = jpg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(0.05)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    return app
