"""Prototype telematics and message-integrity helpers.

The repository contract is an 8-byte CAN prototype frame and a 76-byte
privacy-conscious MEC.  These are not production AUTOSAR SecOC, ECDSA, HSM,
NG-eCall, or ETSI deployment implementations.
"""
from dataclasses import dataclass
import struct
import time
import hmac
import hashlib
from typing import Dict, Any
from . import config

@dataclass
class CANFDFrame:
    arb_id: int
    dlc: int
    raw_bytes: bytes
    freshness_counter: int
    mac_signature_hex: str

@dataclass
class ETSIDENMMessage:
    station_id: int
    action_id: int
    cause_code: int
    subcause_code: int
    speed_kmh: float
    lane_position_m: float
    raw_bytes: bytes

@dataclass
class MedicalExtensionContainer:
    version: int
    etiology_code: int
    confidence_pct: int
    latency_ms: int
    sensor_mask: int
    timestamp_utc: int
    raw_76_bytes: bytes
    signature_hex: str
    is_gdpr_compliant: bool

class TelematicsEngine:
    """Generate prototype in-vehicle and external telematics messages."""
    def __init__(self, vehicle_secret_key: bytes = b"CabinGuardSecKey2026"):
        self.secret_key = vehicle_secret_key
        self.freshness_counter = 1000
        self._last_verified_counter = 0
        self.station_id = 0x5A88B1

    def generate_can_fd_mrm_frame(self, target_decel: float, hazards_on: bool, mrm_state_code: int) -> CANFDFrame:
        """
        Prototype MRM command for the CabinGuard DBC.

        The UTF-8/DBC signal map in this project is an 8-byte message, not an
        actual 64-byte CAN-FD payload. This helper keeps the real bus contract in
        sync with the repository definition while preserving a short checksum field
        for validation and telemetry.
        """
        self.freshness_counter += 1

        # Keep the signal map compact enough for the 8-byte DBC frame that the
        # project actually defines: freshness counter, state code, decel request,
        # hazards flag, and a short authenticity checksum.
        payload = struct.pack(
            ">BBhB",
            self.freshness_counter & 0xFF,
            mrm_state_code & 0xFF,
            int(round(target_decel * 10.0)),
            int(hazards_on)
        )
        checksum = hmac.new(self.secret_key, payload, hashlib.sha256).digest()[:3]
        frame_bytes = payload + checksum

        return CANFDFrame(
            arb_id=config.CAN_MRM_MSG_ID,
            dlc=8,
            raw_bytes=frame_bytes,
            freshness_counter=self.freshness_counter,
            mac_signature_hex=checksum.hex().upper()
        )

    def verify_can_fd_mrm_frame(self, frame: CANFDFrame) -> bool:
        """Verify the prototype frame, key, length, and monotonic counter.

        This models the receiver-side integrity and replay boundary.  It is not
        a substitute for an AUTOSAR SecOC implementation or a hardware trust
        anchor.
        """
        if frame.arb_id != config.CAN_MRM_MSG_ID or len(frame.raw_bytes) != 8:
            return False
        if frame.dlc != 8 or frame.freshness_counter <= self._last_verified_counter:
            return False

        payload = frame.raw_bytes[:5]
        received_tag = frame.raw_bytes[5:]
        expected_tag = hmac.new(
            self.secret_key, payload, hashlib.sha256
        ).digest()[:3]
        if not hmac.compare_digest(received_tag, expected_tag):
            return False
        if frame.raw_bytes[0] != (frame.freshness_counter & 0xFF):
            return False

        self._last_verified_counter = frame.freshness_counter
        return True

    def generate_etsi_denm_message(self, speed_kmh: float, lateral_pos_m: float) -> ETSIDENMMessage:
        """
        Generates an ETSI ITS-G5 DENM V2V Emergency Stop warning broadcast.
        """
        action_id = 42
        cause = config.ETSI_DENM_CAUSE_CODE         # Cause Code 6 (Emergency Stop)
        subcause = config.ETSI_DENM_SUBCAUSE_CODE   # Sub-cause 1 (Human Medical Crisis)

        # Packed ITS header + Situation + Location container
        header = struct.pack(">IIBBff", self.station_id, action_id, cause, subcause, speed_kmh, lateral_pos_m)

        return ETSIDENMMessage(
            station_id=self.station_id,
            action_id=action_id,
            cause_code=cause,
            subcause_code=subcause,
            speed_kmh=speed_kmh,
            lane_position_m=lateral_pos_m,
            raw_bytes=header
        )

    def generate_76byte_mec(self, etiology_str: str, confidence: float, latency_ms: int = 1850) -> MedicalExtensionContainer:
        """
        Synthesizes the standardized 76-byte Medical Extension Container (MEC).
        Layout:
          Byte 0:     Version (0x01)
          Byte 1:     Etiology Code (0x01: Syncope, 0x02: Seizure, 0xFF: Unspecified)
          Byte 2:     Confidence Score (0-100%)
          Bytes 3-4:  Verification Latency in ms (uint16)
          Byte 5:     Sensor Health Bitmask (0x0F = all 4 sensors healthy)
          Bytes 6-7:  Reserved (0x0000)
          Bytes 8-11: Unix Epoch Timestamp (uint32)
                    Bytes 12-75: prototype HMAC-SHA512 authentication tag (64 bytes)
        Total = 76 Bytes (prototype privacy-minimized format; not a legal compliance finding).
        """
        version = 0x01
        if etiology_str == "Syncope":
            etiology_code = 0x01
        elif etiology_str == "Seizure":
            etiology_code = 0x02
        else:
            etiology_code = 0xFF

        conf_pct = int(min(100, max(0, confidence * 100)))
        sensor_mask = 0x0F  # Camera | IMU | FSR | Touch
        reserved = 0x0000
        timestamp_utc = int(time.time())

        # Pack 12-byte header
        header_12b = struct.pack(">BBBHHBI", version, etiology_code, conf_pct, latency_ms, sensor_mask, reserved, timestamp_utc)

        # Prototype authentication tag; this is not an HSM-backed signature.
        hmac_tag_64b = hmac.new(self.secret_key, header_12b, hashlib.sha512).digest()

        full_mec_76b = header_12b + hmac_tag_64b

        # Length and data-minimization shape only; legal compliance is not
        # established by this prototype.
        is_privacy_minimized = (len(full_mec_76b) == config.MEC_PAYLOAD_SIZE_BYTES)

        return MedicalExtensionContainer(
            version=version,
            etiology_code=etiology_code,
            confidence_pct=conf_pct,
            latency_ms=latency_ms,
            sensor_mask=sensor_mask,
            timestamp_utc=timestamp_utc,
            raw_76_bytes=full_mec_76b,
            signature_hex=hmac_tag_64b.hex().upper(),
            is_gdpr_compliant=is_privacy_minimized
        )

