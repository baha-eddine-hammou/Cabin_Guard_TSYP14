# 2. Proposed System Architecture

Three physical sensors, one edge host, one authenticated command to the
vehicle.

![CabinGuard-ADI architecture: sensing, features, bounded evidence, decision on the edge host, vehicle and emergency](figures/architecture.png)

The diagram is Fig. 1 of the paper in colour: the same blocks, signals and arrows, drawn by `figures/architecture.tex`
(`pdflatex architecture.tex`, then `pdftoppm -png -r 220 -singlefile architecture.pdf architecture`).

## Layers

| Layer | Components | Role |
|---|---|---|
| Sensing | 30 fps camera with 850 nm illumination on the steering column | pulse beat times (rPPG), eye aspect ratio, head pitch |
| | MPU6050 inertial measurement unit (IMU) in the headrest, 100 Hz | seizure motion |
| | force-sensing resistors in the seatback and wheel rim, two capacitive touch pads, steering torque | slump, grip, driver input |
| Node | ESP32 | streams seat, wheel and IMU data in 24-byte frames with sequence number and CRC |
| Edge host | Python package `cabinguard` | features, evidence branches, fusion, watchdog, MRM state machine; inputs older than 300 ms count as missing |
| Vehicle | gateway that owns the actuators | accepts only the authenticated `0x120` command, checks plausibility, supervises the alive signal |
| Telematics | eCall unit, V2X | signed and encrypted medical message to the emergency centre; DENM to nearby vehicles without the diagnosis |

## CAN messages

Defined bit for bit in `cabinguard_mrm.dbc` (in the prototype folder) and
`cabinguard/can_messages.py`, and tested to agree:

| ID | Name | Period | Content |
|---|---|---|---|
| `0x120` | MRM_Cmd | 100 ms | phase, braking request, hazards, parking brake, door unlock, etiology, degraded level, eCall and DENM requests, shoulder request; SecOC freshness and 24-bit MAC |
| `0x121` | Health | 100 ms | sensor OK flags, degraded level, deadline overruns, posterior entropy; SecOC protected |
| `0x122` | Telematics_Status | 1 s | DENM cause codes, emergency-message state and bearer; no biometric value |

## Minimum-risk manoeuvre

Alert with chime and haptic pulse (3 s, the driver can cancel), escalation with
hazards and the emergency call, braking at 3.2 m/s² with a move to the hard
shoulder from 10 s after the alert, then parking brake and door unlock at
standstill. The phase sequence follows the transition demand of UN Regulation
No. 157, with design values of our own.

## Hardware

**Built for Phase 1 and the Phase 2 bench:** a laptop as the edge host, an
ESP32 DevKit (WROOM-32) sensor node with the MPU6050, two FSR 406 force sensors,
two capacitive touch pads and a steering-torque potentiometer, a USB camera
with an 850 nm LED ring, and two USB-CAN adapters for a real 500 kbit/s bus.
Parts list (about 150 EUR without the host), wiring, bring-up and the Phase 2
validation plan are in [`hardware/README.md`](hardware/README.md).

**Target for a vehicle-grade build (concept, not built):**

| Subsystem | Candidate component | Role |
|---|---|---|
| Edge compute | NVIDIA Jetson Orin NX 16 GB on a rugged carrier | runs the edge host |
| Driver camera | global-shutter USB camera with an 850 nm band-pass filter, plus a 4-LED 850 nm ring strobed with the frames | eyes, head pitch, pulse |
| Sensor node | ESP32-S3 | IMU, seat and wheel aggregation at 100 Hz with CRC-16 |
| Headrest IMU | InvenSense MPU-6050 | seizure motion |
| Seat and rim pressure | four Interlink FSR-406 behind a buffered divider and a 25 Hz anti-aliasing filter | slump, grip force |
| Wheel touch | Microchip CAP1298 capacitive controller | hands on the wheel |
| CAN interface | Microchip MCP2518FD controller with NXP TJA1042T transceiver | the `0x120`–`0x122` frames (classic CAN, which the controller also supports) |
| V2X and eCall | C-V2X / ITS-G5 on-board unit | DENM to nearby vehicles, medical message to the emergency centre |
| Power | TI LM5143-Q1 dual buck behind a reverse-polarity and load-dump TVS stage | 12 V board net to 12 V, 5 V and 3.3 V rails |

The estimated cost of this research build is about USD 1,080. None of these
parts is safety-certified as used here.

**Functional-safety target (decomposition pattern, not a certification):**
the safety goal "prevent unwarranted emergency braking" is treated as an ASIL D
target and decomposed per ISO 26262-9 into perception and AI at ASIL B(D), the
cross-sensor watchdog and plausibility logic at ASIL B(D), and the actuation
gateway at ASIL D. The gateway is the element that must hold: it authenticates
every command, bounds the deceleration and supervises the host's alive signal.

## Files

| File | What it is |
|---|---|
| `hardware/README.md` | Phase 2 bench: bill of materials, wiring, bring-up, validation plan |
| `hardware/esp32_sensor_node/esp32_sensor_node.ino` | ESP32 sensor-node firmware |
| `figures/architecture.tex`, `.pdf`, `.png` | the architecture diagram above |
| `figures/*.svg` | early concept diagrams (CAN/V2X frame structure, wiring, software pipeline); the architecture diagram supersedes them where they differ |

Code: [`6_Proof_of_Concept_Prototype/prototype`](../6_Proof_of_Concept_Prototype/prototype)
(`cabinguard/pipeline.py` wires the layers together; `cabinguard/hardware.py`
holds the ESP32 frame parser and the camera front end).
