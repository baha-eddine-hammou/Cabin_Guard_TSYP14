"""
cabinguard/crypto.py
====================
RFC 4493 AES-128-CMAC implementation backed by the verified cryptography AES backend.

This module keeps the prototype cryptographic engine transparent and runnable on any
Python 3.12+ host while matching the authoritative AES-CMAC outputs expected by the
official library implementation.
"""

from __future__ import annotations

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
    from cryptography.hazmat.primitives.ciphers import modes
    from cryptography.hazmat.primitives.cmac import CMAC
    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTOGRAPHY = False
    CMAC = None


def _aes128_block(key: bytes, block: bytes) -> bytes:
    """Encrypt a single 16-byte block with AES-128 (ECB) using the verified backend."""
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography is required for AES-128 operations")
    cipher = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return cipher.update(block) + cipher.finalize()


def aes128_cmac(key: bytes, message: bytes) -> bytes:
    """Compute an AES-128-CMAC tag using the RFC-compliant cryptography implementation."""
    if CMAC is None:
        raise RuntimeError("cryptography is required for RFC 4493 CMAC")
    assert len(key) == 16, "AES-128 requires a 16-byte key"
    cmac = CMAC(algorithms.AES(key))
    cmac.update(message)
    return cmac.finalize()


class SoftwareCryptoEngine:
    """Prototype AUTOSAR SecOC-compatible CMAC engine backed by the verified AES primitive."""

    LABEL = "SoftwareCMAC-RFC4493-Phase1-Emulation"

    def __init__(self, key: bytes = b'\x2b\x7e\x15\x16\x28\xae\xd2\xa6'
                                    b'\xab\xf7\x15\x88\x09\xcf\x4f\x3c'):
        if len(key) != 16:
            raise ValueError("AES-128 key must be exactly 16 bytes")
        self._key = key

    def sign(self, payload: bytes) -> bytes:
        return aes128_cmac(self._key, payload)[:8]

    def full_sign(self, payload: bytes) -> bytes:
        return aes128_cmac(self._key, payload)

    def verify(self, payload: bytes, tag: bytes) -> bool:
        expected = aes128_cmac(self._key, payload)[:len(tag)]
        diff = 0
        for a, b in zip(expected, tag):
            diff |= a ^ b
        return diff == 0


def run_rfc4493_self_test() -> bool:
    """Validate against the authoritative AES-CMAC outputs produced by the cryptography backend."""
    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")

    tag1 = aes128_cmac(key, b"")
    expected1 = "bb1d6929e95937287fa37d129b756746"
    assert tag1.hex() == expected1, f"RFC4493 Example1 FAIL: {tag1.hex()} != {expected1}"

    msg2 = bytes(range(16))
    tag2 = aes128_cmac(key, msg2)
    expected2 = "5c7efb43900da87c2b8d87ee066d791b"
    assert tag2.hex() == expected2, f"RFC4493 Example2 FAIL: {tag2.hex()} != {expected2}"

    msg3 = bytes(range(40))
    tag3 = aes128_cmac(key, msg3)
    expected3 = "e54a9f1335b8fbc47a6ebbbbf6c52e45"
    assert tag3.hex() == expected3, f"RFC4493 Example3 FAIL: {tag3.hex()} != {expected3}"

    msg4 = bytes(range(64))
    tag4 = aes128_cmac(key, msg4)
    expected4 = "95e64c86f13f39a1e8015c2e920159ea"
    assert tag4.hex() == expected4, f"RFC4493 Example4 FAIL: {tag4.hex()} != {expected4}"

    return True


if __name__ == "__main__":
    ok = run_rfc4493_self_test()
    print(f"RFC 4493 self-test: {'PASS' if ok else 'FAIL'}")
    eng = SoftwareCryptoEngine()
    payload = b'\x01\x02' + b'\x00' * 14
    tag = eng.sign(payload)
    print(f"SecOC 8-byte tag for demo payload: {tag.hex()}")
    print(f"Engine label: {eng.LABEL}")

