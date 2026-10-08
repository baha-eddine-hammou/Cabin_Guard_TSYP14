"""SecOC-style authenticated CAN frames (AUTOSAR SecOC profile 1 layout).

Profile 1 ("24Bit-CMAC-8Bit-FV") authenticates a PDU with AES-128-CMAC over
``DataID || payload || FreshnessValue``, truncated to 24 bits, and transmits
only the 8 least significant bits of the freshness value. The receiver keeps
the full 64-bit counter and reconstructs the transmitted value from those 8
bits, accepting a frame only when the reconstructed counter is strictly newer
than the last one it accepted.

This module is a software model of that scheme. Keys live in process memory;
on target hardware they belong in an HSM, which this prototype does not have.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .crypto import aes128_cmac

MAC_BYTES = 3            # 24-bit truncated MAC
FV_BYTES = 1             # 8-bit truncated freshness value
FV_WINDOW = 1 << (8 * FV_BYTES)


@dataclass(frozen=True)
class SecuredPdu:
    """Authentic payload plus the truncated freshness value and MAC."""
    data_id: int
    payload: bytes
    fv_trunc: int
    mac: bytes

    def to_bytes(self) -> bytes:
        return self.payload + bytes([self.fv_trunc]) + self.mac

    @classmethod
    def from_bytes(cls, data_id: int, raw: bytes, payload_len: int) -> "SecuredPdu":
        if len(raw) != payload_len + FV_BYTES + MAC_BYTES:
            raise ValueError("secured PDU has the wrong length")
        return cls(data_id, raw[:payload_len], raw[payload_len], raw[payload_len + 1:])


def _mac(key: bytes, data_id: int, payload: bytes, fv: int) -> bytes:
    msg = struct.pack(">H", data_id) + payload + struct.pack(">Q", fv)
    return aes128_cmac(key, msg)[:MAC_BYTES]


class SecOCSender:
    """Owns the transmit freshness counter for one Data ID."""

    def __init__(self, key: bytes, data_id: int, start_fv: int = 0):
        if len(key) != 16:
            raise ValueError("AES-128 key must be 16 bytes")
        self._key = key
        self.data_id = data_id
        self.fv = start_fv

    def protect(self, payload: bytes) -> SecuredPdu:
        self.fv += 1
        return SecuredPdu(self.data_id, payload, self.fv % FV_WINDOW,
                          _mac(self._key, self.data_id, payload, self.fv))


class SecOCReceiver:
    """Verifies frames for one Data ID and rejects replays and forgeries.

    ``max_gap`` bounds how many frames may be lost between two accepted ones;
    the 8-bit truncated value cannot disambiguate larger gaps, so a receiver
    that has lost sync must resynchronise out of band.
    """

    def __init__(self, key: bytes, data_id: int, last_fv: int = 0, max_gap: int = FV_WINDOW - 1):
        if len(key) != 16:
            raise ValueError("AES-128 key must be 16 bytes")
        self._key = key
        self.data_id = data_id
        self.last_fv = last_fv
        self.max_gap = max_gap
        self.rejected = {"mac": 0, "replay": 0, "data_id": 0}
        self.last_reason = "INIT"      # verdict of the last frame: OK, MAC_FAIL, REPLAY or DATA_ID

    def reconstruct(self, fv_trunc: int) -> int:
        """Smallest counter newer than ``last_fv`` whose low byte equals ``fv_trunc``."""
        base = self.last_fv - (self.last_fv % FV_WINDOW)
        candidate = base + fv_trunc
        if candidate <= self.last_fv:
            candidate += FV_WINDOW
        return candidate

    def verify(self, pdu: SecuredPdu) -> bool:
        if pdu.data_id != self.data_id:
            self.rejected["data_id"] += 1
            self.last_reason = "DATA_ID"
            return False
        fv = self.reconstruct(pdu.fv_trunc)
        if fv - self.last_fv > self.max_gap:
            self.rejected["replay"] += 1
            self.last_reason = "REPLAY"
            return False
        expected = _mac(self._key, pdu.data_id, pdu.payload, fv)
        diff = 0
        for a, b in zip(expected, pdu.mac):
            diff |= a ^ b
        if diff or len(pdu.mac) != MAC_BYTES:
            # A replayed frame reconstructs to a newer counter than the one it
            # was signed with, so it fails here rather than on the counter test.
            self.rejected["mac"] += 1
            self.last_reason = "MAC_FAIL"
            return False
        self.last_fv = fv
        self.last_reason = "OK"
        return True
