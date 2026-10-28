"""Bit-exact encoding of the CabinGuard CAN messages defined in cabinguard_mrm.dbc.

``MSG_CabinGuard_MRM_Cmd`` (0x120) is sent every 100 ms in every state, so it
doubles as the ECU alive signal the vehicle gateway supervises. Bytes 0-3 carry
the command signals, byte 4 the truncated SecOC freshness value and bytes 5-7
the truncated CMAC (AUTOSAR SecOC profile 1 layout). ``MSG_CabinGuard_Health``
(0x121) uses the same layout under its own Data ID and freshness counter.
``MSG_CabinGuard_Telematics_Status`` (0x122) carries no biometric value and no
SecOC fields.
"""
from __future__ import annotations

from dataclasses import dataclass

from .secoc import SecOCReceiver, SecOCSender, SecuredPdu

MRM_CMD_ID = 0x120
SENSOR_STATUS_ID = 0x121
HEALTH_ID = SENSOR_STATUS_ID
TELEMATICS_ID = 0x122
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
    shoulder: bool = False         # request a lateral move to the hard shoulder (active MRM only)


def encode_payload(cmd: MRMCommand) -> bytes:
    raw_decel = int(round((cmd.decel_mss - DECEL_OFFSET) / DECEL_SCALE))
    raw_decel = max(0, min(255, raw_decel))
    b0 = (cmd.phase & 0x0F) | (cmd.active << 4) | (cmd.hazards << 5) | (cmd.epb << 6) | (cmd.doors_unlock << 7)
    b2 = (ETIOLOGY_CODES.get(cmd.etiology, 7) & 0x07) | ((cmd.degraded_level & 0x03) << 3) \
        | (cmd.spoof_interlock << 5) | (cmd.ecall << 6) | (cmd.denm << 7)
    b3 = max(0, min(127, int(round(cmd.confidence * 100)))) | (cmd.shoulder << 7)
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
        shoulder=bool(b3 >> 7 & 1),
    )


class MRMCommandTx:
    """ECU side: encodes and authenticates one command per 100 ms cycle."""

    def __init__(self, key: bytes, data_id: int = MRM_CMD_ID):
        self.secoc = SecOCSender(key, data_id)

    def frame(self, cmd: MRMCommand) -> bytes:
        return self.secoc.protect(encode_payload(cmd)).to_bytes()


class MRMCommandRx:
    """Receiver side: verifies authenticity and freshness, then decodes.

    ``secoc.last_reason`` holds the verdict of the last frame (OK, MAC_FAIL,
    REPLAY or DATA_ID), for logging and the demo's CAN trace.
    """

    def __init__(self, key: bytes, data_id: int = MRM_CMD_ID):
        self.secoc = SecOCReceiver(key, data_id)

    def accept(self, arb_id: int, data: bytes) -> MRMCommand | None:
        if arb_id != self.secoc.data_id or len(data) != 8:
            self.secoc.rejected["data_id"] += 1
            self.secoc.last_reason = "DATA_ID"
            return None
        pdu = SecuredPdu.from_bytes(self.secoc.data_id, data, PAYLOAD_LEN)
        if not self.secoc.verify(pdu):
            return None
        return decode_payload(pdu.payload)


@dataclass(frozen=True)
class HealthStatus:
    """Sensor health only: no EAR, heart rate or pressure ever goes on the bus."""
    camera_ok: bool = True
    imu_ok: bool = True
    fsr_ok: bool = True
    grip_ok: bool = True
    degraded_level: int = 0
    deadline_overruns: int = 0
    posterior_entropy: float = 0.0  # bits, 0.01 resolution


def encode_health(h: HealthStatus) -> bytes:
    b0 = h.camera_ok | (h.imu_ok << 1) | (h.fsr_ok << 2) | (h.grip_ok << 3) | ((h.degraded_level & 0x03) << 4)
    return bytes([b0, max(0, min(255, h.deadline_overruns)),
                  max(0, min(255, int(round(h.posterior_entropy * 100)))), 0])


def decode_health(payload: bytes) -> HealthStatus:
    b0, b1, b2 = payload[:3]
    return HealthStatus(bool(b0 & 1), bool(b0 >> 1 & 1), bool(b0 >> 2 & 1), bool(b0 >> 3 & 1),
                        b0 >> 4 & 0x03, b1, b2 / 100.0)


class HealthTx(MRMCommandTx):
    def __init__(self, key: bytes):
        super().__init__(key, HEALTH_ID)

    def frame(self, h: HealthStatus) -> bytes:  # type: ignore[override]
        return self.secoc.protect(encode_health(h)).to_bytes()


class HealthRx(MRMCommandRx):
    def __init__(self, key: bytes):
        super().__init__(key, HEALTH_ID)

    def accept(self, arb_id: int, data: bytes) -> HealthStatus | None:  # type: ignore[override]
        if arb_id != HEALTH_ID or len(data) != 8:
            self.secoc.rejected["data_id"] += 1
            self.secoc.last_reason = "DATA_ID"
            return None
        pdu = SecuredPdu.from_bytes(HEALTH_ID, data, PAYLOAD_LEN)
        return decode_health(pdu.payload) if self.secoc.verify(pdu) else None


MEC_STATES = {"Idle": 0, "Sending": 1, "Acknowledged": 2, "Queued": 3, "Failed": 4}
BEARERS = {"None": 0, "cellular": 1, "sms": 2}


def encode_telematics(denm_cause: int, denm_subcause: int, mec_state: str, attempts: int, bearer: str) -> bytes:
    """0x122 telematics status, as in the DBC; not authenticated, carries no etiology."""
    b2 = (MEC_STATES.get(mec_state, 0) & 0x07) | ((min(attempts, 31) & 0x1F) << 3)
    return bytes([denm_cause & 0xFF, denm_subcause & 0xFF, b2, BEARERS.get(bearer, 0) & 0x03, 0, 0, 0, 0])
