"""SecOC frames, gateway supervision, signed MEC and bearer failover."""
import random
from pathlib import Path

import pytest

from cabinguard.can_messages import MRM_CMD_ID, MRMCommand, MRMCommandRx, MRMCommandTx, decode_payload, encode_payload
from cabinguard.emergency_link import (
    MEC, MEC_LEN, Bearer, EmergencyNotifier, PSAPReceiver, PseudonymSigner, build_denm, seal_for_psap,
)
from cabinguard.vehicle_gateway import VehicleGateway

KEY = bytes(range(16))
MRM = MRMCommand(phase=3, active=True, hazards=True, decel_mss=-3.2, etiology="Syncope",
                 ecall=True, denm=True, confidence=0.91)


def test_payload_roundtrip():
    assert decode_payload(encode_payload(MRM)) == MRM


def test_dbc_matches_encoder():
    cantools = pytest.importorskip("cantools")
    db = cantools.database.load_file(Path(__file__).resolve().parents[1] / "cabinguard_mrm.dbc")
    frame = MRMCommandTx(KEY).frame(MRM)
    sig = db.decode_message(MRM_CMD_ID, frame, decode_choices=False)
    assert sig["MRM_Phase"] == 3 and sig["Detected_Etiology"] == 1
    assert sig["Decel_Request"] == pytest.approx(-3.2)
    assert sig["Confidence"] == pytest.approx(0.91)
    assert sig["SecOC_FV"] == 1


def test_secoc_rejects_tamper_replay_and_wrong_key():
    tx, rx = MRMCommandTx(KEY), MRMCommandRx(KEY)
    good = tx.frame(MRM)
    tampered = bytes([good[0] ^ 0x01]) + good[1:]
    assert rx.accept(MRM_CMD_ID, tampered) is None
    assert rx.accept(MRM_CMD_ID, good) == MRM
    assert rx.accept(MRM_CMD_ID, good) is None                       # replay
    forged = MRMCommandTx(b"\xAA" * 16).frame(MRM)
    assert rx.accept(MRM_CMD_ID, forged) is None                     # unauthorized key
    assert rx.accept(0x7FF, tx.frame(MRM)) is None                   # wrong identifier


def test_secoc_resynchronises_across_truncation_wrap():
    tx, rx = MRMCommandTx(KEY), MRMCommandRx(KEY)
    for i in range(600):
        frame = tx.frame(MRM)
        if i % 7 == 0:                                               # lose some frames
            continue
        assert rx.accept(MRM_CMD_ID, frame) == MRM


def _drive_gateway(gw, tx, frames, t0=0.0):
    t = t0
    for cmd in frames:
        gw.receive(t, MRM_CMD_ID, tx.frame(cmd))
        t += 0.1
    return t


def test_gateway_rejects_implausible_commands():
    tx, gw = MRMCommandTx(KEY), VehicleGateway(KEY)
    gw.receive(0.0, MRM_CMD_ID, tx.frame(MRMCommand()))
    # Jumping straight from normal driving to full braking is refused even when authentic.
    assert not gw.receive(0.1, MRM_CMD_ID, tx.frame(MRM))
    # A deceleration beyond the limit is refused.
    assert not gw.receive(0.2, MRM_CMD_ID, tx.frame(MRMCommand(phase=1, decel_mss=-6.0)))
    assert gw.rejected_implausible == 2


def test_gateway_fail_silent_and_fail_operational():
    tx, gw = MRMCommandTx(KEY), VehicleGateway(KEY)
    t = _drive_gateway(gw, tx, [MRMCommand()] * 3)
    state = gw.tick(t + 0.5, speed_ms=27.0)                          # ECU silent, driver in control
    assert state.ecu_fault and state.decel_mss == 0.0 and not state.fail_operational

    tx, gw = MRMCommandTx(KEY), VehicleGateway(KEY)
    seq = [MRMCommand()] + [MRMCommand(phase=1, active=True)] + [MRMCommand(phase=2, active=True, hazards=True)] + [MRM]
    t = _drive_gateway(gw, tx, seq)
    state = gw.tick(t + 0.5, speed_ms=20.0)                          # ECU dies mid-manoeuvre
    assert state.fail_operational and state.decel_mss < 0 and state.hazards and state.ecall_requested


def test_mec_is_76_bytes_signed_and_minimal():
    signer = PseudonymSigner()
    mec = MEC("Seizure", 0.93, 2100, ("camera", "imu", "fsr", "grip"), 131.0, signer.next_seq(), 1_700_000_000)
    raw = signer.sign(mec)
    assert len(raw) == MEC_LEN == 76
    psap = PSAPReceiver()
    psap.trusted.append(signer.public_key)
    got = psap.verify(raw, now=1_700_000_010)
    assert got.etiology == "Seizure" and got.hr_bpm == 131.0
    assert psap.verify(raw, now=1_700_000_011) is None               # replay
    assert psap.verify(raw[:5] + b"\x00" + raw[6:], now=1_700_000_010) is None  # tamper
    stale = signer.sign(MEC("Syncope", 0.9, 2000, (), None, signer.next_seq(), 1_600_000_000))
    assert psap.verify(stale, now=1_700_000_000) is None


def test_mec_encryption_to_psap():
    signer, psap = PseudonymSigner(), PSAPReceiver()
    psap.trusted.append(signer.public_key)
    raw = signer.sign(MEC("Syncope", 0.88, 2400, ("fsr",), 38.0, signer.next_seq(), 100))
    sealed = seal_for_psap(raw, psap.public_key)
    assert raw not in sealed
    assert psap.receive(sealed, now=100).etiology == "Syncope"
    assert psap.receive(sealed[:-1] + bytes([sealed[-1] ^ 1]), now=100) is None
    assert psap.rejected["decrypt"] == 1


def test_denm_carries_no_etiology():
    denm = build_denm(0x1234, 50.0, PseudonymSigner())
    assert denm[4] == 93 and denm[5] == 0


def test_notifier_retries_then_falls_back_then_queues():
    rng = random.Random(0)
    delivered = []
    primary, sms = Bearer("cellular", up=False), Bearer("sms", up=False)
    n = EmergencyNotifier(primary, sms)
    n.submit(b"mec", 0.0)
    t = 0.0
    while t < 20.0:
        n.step(t, rng, lambda p: delivered.append(p) or True)
        t += 0.1
    assert n.state == "Queued" and primary.sent == 4 and sms.sent == 1
    sms.up = True                                                   # coverage returns
    while t < 80.0 and n.state != "Acknowledged":
        n.step(t, rng, lambda p: delivered.append(p) or True)
        t += 0.1
    assert n.state == "Acknowledged" and delivered == [b"mec"]
