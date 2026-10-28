# CabinGuard-ADI: Cybersecurity, Threat Model and Privacy Dossier

Version 2.0, Phase 1. Alignment target: ISO/SAE 21434 and UNECE R155 concepts.
This is a research prototype; nothing here is a certification or a legal
compliance finding. Every "verified by" entry names a test or a fault-matrix
case in `prototype/` that exercises the control.

## 1. Assets and trust boundaries

Protected assets:

1. Vehicle actuators (brakes, hazard lights, parking brake, door locks).
2. The driver's physiological and facial data.
3. Integrity and authenticity of the emergency message.
4. The driver's identity and location.

```
 cabin sensors ──TB1── edge host (ECU) ──TB2── CAN bus ──TB3── gateway ── actuators
   camera, IMU,           detection,            untrusted         trusted
   seat, wheel            watchdog, MRM                           boundary
                              │
                              └──TB4── telematics unit ── cellular / SMS ── PSAP
                                                       └── ITS-G5 / C-V2X ── vehicles
```

| Boundary | What crosses it | Trust assumption |
|---|---|---|
| TB1 cabin sensor link | camera frames over USB, 24-byte ESP32 frames over serial | CRC-16 and sequence numbers detect corruption and loss; an attacker with physical access to the cabin wiring is out of scope |
| TB2 ECU to CAN | `0x120` command, `0x121` health | untrusted bus: any node may inject |
| TB3 CAN to gateway | the same frames | the gateway verifies everything before actuating |
| TB4 telematics | MEC to the PSAP, DENM to vehicles | untrusted networks, eavesdroppers assumed |

## 2. STRIDE threats and controls

| STRIDE | Threat | Control (implemented) | Verified by |
|---|---|---|---|
| Spoofing | Forged `0x120` braking command from a compromised node | AES-128-CMAC truncated to 24 bits, AUTOSAR SecOC profile 1 layout (`cabinguard/secoc.py`) | `unauthorized key` fault case, `test_secoc_rejects_tamper_replay_and_wrong_key` |
| Spoofing | Laser blinding or a projected face making the camera report closed eyes or no pulse | Cross-sensor interlock distrusts the camera for 10 s when it contradicts an upright, steering driver; an MRM needs two physical sensors; the camera counts once | `tampered data: optical blinding` fault case, `test_camera_branches_count_as_one_sensor` |
| Tampering | Bit flips or edits of a command frame | MAC check; persistent tampering also trips the 300 ms alive timeout | `tampered CAN frames` fault case |
| Tampering | Authentic key used to send an unsafe command (insider, stolen key) | Gateway plausibility gate: phase order of the state machine, deceleration limited to [-4, 0] m/s² | `unauthorized command, valid MAC` fault case |
| Repudiation | Dispute over who braked | Gateway logs every rejected frame and every timeout; the ECU logs security exceptions | gateway `log`, watchdog `security_log` |
| Information disclosure | Other bus nodes reading driver biometrics | The health frame `0x121` carries sensor status only; no EAR, heart rate or pressure ever goes on the bus | `cabinguard_mrm.dbc` |
| Information disclosure | Eavesdropping on the emergency message | MEC encrypted to the PSAP public key (ephemeral ECDH, HKDF-SHA256, AES-128-GCM); DENM carries cause 93 with sub-cause 0, never the etiology | `test_mec_encryption_to_psap`, `test_denm_carries_no_etiology` |
| Denial of service | Flooding or jamming the command | Alive supervision: fail-silent if the driver drives, fail-operational completion of a started stop | both `processing failure` fault cases |
| Denial of service | No cellular coverage | Retries with 1, 2, 4 s backoff, SMS fallback, store-and-forward every 30 s; the MRM never waits for the network | both `communication failure` fault cases |
| Replay | Re-sending a captured valid command | 64-bit freshness counter at both ends, 8 bits on the wire, reconstruction across wrap; MEC replays rejected by sequence number, timestamp window and signer | `replayed CAN frames` fault case, `test_mec_is_76_bytes_signed_and_minimal` |
| Elevation of privilege | Malformed serial frames from the sensor node | Fixed-size frame parser with resynchronisation and CRC; no variable-length fields | `test_parser_resyncs_counts_crc_errors_and_gaps` |

Open items for a production system: an HSM for key storage, SecOC key
provisioning and freshness-value management by the gateway, secure boot and
signed model files, a real V2X PKI issuing pseudonym certificates, and a
babbling-idiot guard on the CAN transceiver.

## 3. In-vehicle command frame `0x120`

AUTOSAR SecOC profile 1, "24Bit-CMAC-8Bit-FV". The MAC is computed over
`DataID (16 bit) || payload (32 bit) || full freshness value (64 bit)`.

```
byte 0   MRM phase (4 bit), active, hazards, parking brake, door unlock
byte 1   deceleration request, 0.05 m/s² per bit, offset -6.4
byte 2   etiology (3 bit), degraded level (2 bit), spoof interlock, eCall, DENM
byte 3   classifier confidence, 0.01 per bit (7 bit)
byte 4   freshness value, low 8 bits
byte 5-7 truncated AES-128-CMAC
```

The receiver reconstructs the full counter as the smallest value newer than
the last accepted one whose low byte matches; a replay therefore authenticates
against the wrong counter and fails the MAC. The frame is cyclic at 100 ms in
every state, which makes it the ECU alive signal as well.

## 4. Emergency message

The 76-byte Medical Extension Container (MEC) goes only to the PSAP, as
optional additional data next to the eCall minimum set of data (EN 15722),
which already carries the location.

```
offset  length  field
0       1       version (0x02)
1       1       etiology: 0x01 syncope, 0x02 seizure, 0xFF unspecified
2       1       confidence, percent
3       2       latency from first alert, ms
5       1       sensor-health bitmask (camera, IMU, FSR, grip)
6       1       heart rate at the event, bpm (0xFF unknown, 0 = no pulse)
7       1       sequence number
8       4       UTC timestamp, s
12      64      ECDSA P-256 signature (r || s) over bytes 0-11
```

The signing key is pseudonymous: it carries no VIN, plate or name, and in a
deployment would be bound to a short-lived pseudonym certificate. The sealed
message (33-byte ephemeral key, 12-byte nonce, ciphertext and tag) is what
leaves the vehicle; the PSAP rejects it if decryption fails, the signature
does not verify against a trusted key, the timestamp is more than 300 s off,
or the signer and sequence number were already seen.

Nearby vehicles receive a DENM with cause code 93 (humanProblem) and
sub-cause 0 (unavailable), signed with the same pseudonym. The available
sub-causes "heartProblem" and "glycemiaProblem" are deliberately not used.

## 5. Privacy engineering

Objectives, not a GDPR compliance determination; physiological and facial
data are special-category data under GDPR Article 9.

| Principle | Implementation |
|---|---|
| Data minimisation | Only the MEC fields above leave the vehicle, only after an unanswered alert |
| Storage limitation | No video frame or waveform is written anywhere; feature buffers are 10 s and in memory |
| Purpose limitation | Features feed only the safety decision; nothing is logged for profiling |
| Confidentiality on the bus | No biometric value on CAN |
| Confidentiality off the vehicle | MEC encrypted end to end to the PSAP; DENM without the etiology |
| Unlinkability | Pseudonymous signing keys, no identity fields |

The EU General Safety Regulation (2019/2144) requires drowsiness and
distraction warning systems to work without biometric data. CabinGuard
processes physiological signals, so it falls outside that scope and needs its
own legal basis and ethics approval before any trial with drivers.
