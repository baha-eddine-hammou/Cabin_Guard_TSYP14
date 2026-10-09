"""Jury demo engine: scripted events end on the shoulder, attacks get the right verdicts, reset is clean."""
import json

import pytest

from cabinguard.demo.engine import DemoEngine, to_json
from cabinguard.demo.runner import PHASE_CUES, SCRIPT, DemoRunner


def run(engine, t, seconds):
    rec = None
    for _ in range(int(round(seconds / 0.1))):
        rec = engine.step(t)
        to_json(rec)                                     # every cycle must reach the dashboard as strict JSON
        t += 0.1
    return rec, t


@pytest.mark.parametrize("event", ["seizure", "syncope"])
def test_event_ends_stopped_on_shoulder(event):
    e = DemoEngine()
    rec, t = run(e, 100.0, 2.0)
    assert rec["mrm"]["state"] == "NORMAL"
    e.submit("event", event)
    rec, t = run(e, t, 45.0)
    assert rec["mrm"]["state"] == "PHASE_4_STANDSTILL"
    v = rec["vehicle"]
    assert v["speed_kmh"] == 0.0 and v["epb"] and v["shoulder"] and v["lateral_m"] < -6.5
    assert rec["telematics"]["state"] == "Acknowledged"
    assert rec["telematics"]["sealed_len"] == 137
    assert rec["telematics"]["denm"] == {"cause": 93, "sub_cause": 0}
    assert rec["telematics"]["mec"]["etiology"] == {"seizure": "Seizure", "syncope": "Syncope"}[event]
    assert all(tag["class"] == "SYNTHETIC" for tag in rec["provenance"]["channels"].values())


@pytest.mark.parametrize("attack,verdict", [("forge", "MAC_FAIL"), ("replay", "MAC_FAIL"), ("tamper", "MAC_FAIL"),
                                            ("implausible", "IMPLAUSIBLE")])
def test_attack_rejected_and_car_unaffected(attack, verdict):
    e = DemoEngine()
    _, t = run(e, 100.0, 5.0)                            # replay needs frames captured 3 s earlier
    e.submit("attack", attack)
    seen = []
    for _ in range(25):
        rec = e.step(t)
        t += 0.1
        seen += [r["verdict"] for r in rec["can"] if r["sender"] != "ECU" and r["id"] == "0x120"]
        assert rec["vehicle"]["phase"] == 0 and rec["vehicle"]["decel"] == 0.0
    assert seen and set(seen) == {verdict}
    assert f"attack:{attack}" not in rec["provenance"]["injected"]       # it ended after ATTACK_S


def test_genuine_frames_verify_and_rows_use_session_time():
    e = DemoEngine()
    rec, _ = run(e, 5000.0, 3.0)
    ids = {r["id"]: r["verdict"] for r in rec["can"]}
    assert ids == {"0x121": "OK", "0x120": "OK", "0x122": "status (not authenticated)"}
    assert all(0.0 <= r["t"] < 3.0 for r in rec["can"])


def test_faults_toggle_and_reset_is_clean():
    e = DemoEngine()
    _, t = run(e, 100.0, 1.0)
    e.submit("fault", "blind")
    e.submit("attack", "forge")
    rec, t = run(e, t, 1.0)
    assert rec["provenance"]["injected"] == ["blind", "attack:forge"]
    assert rec["inputs"]["snr_db"] == -5.0
    assert rec["counters"]["mac"] > 0
    e.submit("fault", "blind")                           # second press switches it off
    rec, t = run(e, t, 0.1)
    assert "blind" not in rec["provenance"]["injected"]
    e.submit("event", "seizure")
    run(e, t, 20.0)
    e.submit("reset")
    rec, t = run(e, t + 20.0, 0.1)
    assert rec["k"] == 1 and rec["event"]["kind"] is None
    assert rec["mrm"]["state"] == "NORMAL" and rec["vehicle"]["speed_kmh"] == 100.0
    assert rec["counters"]["mac"] == 0 and rec["telematics"]["state"] == "Idle"
    rec, _ = run(e, t, 1.0)                              # the rebuilt gateway accepts the rebuilt ECU's frames
    assert {r["verdict"] for r in rec["can"] if r["id"] in ("0x120", "0x121")} == {"OK"}


def test_ecu_hang_warns_in_normal_driving_and_gateway_finishes_an_mrm():
    e = DemoEngine()
    _, t = run(e, 100.0, 1.0)
    e.submit("fault", "ecu_hang")
    rec, t = run(e, t, 3.0)
    assert rec["mrm"]["state"] == "ECU_FAILED" and rec["decision"] is None
    v = rec["vehicle"]
    assert v["ecu_fault"] and not v["hazards"] and v["decel"] == 0.0 and not v["fail_operational"]

    e.submit("reset")
    rec, t = run(e, t, 1.0)
    e.submit("event", "seizure")
    while rec["vehicle"]["phase"] < 2:
        rec, t = run(e, t, 0.1)
    e.submit("fault", "ecu_hang")
    rec, t = run(e, t, 40.0)
    v = rec["vehicle"]
    assert v["fail_operational"] and v["hazards"] and v["epb"] and v["speed_kmh"] == 0.0


def test_script_plays_in_order_and_cues_follow_phases():
    e = DemoEngine()
    r = DemoRunner(e)
    r.submit("script", "syncope")
    t0 = r._script_t0
    r._play_script(t0 + SCRIPT[-1][0] - 0.01)
    assert r._script_next == len(SCRIPT) - 1 and e.state.event is None
    r._play_script(t0 + SCRIPT[-1][0])
    e.step(t0)
    assert e.state.event == "syncope"
    assert r.cue == SCRIPT[-1][3]
    assert set(PHASE_CUES) == {"PHASE_1_PRE_ALERT", "PHASE_2_ESCALATION", "PHASE_3_ACTIVE_MRM", "PHASE_4_STANDSTILL"}
    r.submit("reset")
    assert r._script_t0 is None and r.cue == "Ready"


def test_server_page_socket_and_command_filter():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from cabinguard.demo.server import create_app

    e = DemoEngine()
    runner = DemoRunner(e)
    runner.latest = e.step(100.0)
    client = TestClient(create_app(runner))
    page = client.get("/")
    assert page.status_code == 200 and "app.js" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/video.mjpg").status_code == 404              # no camera attached
    with client.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text())["k"] == 1
        ws.send_text(json.dumps({"cmd": "fault", "arg": "blind"}))
        ws.send_text(json.dumps({"cmd": "shutdown"}))                 # not in ALLOWED: dropped
        ws.send_text(json.dumps({"cmd": "event", "arg": ["seizure"]}))  # non-string argument: dropped
        ws.send_text(json.dumps(["event", "seizure"]))                  # not an object: dropped
        ws.send_text(json.dumps({"cmd": "event", "arg": "seizure"}))
    cmds = []
    while not e.commands.empty():
        cmds.append(e.commands.get_nowait())
    assert [(c.name, c.arg) for c in cmds] == [("fault", "blind"), ("event", "seizure")]
