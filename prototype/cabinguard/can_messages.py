"""Bit-exact encoding of the CabinGuard CAN messages defined in cabinguard_mrm.dbc.

``MSG_CabinGuard_MRM_Cmd`` (0x120) is sent every 100 ms in every state, so it
doubles as the ECU alive signal the vehicle gateway supervises. Bytes 0-3 carry
the command signals, byte 4 the truncated SecOC freshness value and bytes 5-7
the truncated CMAC (AUTOSAR SecOC profile 1 layout).
"""
from __future__ import annotations

from dataclasses import dataclass

from .secoc import SecOCReceiver, SecOCSender, SecuredPdu

MRM_CMD_ID = 0x120
SENSOR_STATUS_ID = 0x121
PAYLOAD_LEN = 4

DECEL_SCALE = 0.05
DECEL_OFFSET = -6.4

ETIOLOGY_CODES = {"None": 0, "Normal": 0, "Syncope": 1, "Seizure": 2, "Unknown": 7}
ETIOLOGY_NAMES = {v: k for k, v in ETIOLOGY_CODES.items() if k != "Normal"}


@dataclass(frozen=True)
class MRMCommand:
    phase: int = 0                 # 0 normal, 1 pre-alert, 2 escalation, 3 active MRM, 4 standstill
    active: bool = False
    hazards: bool = False
    epb: bool = False
    doors_unlock: bool = False
    decel_mss: float = 0.0         # requested longitudinal acceleration, <= 0
    etiology: str = "None"
    degraded_level: int = 0        # 0 nominal, 1 camera lost, 2 IMU lost, 3 minimum
    spoof_interlock: bool = False
    ecall: bool = False
    denm: bool = False
    confidence: float = 0.0        # 0..1.27, 0.01 resolution


def encode_payload(cmd: MRMCommand) -> bytes:
    raw_decel = int(round((cmd.decel_mss - DECEL_OFFSET) / DECEL_SCALE))
    raw_decel = max(0, min(255, raw_decel))
    b0 = (cmd.phase & 0x0F) | (cmd.active << 4) | (cmd.hazards << 5) | (cmd.epb << 6) | (cmd.doors_unlock << 7)
    b2 = (ETIOLOGY_CODES.get(cmd.etiology, 7) & 0x07) | ((cmd.degraded_level & 0x03) << 3) \
        | (cmd.spoof_interlock << 5) | (cmd.ecall << 6) | (cmd.denm << 7)
    b3 = max(0, min(127, int(round(cmd.confidence * 100))))
    return bytes([b0, raw_decel, b2, b3])


def decode_payload(payload: bytes) -> MRMCommand:
    b0, b1, b2, b3 = payload[:PAYLOAD_LEN]
    return MRMCommand(
        phase=b0 & 0x0F,
        active=bool(b0 >> 4 & 1),
        hazards=bool(b0 >> 5 & 1),
        epb=bool(b0 >> 6 & 1),
        doors_unlock=bool(b0 >> 7 & 1),
        decel_mss=round(b1 * DECEL_SCALE + DECEL_OFFSET, 4),
        etiology=ETIOLOGY_NAMES.get(b2 & 0x07, "Unknown"),
        degraded_level=b2 >> 3 & 0x03,
        spoof_interlock=bool(b2 >> 5 & 1),
        ecall=bool(b2 >> 6 & 1),
        denm=bool(b2 >> 7 & 1),
        confidence=(b3 & 0x7F) / 100.0,
    )


class MRMCommandTx:
    """ECU side: encodes and authenticates one command per 100 ms cycle."""

    def __init__(self, key: bytes, data_id: int = MRM_CMD_ID):
        self.secoc = SecOCSender(key, data_id)

    def frame(self, cmd: MRMCommand) -> bytes:
        return self.secoc.protect(encode_payload(cmd)).to_bytes()


class MRMCommandRx:
    """Receiver side: verifies authenticity and freshness, then decodes."""

    def __init__(self, key: bytes, data_id: int = MRM_CMD_ID):
        self.secoc = SecOCReceiver(key, data_id)

    def accept(self, arb_id: int, data: bytes) -> MRMCommand | None:
        if arb_id != MRM_CMD_ID or len(data) != 8:
            self.secoc.rejected["data_id"] += 1
            return None
        pdu = SecuredPdu.from_bytes(self.secoc.data_id, data, PAYLOAD_LEN)
        if not self.secoc.verify(pdu):
            return None
        return decode_payload(pdu.payload)
