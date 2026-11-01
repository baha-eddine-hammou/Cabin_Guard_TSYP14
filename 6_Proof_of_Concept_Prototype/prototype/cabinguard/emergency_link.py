"""Emergency notification: signed 76-byte MEC, PSAP verification, bearer failover.

Two audiences get two different messages:

* the public safety answering point (PSAP) receives the Medical Extension
  Container (MEC), signed with a pseudonymous ECDSA P-256 key and encrypted to
  the PSAP's public key (ECIES: ephemeral ECDH, HKDF-SHA256, AES-128-GCM);
* nearby vehicles receive a DENM with cause ``humanProblem`` (93) and sub-cause
  ``unavailable`` (0), so the etiology never leaves the PSAP channel.

The MEC carries no identity, no location (the eCall minimum set of data
already has it) and no raw physiological signal.
"""
from __future__ import annotations

import os
import struct
from collections import deque
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MEC_VERSION = 0x02
MEC_HEADER = struct.Struct(">BBBHBBBI")   # 12 bytes
MEC_LEN = MEC_HEADER.size + 64             # 76 bytes
ETIOLOGY = {"Syncope": 0x01, "Seizure": 0x02}
SENSOR_BITS = {"camera": 0x01, "imu": 0x02, "fsr": 0x04, "grip": 0x08}
FRESHNESS_WINDOW_S = 300

DENM_CAUSE_HUMAN_PROBLEM = 93              # ETSI TS 102 894-2 CauseCodeType
DENM_SUBCAUSE_UNAVAILABLE = 0


@dataclass(frozen=True)
class MEC:
    etiology: str
    confidence: float
    latency_ms: int
    sensors_ok: tuple[str, ...]
    hr_bpm: float | None
    seq: int
    timestamp: int

    def header(self) -> bytes:
        mask = 0
        for name in self.sensors_ok:
            mask |= SENSOR_BITS[name]
        hr = 0xFF if self.hr_bpm is None else max(0, min(254, int(round(self.hr_bpm))))
        return MEC_HEADER.pack(
            MEC_VERSION, ETIOLOGY.get(self.etiology, 0xFF),
            max(0, min(100, int(round(self.confidence * 100)))),
            max(0, min(65535, int(self.latency_ms))), mask, hr, self.seq & 0xFF,
            self.timestamp & 0xFFFFFFFF)

    @classmethod
    def parse_header(cls, raw: bytes) -> "MEC":
        ver, etio, conf, lat, mask, hr, seq, ts = MEC_HEADER.unpack(raw[:MEC_HEADER.size])
        if ver != MEC_VERSION:
            raise ValueError("unsupported MEC version")
        names = {v: k for k, v in ETIOLOGY.items()}
        return cls(names.get(etio, "Unspecified"), conf / 100.0, lat,
                   tuple(n for n, b in SENSOR_BITS.items() if mask & b),
                   None if hr == 0xFF else float(hr), seq, ts)


class PseudonymSigner:
    """Vehicle-side signer with a key that carries no vehicle identity.

    In a deployment the public key would sit in a short-lived pseudonym
    certificate from the V2X PKI; here the PSAP is simply given the key.
    """

    def __init__(self):
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.seq = 0

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self._key.public_key()

    def sign(self, mec: MEC) -> bytes:
        header = mec.header()
        r, s = decode_dss_signature(self._key.sign(header, ec.ECDSA(hashes.SHA256())))
        return header + r.to_bytes(32, "big") + s.to_bytes(32, "big")

    def next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFF
        return self.seq


def _derive(shared: bytes) -> bytes:
    return HKDF(hashes.SHA256(), 16, salt=None, info=b"CabinGuard-MEC").derive(shared)


def seal_for_psap(mec_bytes: bytes, psap_public: ec.EllipticCurvePublicKey) -> bytes:
    eph = ec.generate_private_key(ec.SECP256R1())
    key = _derive(eph.exchange(ec.ECDH(), psap_public))
    nonce = os.urandom(12)
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.CompressedPoint)
    return eph_pub + nonce + AESGCM(key).encrypt(nonce, mec_bytes, eph_pub)


class PSAPReceiver:
    """Decrypts, verifies and de-duplicates incoming MECs."""

    def __init__(self):
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.trusted: list[ec.EllipticCurvePublicKey] = []
        self._seen: set[tuple[bytes, int, int]] = set()
        self.rejected = {"decrypt": 0, "signature": 0, "stale": 0, "replay": 0}

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self._key.public_key()

    def receive(self, sealed: bytes, now: int) -> MEC | None:
        eph_pub, nonce, ct = sealed[:33], sealed[33:45], sealed[45:]
        try:
            peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), eph_pub)
            raw = AESGCM(_derive(self._key.exchange(ec.ECDH(), peer))).decrypt(nonce, ct, eph_pub)
        except (InvalidTag, ValueError):
            self.rejected["decrypt"] += 1
            return None
        return self.verify(raw, now)

    def verify(self, raw: bytes, now: int) -> MEC | None:
        if len(raw) != MEC_LEN:
            self.rejected["signature"] += 1
            return None
        header, sig = raw[:12], raw[12:]
        der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
        signer = None
        for pub in self.trusted:
            try:
                pub.verify(der, header, ec.ECDSA(hashes.SHA256()))
                signer = pub
                break
            except InvalidSignature:
                continue
        if signer is None:
            self.rejected["signature"] += 1
            return None
        mec = MEC.parse_header(header)
        if abs(now - mec.timestamp) > FRESHNESS_WINDOW_S:
            self.rejected["stale"] += 1
            return None
        ident = (signer.public_bytes(serialization.Encoding.X962,
                                     serialization.PublicFormat.CompressedPoint), mec.seq, mec.timestamp)
        if ident in self._seen:
            self.rejected["replay"] += 1
            return None
        self._seen.add(ident)
        return mec


@dataclass
class Bearer:
    """A transmission path. ``up`` and ``loss`` model coverage and packet loss."""
    name: str
    up: bool = True
    loss: float = 0.0
    sent: int = 0

    def transmit(self, rng, payload: bytes, deliver) -> bool:
        self.sent += 1
        if not self.up or rng.random() < self.loss:
            return False
        return deliver(payload)


@dataclass
class EmergencyNotifier:
    """Delivers the sealed MEC with acknowledgement, retry and failover.

    Primary bearer first, retried with exponential backoff; after
    ``max_primary`` failures the SMS bearer is tried; while nothing gets
    through, the message stays queued and is retried every ``queue_retry_s``.
    The vehicle's safety response never waits on any of this.
    """
    primary: Bearer
    fallback: Bearer
    max_primary: int = 4
    base_backoff_s: float = 1.0
    queue_retry_s: float = 30.0
    queue: deque = field(default_factory=deque)
    state: str = "Idle"
    attempts: int = 0
    delivered_at: float | None = None
    _next_try: float = 0.0
    log: list = field(default_factory=list)

    def submit(self, sealed: bytes, t: float) -> None:
        self.queue.append(sealed)
        self.state, self.attempts, self._next_try = "Sending", 0, t

    def step(self, t: float, rng, deliver) -> None:
        if not self.queue or t < self._next_try:
            return
        bearer = self.primary if self.attempts < self.max_primary else self.fallback
        self.attempts += 1
        ok = bearer.transmit(rng, self.queue[0], deliver)
        self.log.append((t, bearer.name, ok))
        if ok:
            self.queue.popleft()
            self.state, self.delivered_at = "Acknowledged", t
        elif self.attempts < self.max_primary:
            self._next_try = t + self.base_backoff_s * 2 ** (self.attempts - 1)
        elif self.attempts == self.max_primary:
            self._next_try = t                     # switch to the fallback now
        else:
            self.state = "Queued"
            self._next_try = t + self.queue_retry_s
            self.attempts = self.max_primary - 1   # next try goes to primary again


def build_denm(station_pseudonym: int, speed_kmh: float, signer: PseudonymSigner) -> bytes:
    """Minimal DENM body: pseudonym, cause, sub-cause, speed, plus ECDSA signature."""
    body = struct.pack(">IBBH", station_pseudonym & 0xFFFFFFFF, DENM_CAUSE_HUMAN_PROBLEM,
                       DENM_SUBCAUSE_UNAVAILABLE, int(max(0.0, speed_kmh) * 10))
    r, s = decode_dss_signature(signer._key.sign(body, ec.ECDSA(hashes.SHA256())))
    return body + r.to_bytes(32, "big") + s.to_bytes(32, "big")
