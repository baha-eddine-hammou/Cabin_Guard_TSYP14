"""Shoulder request on 0x120, the 0x121 health frame and gateway dispatch."""
from pathlib import Path

import pytest

from cabinguard.can_messages import (HEALTH_ID, MRM_CMD_ID, HealthRx, HealthStatus, HealthTx, MRMCommand,
                                     MRMCommandTx, decode_payload, encode_payload)
from cabinguard.pipeline import run_scenario
from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
from cabinguard.vehicle_gateway import STARTUP_GRACE_S, VehicleGateway

KEY = bytes(range(16))
P3 = MRMCommand(phase=3, active=True, hazards=True, decel_mss=-3.2, etiology="Seizure", shoulder=True,
                confidence=0.95)


def test_shoulder_bit_roundtrips_and_matches_dbc():
    assert decode_payload(encode_payload(P3)).shoulder
    assert not decode_payload(encode_payload(MRMCommand(confidence=1.27))).shoulder
    cantools = pytest.importorskip("cantools")
    db = cantools.database.load_file(Path(__file__).resolve().parents[1] / "cabinguard_mrm.dbc")
    sig = db.decode_message(MRM_CMD_ID, MRMCommandTx(KEY).frame(P3), decode_choices=False)
    assert sig["Shoulder_Req"] == 1 and sig["Confidence"] == pytest.approx(0.95)


def test_health_frame_matches_dbc_and_is_authenticated():
    h = HealthStatus(camera_ok=False, imu_ok=True, fsr_ok=True, grip_ok=False, degraded_level=1,
                     deadline_overruns=2, posterior_entropy=0.42)
    frame = HealthTx(KEY).frame(h)
    assert HealthRx(KEY).accept(HEALTH_ID, frame) == h
    assert HealthRx(b"\x01" * 16).accept(HEALTH_ID, frame) is None
    cantools = pytest.importorskip("cantools")
    db = cantools.database.load_file(Path(__file__).resolve().parents[1] / "cabinguard_mrm.dbc")
    sig = db.decode_message(HEALTH_ID, frame, decode_choices=False)
    assert (sig["Camera_OK"], sig["IMU_OK"], sig["Grip_OK"], sig["Degraded_Level"]) == (0, 1, 0, 1)
    assert sig["Posterior_Entropy"] == pytest.approx(0.42)


def test_gateway_dispatches_by_id_and_records_verdicts():
    gw, tx, htx = VehicleGateway(KEY), MRMCommandTx(KEY), HealthTx(KEY)
    assert gw.receive(0.0, HEALTH_ID, htx.frame(HealthStatus()))
    assert gw.receive(0.0, MRM_CMD_ID, tx.frame(MRMCommand()))
    assert not gw.receive(0.0, 0x7FF, b"\x00" * 8)
    assert gw.rx.secoc.rejected == {"mac": 0, "replay": 0, "data_id": 0}     # health is not an attack
    forger = MRMCommandTx(b"\xAA" * 16)
    forger.frame(MRMCommand())          # FV 1 would equal the last accepted value and read as a replay
    assert not gw.receive(0.1, MRM_CMD_ID, forger.frame(MRMCommand()))
    assert [v for _, _, v in gw.verdicts] == ["OK", "OK", "IGNORED", "MAC_FAIL"]


def test_shoulder_only_plausible_in_active_manoeuvre():
    gw, tx = VehicleGateway(KEY), MRMCommandTx(KEY)
    assert gw.receive(0.0, MRM_CMD_ID, tx.frame(MRMCommand()))
    assert not gw.receive(0.1, MRM_CMD_ID, tx.frame(MRMCommand(shoulder=True)))
    assert gw.verdicts[-1][2] == "IMPLAUSIBLE"


def test_startup_grace_before_first_frame():
    gw = VehicleGateway(KEY)
    assert not gw.tick(0.0, 27.0).ecu_fault
    assert not gw.tick(STARTUP_GRACE_S - 0.1, 27.0).ecu_fault
    assert gw.tick(STARTUP_GRACE_S + 0.2, 27.0).ecu_fault


def test_mrm_ends_stopped_on_the_shoulder():
    r = run_scenario(MultimodalSensorSimulator(ScenarioType.EPILEPTIC_SEIZURE, 70, 1), seed=1)
    final = r.records[-1]
    assert final.mrm_state == "PHASE_4_STANDSTILL" and final.speed_kmh == 0
    assert final.lateral_m == pytest.approx(-7.0, abs=0.3)
    # the lateral move only happens while moving, never after standstill
    moving = [x for x in r.records if x.speed_kmh > 0]
    assert max(abs(b.lateral_m - a.lateral_m) for a, b in zip(r.records, r.records[1:])) <= 0.15 + 1e-9
    assert min(x.lateral_m for x in moving) <= -6.5


def test_normal_driving_stays_in_lane():
    r = run_scenario(MultimodalSensorSimulator(ScenarioType.NORMAL_DRIVING, 30, 1), seed=1)
    assert all(x.lateral_m == 0.0 for x in r.records)
