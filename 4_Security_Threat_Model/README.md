# 4. Security & Threat Model

The gateway in front of the actuators is the trusted boundary. The CAN bus,
the cellular network and the radio channel are untrusted. Alignment target:
ISO/SAE 21434 and UNECE R155 concepts. This is a research prototype; nothing
here is a certification or a legal compliance finding. Every "verified by"
entry names a test or fault-matrix case in
[`6_Proof_of_Concept_Prototype/prototype`](../6_Proof_of_Concept_Prototype/prototype)
that exercises the control.

![Trust boundaries: the cabin and edge host, the untrusted CAN bus, cellular and radio channels, and the gateway as the trusted boundary in front of the actuators](figures/trust_boundaries.png)

## Assets and trust boundaries

Protected assets: the vehicle actuators (brakes, hazard lights, parking brake,
door locks); the driver's physiological and facial data; the integrity and
authenticity of the emergency message; the driver's identity and location.

| Boundary | What crosses it | Trust assumption |
|---|---|---|
| TB1 cabin sensor link | camera frames over USB, 24-byte ESP32 frames over serial | CRC-16 and sequence numbers detect corruption and loss; an attacker with physical access to the cabin wiring is out of scope |
| TB2 host to CAN | `0x120` command, `0x121` health | untrusted bus: any node may inject |
| TB3 CAN to gateway | the same frames | the gateway verifies everything before actuating |
| TB4 telematics | the medical message to the emergency centre, the DENM to vehicles | untrusted networks, eavesdroppers assumed |

## STRIDE threats and controls

| STRIDE | Threat | Control (implemented) | Verified by |
|---|---|---|---|
| Spoofing | Forged `0x120` braking command from a node without the key | AES-128-CMAC truncated to 24 bits, AUTOSAR SecOC profile 1 (`cabinguard/secoc.py`) | fault case "unauthorized key", `test_secoc_rejects_tamper_replay_and_wrong_key` |
| Spoofing | Laser blinding or a projected face making the camera report closed eyes or no pulse | the camera is distrusted for 10 s when it contradicts an upright, steering driver; a manoeuvre needs two physical sensors and the camera counts once | fault case "optical blinding", `test_camera_branches_count_as_one_sensor` |
| Tampering | Bit flips or edits of a command frame | MAC check; persistent tampering also trips the 300 ms alive timeout | fault case "tampered CAN frames" |
| Tampering | Authentic key used to send an unsafe command | gateway plausibility gate: phase order of the state machine, deceleration limited to 0 to −4 m/s² | fault case "unauthorized command, valid MAC" |
| Repudiation | Dispute over who braked | the gateway logs every rejected frame and timeout; the host logs security events | gateway log, watchdog `security_log` |
| Information disclosure | Other bus nodes reading driver biometrics | the health frame `0x121` carries sensor status only; no eye opening, heart rate or pressure ever goes on the bus | `cabinguard_mrm.dbc` |
| Information disclosure | Eavesdropping on the emergency message | medical message encrypted to the emergency centre's public key (ephemeral ECDH, HKDF-SHA256, AES-128-GCM); the DENM carries cause 93 with sub-cause 0, never the diagnosis | `test_mec_encryption_to_psap`, `test_denm_carries_no_etiology` |
| Denial of service | Flooding or jamming the command | alive supervision: fail-silent while the driver drives, completion of a stop already under way | both "processing failure" fault cases |
| Denial of service | No cellular coverage | retries with 1, 2 and 4 s backoff, SMS fallback, store-and-forward every 30 s; the manoeuvre never waits for the network | both "communication failure" fault cases |
| Replay | Re-sending a captured valid command | 64-bit freshness counter at both ends, 8 bits on the wire, reconstruction across wrap; medical-message replays rejected by sequence number, timestamp window and signer | fault case "replayed CAN frames", `test_mec_is_76_bytes_signed_and_minimal` |
| Elevation of privilege | Malformed serial frames from the sensor node | fixed-size frame parser with resynchronisation and CRC; no variable-length fields | `test_parser_resyncs_counts_crc_errors_and_gaps` |

All 140 fault-matrix runs (14 cases, 10 seeds, synthetic sensors) reached the
required outcome; see [`5_Validation_Benchmarking`](../5_Validation_Benchmarking).

## In-vehicle command frame `0x120`

![Bit layout of the 0x120 command frame: 32-bit payload, 8-bit freshness value, 24-bit MAC](figures/frame_0x120.png)

AUTOSAR SecOC profile 1, "24Bit-CMAC-8Bit-FV". The MAC is computed over
`DataID (16 bit) || payload (32 bit) || full freshness value (64 bit)`.

| Byte | Content |
|---|---|
| 0 | manoeuvre phase (4 bit), active, hazards, parking brake, door unlock |
| 1 | deceleration request, 0.05 m/s² per bit, offset −6.4 |
| 2 | etiology (3 bit), degraded level (2 bit), spoof interlock, eCall request, DENM request |
| 3 | classifier confidence, 0.01 per bit (7 bit), shoulder request (bit 31) |
| 4 | freshness value, low 8 bits |
| 5–7 | truncated AES-128-CMAC |

The receiver reconstructs the full counter as the smallest value newer than
the last accepted one whose low byte matches; a replay therefore authenticates
against the wrong counter and fails the MAC. The frame is cyclic at 100 ms in
every state, which makes it the host's alive signal as well. The layout is
read from `cabinguard_mrm.dbc`; the payload, the database file and the decoder
are tested to agree bit for bit.

## Emergency message

The 76-byte medical extension container (MEC) goes only to the emergency
centre. It travels beside the eCall, not inside its 140-byte minimum set of
data (EN 15722), which already carries the location.

| Offset | Length | Field |
|---|---|---|
| 0 | 1 | version (0x02) |
| 1 | 1 | etiology: 0x01 syncope, 0x02 seizure, 0xFF unspecified |
| 2 | 1 | confidence, percent |
| 3 | 2 | latency from the first alert, ms |
| 5 | 1 | sensor-health bitmask (camera, IMU, seat, grip) |
| 6 | 1 | heart rate at the event, bpm (0xFF unknown, 0 no pulse) |
| 7 | 1 | sequence number |
| 8 | 4 | UTC timestamp, s |
| 12 | 64 | ECDSA P-256 signature (r ‖ s) over bytes 0–11 |

The signing key is pseudonymous: no VIN, plate or name, and in a deployment it
would be bound to a short-lived pseudonym certificate. The sealed message
(33-byte ephemeral key, 12-byte nonce, ciphertext and tag, 137 bytes) is what
leaves the vehicle; the emergency centre rejects it if decryption fails, the
signature does not verify against a trusted key, the timestamp is more than
300 s off, or the signer and sequence number were already seen.

Nearby vehicles receive a DENM with cause code 93 (human problem) and
sub-cause 0 (unavailable), signed with the same pseudonym. The available
sub-causes "heart problem" and "glycemia problem" are deliberately not used.

## Privacy engineering

Objectives, not a GDPR compliance determination; physiological and facial
data are special-category data under GDPR Article 9.

| Principle | Implementation |
|---|---|
| Data minimisation | only the fields above leave the vehicle, and only after an unanswered alert |
| Storage limitation | no video frame or waveform is written anywhere; feature buffers are 10 s, in memory |
| Purpose limitation | features feed only the safety decision; nothing is logged for profiling |
| Confidentiality on the bus | no biometric value on CAN |
| Confidentiality off the vehicle | the medical message is encrypted end to end to the emergency centre; the DENM has no diagnosis |
| Unlinkability | pseudonymous signing keys, no identity fields |

The recitals of the EU General Safety Regulation (2019/2144) say drowsiness
and distraction warning systems should work without biometric data.
CabinGuard processes physiological signals, so it needs its own legal basis
and ethics approval before any trial with drivers.

## Residual risks and open items

- An attacker with physical access to the in-cabin sensor link: the link has a
  CRC against corruption, not authentication.
- A compromised host that holds the CAN key: it passes both gateway checks, and
  since the gateway checks the order of the phases but not their duration, it
  could brake at −4 m/s² within three frames. Phase 2 options are minimum phase
  durations, a gateway-side brake-pedal cancel and a tighter braking cap.
- The demo key is public and kept in software. A production system needs a
  hardware security module for key storage, SecOC key provisioning and
  freshness management by the gateway, secure boot and signed model files, a
  real V2X PKI issuing pseudonym certificates, and a babbling-idiot guard on
  the CAN transceiver.

## Code

`cabinguard/secoc.py` (SecOC sender and receiver), `cabinguard/can_messages.py`
and `cabinguard_mrm.dbc` (frames), `cabinguard/crypto.py` (AES-128-CMAC with the
RFC 4493 self-test), `cabinguard/vehicle_gateway.py` (plausibility gate, alive
supervision), `cabinguard/emergency_link.py` (MEC, ECDSA, ECIES, bearer
failover). Tests: `tests/test_security_comm.py`, `tests/test_shoulder_gateway.py`.

*Figures in this folder are drawn by `6_Proof_of_Concept_Prototype/prototype/experiments/deliverable_figures.py` from the committed results and the paper's equations.*
