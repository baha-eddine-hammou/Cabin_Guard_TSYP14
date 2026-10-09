# CabinGuard-ADI: System Architecture & Hardware Engineering Specification

**Document Reference:** CG-ADI-SPEC-HW-001  
**Version:** 1.0 (Phase 1 Final Technical Deliverable)  
**Classification:** Technical Challenge Deliverable — IEEE VTS TSYP14  
**Safety Integrity Level Target:** Prototype architecture only; ASIL-D-oriented decomposition for future automotive development, not a safety-certified subsystem  
**Security Level Target:** Prototype security model only; not a certified automotive security implementation  

---

## 1. Executive Summary & System Boundary

CabinGuard-ADI is an in-cabin automotive embedded safety system designed to detect acute driver incapacitation (specifically convulsive epileptic seizures and sudden cardiac syncope) and execute an automated, secure Minimum Risk Maneuver (MRM) under UNECE Regulation No. 157.

This document defines the complete electrical, mechanical, and compute hardware specification, sensor pinout mappings, power delivery networks, communication buses, and functional safety partitioning for the physical implementation.

```
+-----------------------------------------------------------------------------------------+
|                                    IN-CABIN ENVIRONMENT                                 |
|                                                                                         |
|  +--------------------+     +-------------------+     +------------------+              |
|  | NIR Global Shutter |     | Headrest 6-Axis   |     | Seatback FSR     |              |
|  | Camera (60 FPS)    |     | IMU (MPU6050)     |     | Pressure Array   |              |
|  +---------+----------+     +---------+---------+     +--------+---------+              |
|            |                          |                        |                        |
|            | USB 3.0 UVC              | I2C (400 kHz)          | Analog (ADC)           |
|            |                          v                        v                        |
|            |                 +---------------------------------------+                  |
|            |                 |    Cabin Sensor Gateway (ESP32-S3)    |                  |
|            |                 |  100 Hz Sampling, Ring-Buffer, CRC-16 |                  |
|            |                 +-------------------+-------------------+                  |
|            |                                     |                                      |
|            |                                     | High-Speed UART / USB-CDC (921.6k)   |
|            v                                     v                                      |
|  +--------------------------------------------------------------------+                 |
|  |               Main Edge AI Controller (NVIDIA Jetson Orin NX 16GB) |                 |
|  |  • Real-Time MediaPipe / TensorRT Landmark Pipeline (60 FPS)       |                 |
|  |  • Welch Spectral Energy Ratio & Postural Slump Index Estimation   |                 |
|  |  • Pulse-rhythm (LogReg) and motion (boosted trees) branches       |                 |
|  |  • Bounded-evidence fusion, watchdog, two-sensor rule, interlock   |                 |
|  |  • SecOC profile 1 (AES-128-CMAC, 24-bit MAC, 8-bit freshness)     |                 |
|  +-----------------------------------+--------------------------------+                 |
|                                      |                                                  |
|                  Isolated SPI Bus    |                                                  |
|                  v                   |                                                  |
|        +-------------------+         | Automotive Ethernet (100BASE-T1)                 |
|        | MCP2518FD / TJA1042|        v                                                  |
|        | CAN-FD Controller |   +------------------------------------+                   |
|        +---------+---------+   | Dual C-V2X / ITS-G5 OBU Telematics |                   |
|                  |             +-----------------+------------------+                   |
|                  | CAN-FD 5 Mbps                 | ETSI DENM / 76-byte MEC              |
+------------------|-------------------------------|--------------------------------------+
                   v                               v
         [ Vehicle CAN-FD Bus ]         [ V2V / V2I 5.9 GHz DSRC ]
         • EBS (Decel: -3.2 m/s²)        • Emergency Vehicle Alert
         • EPS (Lane Pull: -7.0 m)       • Surrounding Traffic Warning
         • BCM (Hazards & Unlocks)       • Hospital Trauma Triage Ingest
```

---

## 2. Complete Bill of Materials (BOM) & Component Selection

All components have been selected for automotive-grade operating temperature ranges (AEC-Q100 Grade 2: $-40^\circ\text{C}$ to $+105^\circ\text{C}$ where applicable) and production COTS availability.

| Subsystem | Component | Part Number / Model | Key Specifications | Interface | Operating Voltage | Unit Cost (USD) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Edge Compute** | Edge AI SOM | NVIDIA Jetson Orin NX 16GB | 100 TOPS (INT8), 1024-core Ampere GPU, 8-core Arm Cortex-A78AE | PCIe, USB 3.2, SPI, UART | 7.0V – 20.0V (15W mode) | $499.00 |
| **Edge Carrier** | Rugged Carrier Board | Connect Tech Hadron / Custom | 2x M.2, 2x GbE, isolated CAN-FD transceiver, automotive locking Hirose headers | Hirose / Micro-Fit | 12.0V DC | $185.00 |
| **Microcontroller** | Sensor Aggregator | Espressif ESP32-S3-WROOM-1 | Dual-core Xtensa LX7 @ 240 MHz, 512KB SRAM, 8MB PSRAM, USB OTG | USB, I2C, ADC, Touch | 3.3V DC (LDO regulated) | $3.80 |
| **Vision Sensing** | NIR Driver Camera | See3CAM_CU27 (OmniVision OV2740) | 1080p @ 60 FPS, global-shutter, integrated 850 nm IR-pass bandpass filter | USB 3.0 UVC | 5.0V DC (USB VBUS) | $95.00 |
| **IR Illumination** | Active NIR Array | Osram SFH 4715AS (4-LED ring) | 850 nm centroid, $90^\circ$ optical half-angle, constant-current strobe sync | Strobe GPIO trigger | 12.0V DC (via buck) | $14.50 |
| **Inertial Sensing**| Headrest IMU | InvenSense MPU-6050 (AEC Grade 3) | 6-axis, $\pm 2g$ accel, 16-bit ADC, programmable 100 Hz digital low-pass filter | I2C (Fast Mode 400 kHz) | 3.3V DC | $4.20 |
| **Pressure Matrix**| Thoracic FSR Array | Interlink Electronics FSR-406 (4x) | $43.7 \times 43.7\text{ mm}$ active area, $0.2\text{ N}$ to $20\text{ N}$ dynamic force | Analog Resistive Divider | 3.3V DC (ADC input) | $28.00 |
| **Steering Touch** | Capacitive Wheel Grip | Microchip CAP1298 (8-channel) | Dual-zone capacitive touch sensor, automatic environmental recalibration | I2C / Discrete IO | 3.3V DC | $1.95 |
| **CAN Interface** | CAN-FD Controller | Microchip MCP2518FD + NXP TJA1042T | Up to 8 Mbps CAN-FD payload, ISO 11898-2:2016 compliant, 2.5 kV isolation | SPI (20 MHz) | 3.3V (VIO) / 5.0V (CAN) | $3.40 |
| **V2X Telematics** | C-V2X / DSRC OBU | Telit Cinterion MV32-W / Cohda MK5 | Dual 5.9 GHz ITS band, GNSS RTK, hardware cryptography concept for future deployment | 100BASE-T1 / USB 3.0 | 12.0V DC | $240.00 |
| **Power Supply** | Automotive Buck Regulator| Texas Instruments LM5143-Q1 | Dual-channel synchronous buck, AEC-Q100, $3.5\text{V}$ to $65\text{V}$ input transient clamp | Fixed DC output | 12V/24V nominal | $6.80 |
| **Prototype Security Element** | Demonstration cryptography component | Open research prototype key store | Research demonstrator for keyed message authentication; not a certified automotive secure element | I2C / software key | 3.3V DC | $1.25 |
| **Total BOM Cost** | — | — | Complete 1-vehicle research prototype bill of materials | — | — | **$1,082.90** |

---

## 3. Microcontroller & Sensor Interconnect Pinout

The ESP32-S3 microcontroller acts as an ASIL-B(D) localized preprocessor, aggregating all non-vision tactile and kinematic signals and buffering them at 100 Hz.

```
                           +----------------------+
                           |   ESP32-S3-WROOM-1   |
                           |                      |
[ MPU-6050 IMU ] --------> | GPIO 1 (I2C SDA)     |
[ 3.3V Pull-up: 2.2k ]     | GPIO 2 (I2C SCL)     |
[ IMU INT / DRDY ] ------> | GPIO 3 (Ext Interrupt)|
                           |                      |
[ FSR 1: Thoracic Left ] ->| GPIO 4 (ADC1_CH3)    |
[ FSR 2: Thoracic Right] ->| GPIO 5 (ADC1_CH4)    |
[ FSR 3: Lumbar Upper ] -->| GPIO 6 (ADC1_CH5)    |
[ FSR 4: Lumbar Lower ] -->| GPIO 7 (ADC1_CH6)    |
                           |                      |
[ Capacitive Grip Top ] -->| GPIO 8 (Touch CH8)   |
[ Capacitive Grip Btm ] -->| GPIO 9 (Touch CH9)   |
                           |                      |
[ Camera IR Sync Strobe ]<-| GPIO 10 (Timer PWM)  |
                           |                      |
[ Status Green (Nominal)]<-| GPIO 11 (LED Out)    |
[ Status Yellow (Degr.) ]<-| GPIO 12 (LED Out)    |
[ Status Red (Crisis) ] <--| GPIO 13 (LED Out)    |
                           |                      |
[ Host Serial TX ] ------->| GPIO 19 (USB D-)     | ----> [ Jetson Orin NX ]
[ Host Serial RX ] ------->| GPIO 20 (USB D+)     |       (USB-CDC / UART)
                           +----------------------+
```

### 3.1 Analog Signal Conditioning Circuitry for FSR Mat
Each of the 4 FSR elements is wired in an active voltage-divider configuration with a precision rail-to-rail operational amplifier buffer (TI OPA2350, automotive Grade 1):
$$V_{\text{out}} = V_{\text{ref}} \cdot \frac{R_{\text{fixed}}}{R_{\text{FSR}} + R_{\text{fixed}}}$$
Where:
- $V_{\text{ref}} = 3.30\text{ V}$ (stabilized by low-noise reference LDO TI REF3033).
- $R_{\text{fixed}} = 10.0\text{ k}\Omega$ (0.1% tolerance, $25\text{ ppm/}^\circ\text{C}$).
- $R_{\text{FSR}}$ varies from $>1\text{ M}\Omega$ (unloaded) down to $800\,\Omega$ ($20\text{ N}$ full contact pressure).
- Anti-aliasing active 2nd-order Sallen-Key low-pass filter with $f_c = 25\text{ Hz}$ suppresses vehicle chassis mechanical resonance prior to ADC ingestion.

---

## 4. Power Delivery Network (PDN) & Thermal Budget

The vehicle $12.0\text{ V}$ board net (subject to ISO 7637-2 load dump pulses up to $+42\text{ V}$ and cold-crank down to $+6.0\text{ V}$) is regulated through a multi-stage automotive power conditioning network:

```
[ Vehicle 12V Battery ]
       |
       v
+-------------------------------------------------------+
| Reverse Polarity Protection & Surge TVS Diode Clamping|
| (Vishay SM5S36A: 36V standoff, 120A load-dump clamp)  |
+--------------------------+----------------------------+
                           |
                           v
+-------------------------------------------------------+
| TI LM5143-Q1 Synchronous Automotive Dual Buck Stage   |
+--------------------------+----------------------------+
       |                                          |
       | 5.0V @ 5.0A (94% efficiency)             | 12.0V Regulated @ 2.5A
       |                                          |
       +---> [ Jetson 5V Bus / USB Hub ]          +---> [ Jetson Orin NX Core ]
       |                                          |
       +---> [ TI TPS7A8300 Ultra-Low-Noise LDO ] +---> [ NIR Strobe LED Driver ]
       |     3.3V @ 1.0A (Analog Sensors, ESP32)
       |
       +---> [ 5V Isolated DC-DC (RECOM RO-0505S) ]
             5V Isolated (MCP2518FD CAN Transceiver)
```

### 4.1 Thermal Budget & Heat Dissipation
- **Jetson Orin NX (15W TDP):** Extruded aluminum enclosure with copper heat-pipe base and 40 mm MagLev fan (4-wire PWM tachometer). Rated for continuous thermal equilibrium at $+45^\circ\text{C}$ ambient cabin temperature without GPU throttling.
- **ESP32-S3 Gateway:** $<0.8\text{ W}$ operating dissipation; passive convective dissipation through PCB ground pour (4-layer $2\text{ oz}$ copper).
- **NIR Illuminator (4x 850 nm LEDs):** Pulsed duty cycle $12.5\%$ ($2.08\text{ ms}$ pulse width at $60\text{ Hz}$ frame sync); mean dissipation $<1.8\text{ W}$.

---

## 5. Functional Safety Architecture (ISO 26262 ASIL-D Target Decomposition)

> [!IMPORTANT]
> **Safety Disclaimer & Architecture Classification:** The hardware bill of materials detailed in Section 2 represents an engineering proof-of-concept prototype demonstrator. COTS microcontrollers (ESP32-S3), developer edge boards (Jetson Orin NX developer kits), and standard breakout sensors are **not safety-certified**. Rather, this section specifies the **ASIL-D-oriented architectural decomposition pattern** intended for production automotive ECUs, distinguishing conceptual decomposition from formal ASIL certification.

To achieve automotive certification feasibility while avoiding the prohibitive cost of developing full ASIL-D computer vision perception neural networks, CabinGuard-ADI specifies an **ASIL Decomposition Architecture** per ISO 26262-9:2018:

$$\text{Safety Goal 1 (SG-1: Prevent Unwarranted Highway Emergency Braking)} \longrightarrow \text{ASIL-D Target}$$
$$\text{Decomposition Target:} \quad \text{ASIL-B(D)}_{\text{Perception/AI}} + \text{ASIL-B(D)}_{\text{Watchdog/Plausibility}} + \text{ASIL-D}_{\text{Actuation/Gateway}}$$

```
+------------------------------------------------------------------------------------+
|  PERCEPTION LAYER: ASIL-B(D) Target                                                |
|  • NIR Camera + Landmark Tracking (TensorRT FP16)                                  |
|  • Deep Spectral CNN / Welch Energy Ratio (SER)                                    |
|  • Bayesian Etiology Estimator (Log-Sum-Exp Posterior)                            |
+------------------------------------------+-----------------------------------------+
                                           | Candidate Trigger & Feature Vector
                                           v
+------------------------------------------------------------------------------------+
|  CROSS-SENSOR PLAUSIBILITY WATCHDOG: ASIL-B(D) Target [Deterministic Safety Core]  |
|  • Rule 1: Multi-modal Concordance (rPPG vs FSR vs IMU)                           |
|  • Rule 2: Optical Blinding & Contrast Gradient Spoofing Detector (SNR < -15.0 dB) |
|  • Rule 3: Verification Persistence Window Timer ($T_{\text{ver}} = 2.0\text{ s}$) |
|  • Rule 4: Driver Steering Torque Manual Override Interlock ($\tau > 4.0\text{ Nm}$)  |
|  • Rule 5: Seizure-Aware Spasticity Override Suppression                           |
+------------------------------------------+-----------------------------------------+
                                           | Validated Command Flag
                                           v
+------------------------------------------------------------------------------------+
|  VEHICLE CHASSIS ACTUATION INTERLOCK: ASIL-D Target                                |
|  • Dual-channel hardware interlock on CAN-FD transmission                          |
|  • AUTOSAR SecOC freshness counter verification (Anti-Replay)                     |
|  • EBS Deceleration Ramp-Rate Limiter (Max $|j| \le 2.5\text{ m/s}^3$)             |
|  • Hardware Watchdog Timer (Texas Instruments TPS3823: 200 ms timeout)             |
+------------------------------------------------------------------------------------+
```

---

## 6. Evidence and Timing

The synthetic 50-trial benchmark that used to be reported here was produced
by a classifier whose parameters were set to match the simulator, so its
100 % figures measured nothing and have been withdrawn. Current evidence:

| Question | Where the answer is | How it is produced |
| :--- | :--- | :--- |
| Detection accuracy, false MRM starts per hour of real driving, latency | `prototype/results/fusion_metrics.json` | `experiments/realdata/evaluate_fusion.py` on PhysioNet recordings, out-of-fold |
| Cardiac branch AUC and recall; injected-jerk motion baseline | `prototype/results/branch_metrics.json` | `experiments/realdata/train_branches.py` |
| Deployed motion branch (recorded motion only): alarms per hour, recorded-mimic detection, sensitivity vs modelled amplitude | `prototype/results/motion_real.json` | `experiments/realdata/train_motion_real.py` |
| Sensor, processing, communication, tamper, replay and unauthorized-command handling | `prototype/results/fault_matrix.json` | `experiments/fault_matrix.py`, 14 cases x 10 seeds |
| Cycle compute time against the 100 ms deadline | `fault_matrix.json` (`cycle_compute_ms`) and the `run_realtime.py` summary | measured on the development laptop; must be re-measured on the target host |

The safety-relevant latency is dominated by design, not computation: an
event must hold for 2 s after 8 s evidence averaging, then the driver gets a
3 s alert before the vehicle is taken over. Cycle compute is a few
milliseconds with inference pinned to one thread. The Phase 2 bench plan in
`hardware/README.md` lists the timing measurements to repeat on the target
processor.
