# CabinGuard-ADI: Cybersecurity, Threat Model & Privacy Engineering Dossier

**Document Reference:** CG-ADI-SEC-TARA-001  
**Version:** 1.0 (Phase 1 Final Technical Deliverable)  
**Alignment Target:** ISO/SAE 21434 and UNECE R155/R156 concepts; this research prototype is not certified or legally compliant by virtue of this document
**Classification:** Technical Challenge Deliverable — IEEE VTS TSYP14  

---

## 1. Threat Analysis & Risk Assessment (TARA) Overview

Connected automated safety systems operating on vehicle chassis buses face dual-domain attack vectors: **physical/sensor spoofing** in the cabin and **cyber/message tampering** across communication links.

CabinGuard-ADI proposes a **zero-trust-inspired in-cabin architecture** where:
1. No single sensor channel is trusted implicitly.
2. Prototype actuation messages are checked with keyed integrity and a monotonic counter; production AUTOSAR SecOC integration is future work.
3. No raw biometric, facial geometry, or patient identity data is transmitted off the vehicle edge controller.

The current Python implementation does not provide an HSM, ECDSA, secure
boot, encrypted model storage, real wireless DENM/eCall, or a certified
AUTOSAR SecOC endpoint. Controls not implemented in the prototype are marked
as future deployment requirements below.

```
                              TRUST BOUNDARY MAP
  
  [ UNTRUSTED CABIN ]       [ EDGE PROCESSING DOMAIN ]     [ VEHICLE CHASSIS BUS ]
  
  +------------------+     +--------------------------+    +----------------------+
  | Physical Driver  |     |  Edge Prototype (software)|    | Modeled Safety       |
  | Optical Ambience | === |  • Prototype watchdog    | == | Response             |
  | Laser / RF Noise | TB1 |  • Isolated Linux Enclave|TB3 |                      |
  +------------------+     |  • Model Weights (AES256)|    +----------------------+
                           +--------------------------+    +----------------------+
  [ ANALOG TACTILE ]                   ||                  | Electronic Power     |
  +------------------+                 ||                  | Steering (EPS)       |
  | FSR / IMU / Grip | =============== ||                  +----------------------+
  | Sensors          |       TB2       ||                  
  +------------------+                 ||                  [ PUBLIC V2X SPECTRUM ]
                                       ||                  +----------------------+
                                       +================== | ETSI DENM / C-V2X    |
                                              TB4          | 5.9 GHz ITS Band     |
                                                           +----------------------+

  TB1: Cabin Optical Boundary (Laser blinding, projected face deepfakes)
  TB2: Microcontroller Serial Boundary (I2C tap, voltage glitching, wire cut)
  TB3: Chassis CAN-FD Bus Boundary (OBD-II port compromise, frame injection)
  TB4: Wireless Telematics Boundary (Cellular/DSRC eavesdropping, location tracking)
```

---

## 2. STRIDE Threat Matrix Analysis

The system was evaluated against Microsoft STRIDE across all 5 architectural trust boundaries:

| STRIDE Category | Threat ID | Target Asset | Attack Vector & Mechanism | Unmitigated Impact | Inherent Risk | Implemented Countermeasure | Residual Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Spoofing** | TH-S01 | NIR Camera Stream | Laser injection / projector deepfake simulating prolonged eye closure ($EAR < 0.15$) | False highway MRM emergency braking (phantom stop) | **CRITICAL** (CVSS 8.2) | Algorithm 1: Cross-sensor plausibility checks. EAR drop without thoracic FSR slump or rPPG bradycardia/tachycardia is flagged as spoofing; MRM suppressed. | **LOW** (CVSS 2.1) |
| **Spoofing** | TH-S02 | Prototype CAN Bus | Malicious sender broadcasting forged `0x120` MRM Command frames | Unauthorized prototype actuation request | **CRITICAL** (CVSS 8.9) | Prototype HMAC tag and monotonic receiver counter; tampered, replayed, and wrong-key frames are rejected in software. Production gateway validation remains open. | **Unquantified pending vehicle integration** |
| **Tampering** | TH-T01 | IMU Telemetry | Cutting I2C bus wiring or desoldering ground pin to simulate loss of tremor | Failure to differentiate convulsive seizure from normal driving | **HIGH** (CVSS 7.4) | Hardware heartbeat pinging (100 Hz). Missing ACK immediately shifts system to **Degraded Mode 2** (rPPG + FSR + Grip fallback). | **LOW** (CVSS 2.3) |
| **Tampering** | TH-T02 | Classifier configuration | Overwriting Bayesian prior tables or thresholds | Disabling crisis detection or skewing decisions | **HIGH** (CVSS 7.1) | Configuration is source-controlled for the prototype; secure boot, signed artifacts, and protected storage are future deployment requirements. | **Unquantified** |
| **Repudiation** | TH-R01 | Driver Override | Driver claims vehicle braked autonomously when driver actually hit the brakes | Legal liability dispute with OEM | **MEDIUM** (CVSS 4.5) | Tamper-proof circular event data recorder (EDR) logging raw sensor feature vectors, classifier posteriors, and pedal states with monotonic timestamps. | **LOW** (CVSS 1.0) |
| **Information Disclosure** | TH-I01 | Raw Face Video | Eavesdropping on internal USB bus or telematics uplink to steal driver video | Violation of GDPR Art. 9 (sensitive biometric & health data theft) | **CRITICAL** (CVSS 8.1) | Zero raw video storage or external transmission. Video resides strictly in volatile GPU VRAM and is flushed immediately after landmark inference. | **NEGLIGIBLE** (CVSS 0.0) |
| **Information Disclosure** | TH-I02 | Prototype MEC payload | Intercepting a future telematics broadcast to infer medical status | Medical discrimination / tracking driver movements | **HIGH** (CVSS 6.8) | Current prototype contains no identity fields and uses a 64-byte HMAC-derived tag; real pseudonym rotation, wireless confidentiality, and deployment privacy review remain future work. | **Unquantified** |
| **Denial of Service** | TH-D01 | CAN-FD Bus | CAN bus flood with high-priority dominant zero bits ($0x000$) | Safety bus starvation; failure to brake vehicle during true crisis | **CRITICAL** (CVSS 8.5) | Hardware-enforced CAN-FD transceiver RX/TX babbling idiot filter (NXP TJA1042T TXD dominant timeout: $1.2\text{ ms}$). Isolated dedicated safety subnet. | **LOW** (CVSS 2.0) |
| **Elevation of Privilege** | TH-E01 | Sensor MCU | Buffer overflow exploit over ESP32 USB serial link to seize gateway root | Arbitrary injection of synthetic crisis feature vectors | **HIGH** (CVSS 7.6) | Strict framing protocol with static memory buffers, length bounds checking, CRC-16 checksumming, and privilege separation on edge host. | **LOW** (CVSS 1.5) |

---

## 3. Formal Attack Trees with CVSS v3.1 Scoring

### 3.1 Attack Tree 1: Adversarial Optical Blinding & False-Crisis Injection
**Objective:** Induce unauthorized highway emergency braking by falsifying camera symptoms of syncope.  
**Inherent Vector:** `CVSS:3.1/AV:A/AC:L/PR:N/UI:N/S:C/C:N/I:H/A:H` (**Score: 8.7 — Critical**)

```
[ Induce False Emergency Braking via Vision Spoofing ]
                   |
     +-------------+-------------+
     |                           |
[ Laser Overexposure ]     [ Synthetic Eyelid Injection ]
(Class 3B NIR Laser)       (Projector / Transparent Display)
     |                           |
     v                           v
  Blinds Camera Sensor       Triggers EAR < 0.15 Detection
  (Histogram Peak at 255)    (Simulates Prolonged Blinking)
     |                           |
     +-------------+-------------+
                   |
                   v
       [ Algorithm 1 Watchdog Evaluation ]
                   |
         +---------+---------+
         |                   |
   Concordance Check   Optical SNR Test
   • FSR shows normal  • SNR drops to 0.8 dB
     thoracic contact    (Threshold: >3.0 dB)
   • rPPG heart rate   • Contrast gradient
     normal (74 BPM)     collapses
         |                   |
         +---------+---------+
                   |
                   v
     [ SPOOFING INTERLOCK FIRES ]
     • Status: laser_spoofing_detected = True
     • Action: Confidence locked to 0.0
     • Safety: MRM Suppressed, Warning Chime to Driver
     • Outcome: ATTACK NEUTRALIZED
```

---

### 3.2 Attack Tree 2: Malicious CAN-FD Bus Injection & Spoofed MRM Command
**Objective:** Transmit forged `0x120` command frame to Electronic Braking System (EBS) to lock wheels.  
**Inherent Vector:** `CVSS:3.1/AV:P/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H` (**Score: 7.9 — High**)

```
[ Execute Unauthorized Braking via CAN Injection ]
                        |
            [ Access Vehicle OBD-II Port ]
                        |
            [ Inject Frame ID 0x120 ]
                        |
          +-------------+-------------+
          |                           |
  [ Scenario A: Plain CAN ]   [ Scenario B: Prototype verifier ]
  • Forged frame accepted     • Software receiver verifies:
   • Wheels brake abruptly       1. Freshness Value check (FV)
  • DANGEROUS STOP              2. HMAC tag check
                                      |
                                      +--> [ Tag mismatch / counter stale ]
                                      |
                                      v
                               [ FRAME DISCARDED ]
                               • Security Event Logged (SEv_0x120_AuthFail)
                               • Actuator ignores command
                               • ATTACK NEUTRALIZED
```

---

## 4. Implemented Prototype Message Integrity and Future Cryptographic Architecture

The prototype does not implement AUTOSAR Classic SecOC. It uses an
HMAC-SHA256-derived three-byte tag on the 8-byte `0x120` command frame and
tracks a full monotonic counter in the Python receiver object. This models the
intended integrity and replay boundary, but is not sufficient for a production
vehicle gateway.

### 4.1 Frame Structure & Bit Allocation
The implemented `MSG_CabinGuard_MRM_Cmd` (CAN-FD ID `0x120`) carries 8 bytes total payload:

The authoritative prototype layout is: byte 0 low freshness-counter byte,
byte 1 MRM state, bytes 2--3 signed deceleration in tenths of m/s$^2$,
byte 4 hazard flag, and bytes 5--7 a 24-bit HMAC-SHA256-derived tag. The
legacy 64-byte SecOC diagram below is retained only as historical target
architecture material and must not be presented as implemented behavior.

```
+----------------------------------------------------------------------------------+
|                     AUTOSAR SecOC SECURED PDU LAYOUT (64 Bytes)                  |
+----------------------------------------------------------------------------------+
|  Bytes 0 - 31   |  Authentic Payload (Control Signals & Actuator Demands)        |
|                 |  • MRM State (4b), Decel Demand (8b), Steer Demand (9b)        |
|                 |  • Hazard/EPB/Door Flags (4b), Etiology (3b), Confidence (7b)  |
|                 |  • Diagnostics, Mode, Redundancy Status (28b)                  |
|                 |  • Reserved padding (197b)                                     |
+-----------------+----------------------------------------------------------------+
|  Bytes 32 - 35  |  Truncated Freshness Value (FV): Lower 32 bits of 64-bit Trip  |
|                 |  Monotonic Counter (Maintained by Central Gateway FVM)         |
+-----------------+----------------------------------------------------------------+
|  Bytes 36 - 63  |  Truncated Authenticator (MAC): Lower 224 bits of AES-128-CMAC |
|                 |  Generated over [Data ID (16b) || Payload (32B) || Full FV]    |
+----------------------------------------------------------------------------------+
```

### 4.2 Cryptographic Key Management & Root of Trust
- **Prototype key:** The Python demonstrator uses a fixed demonstration secret supplied to `TelematicsEngine`; this key must not be used in a vehicle.
- **Future symmetric design:** A production gateway would require OEM key provisioning, protected storage, freshness management, and a verified SecOC profile.
- **Future V2X design:** Production DENM/eCall signing, pseudonym certificates, key rotation, and secure-element integration require a separate implementation and deployment assessment.

---

## 5. Privacy, GDPR & HIPAA Compliance Architecture

Medical emergency detection in passenger cabins can involve **Special Category Personal Data** under **GDPR Article 9(1)**. This document describes privacy engineering objectives, not a legal compliance determination.

### 5.1 Privacy by Design (PbD) Implementation Matrix

| Requirement | Regulatory Article | System Implementation | Technical Verification |
| :--- | :--- | :--- | :--- |
| **Data Minimization** | GDPR Art. 5(1)(c) | The software prototype passes scalar synthetic features; it does not implement a camera pipeline or prove a 16.6 ms purge. | Prototype data-flow inspection; deployment verification required. |
| **Purpose Limitation** | GDPR Art. 5(1)(b) | Data is processed solely for immediate life-safety preservation during active driving; never used for driver profiling or commercial telematics. | Firmware isolation; dedicated CAN subnet. |
| **Data minimization in telematics** | GDPR Recital 26 is a design reference, not a compliance finding | The prototype MEC omits name, VIN, plate, and medical-record fields. | 76-byte payload-length and field tests in `test_cabinguard.py`. |
| **Location Obfuscation** | Future deployment requirement | The current prototype does not encode location in the MEC. | No implementation evidence yet. |
| **Ephemeral Pseudonymity** | Future deployment requirement | Pseudonymous certificates and rotation are not implemented in the prototype. | No implementation evidence yet. |

### 5.2 Bit-Level Verification of the 76-Byte Medical Extension Container (MEC)

The prototype payload is structured for data minimization. It is not currently transmitted over a real ETSI DENM or NG-eCall service:

```
Offset (Bytes)   Length (Bytes)   Field Description
0                1                Protocol version
1                1                Etiology code
2                1                Confidence percentage
3 - 4            2                Verification latency in milliseconds
5                1                Sensor-health bitmask
6 - 7            2                Reserved bytes
8 - 11           4                UTC Unix timestamp
12 - 75          64               Prototype HMAC-SHA512-derived authentication tag
Total:           76 Bytes (prototype payload length only)
```
