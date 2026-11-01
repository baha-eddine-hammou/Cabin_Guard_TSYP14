"""Sensor-node protocol and CAN transport used by the Phase 2 bench."""
import pytest

from cabinguard.hardware import ACC_LSB_PER_G, NodeParser, encode_node_frame, grip_state


def test_node_frame_roundtrip_and_units():
    raw = encode_node_frame(7, 1234, (8192, -4096, 0), 2048, 100, 0b11, 2048 + 410)
    (s,) = NodeParser().feed(raw, host_t=1.0)
    assert s.seq == 7 and s.node_ms == 1234
    assert s.acc_g == pytest.approx((1.0, -0.5, 0.0))
    assert s.fsr == pytest.approx(0.5, abs=1e-3) and s.steer_nm == pytest.approx(2.0, abs=0.01)
    assert len(raw) == 24 and ACC_LSB_PER_G == 8192


def test_parser_resyncs_counts_crc_errors_and_gaps():
    p = NodeParser()
    good = [encode_node_frame(i, i * 10, (0, 0, 8192), 0, 0, 1, 2048) for i in range(5)]
    corrupt = bytearray(good[1])
    corrupt[10] ^= 0xFF
    stream = b"\x00\x13garbage" + good[0] + bytes(corrupt) + good[3] + good[4]
    out = []
    for i in range(0, len(stream), 7):               # arbitrary chunking, as a UART delivers it
        out += p.feed(stream[i:i + 7], 0.0)
    assert [s.seq for s in out] == [0, 3, 4]
    assert p.crc_errors >= 1 and p.lost == 2


def test_grip_state():
    assert grip_state(0, 0) == "DISENGAGED"
    assert grip_state(1, 100) == "ACTIVE"
    assert grip_state(3, 3500) == "CLENCHED"


def test_pipeline_over_python_can_virtual_bus():
    pytest.importorskip("can")
    from cabinguard.hardware import CanBus
    from cabinguard.pipeline import CabinGuardECU, VehicleSide
    from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
    key = bytes(range(16))
    ecu_bus, veh_bus = CanBus("virtual", "test-cg"), CanBus("virtual", "test-cg")
    try:
        ecu, veh = CabinGuardECU(key), VehicleSide(key)
        for snap in MultimodalSensorSimulator(ScenarioType.EPILEPTIC_SEIZURE, 60, 2):
            ecu.step(snap, veh.speed_ms, ecu_bus)
            veh.step(snap.t, veh_bus, ecu)
        assert veh.speed_ms == 0 and veh.gateway.rx.secoc.rejected["mac"] == 0
        assert [m.etiology for m in veh.received_mec] == ["Seizure"]
    finally:
        ecu_bus.close()
        veh_bus.close()


def test_snapshot_from_parsed_samples_matches_simulator_contract():
    from cabinguard.simulator import SensorSnapshot
    s = SensorSnapshot(t=0.0)
    assert {"camera_t", "imu_t", "seat_t", "new_beats", "imu_window_g"} <= set(vars(s))
