# CabinGuard-ADI jury demo: recommended plan

## 0. As built, after the team's answers

The answers to Section 9 changed the plan. This section records what was built
and what follows from the answers; the sections after it are the original plan,
kept for the reasoning and the corrections.

| Question | Answer | Consequence |
|---|---|---|
| GPU | 4 GB VRAM laptop | No CARLA (its minimum is 6 GB). The built-in top-view road is the vehicle view. Heavy GPU work is deferred |
| MATLAB | R2025, all toolboxes | MATLAB is an offline independent checker of recorded sessions, never in the control path (Section 4.1). With a supported USB-CAN adapter it can also read the physical bus through Vehicle Network Toolbox |
| CAN hardware | none yet, can buy | Buy two adapters that both python-can and MATLAB Vehicle Network Toolbox support, for example PEAK PCAN-USB. CANable and candleLight (`gs_usb`, `slcan`) work with python-can but not with Vehicle Network Toolbox |
| Sensors | ESP32, laptop webcam, USB webcam | `--camera 0` or `--camera 1` for the face channel; `--serial COMx` for the ESP32 node |
| Lateral manoeuvre | stop on the hard shoulder | Option B is built: `Shoulder_Req` on bit 31 of 0x120, gateway plausibility (shoulder only from phase 3), kinematic lateral model to -7 m (one lane plus the shoulder) |
| Jury format | 4-minute talk with a 2-minute demo | The 2-minute storyline below replaces Section 6 for the jury; Section 6 stays as the Q&A menu |
| Team and time | 5 people, 7 weeks | Work split below |

**What was built (MVP).**

- `prototype/run_jury_demo.py` starts the engine, the pacing thread and a local web server on 127.0.0.1:8765, and opens the browser.
- `cabinguard/demo/engine.py` runs `CabinGuardECU` and `VehicleSide` unchanged at 10 Hz, mixes simulator and live channels, applies operator faults and attacks, pairs every CAN frame with the gateway's verdict, and builds one record per cycle with computed evidence chips.
- `cabinguard/demo/runner.py` paces cycles on `time.perf_counter` and plays the scripted run with presenter cues.
- `cabinguard/demo/server.py` and `static/` are the dashboard: FastAPI, one WebSocket and plain HTML, CSS and JavaScript, with no framework and nothing loaded from the internet. NiceGUI (M3) was not needed.
- The camera path uses the MediaPipe Tasks FaceLandmarker with the model file shipped in `prototype/models/`.
- Accepted residual risk (decided): a compromised ECU that holds the SecOC key passes both gateway checks. The gateway checks the order of the phases but not their duration, so such an ECU can reach phase 3 braking at -4 m/s² with the shoulder move within three frames (300 ms). Protecting the host and its key is out of scope; the paper states this in Sections VI and VII. If a juror asks, the Phase 2 answer is gateway-side minimum phase durations, a gateway-side brake-pedal cancel and a phase-3 deceleration cap.
- Not built yet: the DATASET REPLAY tier (I3, needs the Colab run), the physical CAN bench (O2), the MATLAB checker (O3) and the ESP32 hardening (I2).

**The 2-minute demo** (times from pressing P; measured on the in-process run).

| Time | What happens | What the presenter says |
|---|---|---|
| 0:00 | Reset; car at 100 km/h; all chips SYNTHETIC | "Every panel says where its data comes from. This is synthetic: it exercises the software, it is not detection performance." |
| 0:06-0:08 | Forged brake commands from an attacker without the key | "Every forged frame fails its MAC check; the car never reacts." |
| 0:14 | Seizure scenario starts (onset 1 s later) | "Watch the evidence per sensor build." |
| about 0:26 | Phase 1: two physical sensors agree, chime, cancel window | "Two independent physical sensors must agree before anything happens." |
| about 0:29 | Phase 2: hazards, sealed eCall acknowledged | "The emergency centre receives 137 bytes: encrypted, signed, no identity." |
| about 0:36 | Phase 3: braking at 3.2 m/s² and steering to the shoulder; DENM | "Nearby cars learn there is a human problem, never the diagnosis." |
| about 0:45 | Phase 4: standstill on the shoulder, parking brake, doors unlocked | |
| 0:45-1:45 | Esc, then live faults: Blind camera (spoofing interlock, no manoeuvre), Compromised ECU (valid MAC, rejected as implausible), ECU hang (warning only in normal driving) | One sentence each |
| 1:45-2:00 | Close | "Phase 2 is the same command with `--camera` and `--serial`." |

**Work split for 5 people over 7 weeks.**

| Who | Weeks | Work | Done when |
|---|---|---|---|
| Demo owner | 1-7 | Install on the jury laptop (python.org CPython 3.12, `pip install -e "prototype[demo,hardware]"`), run the scripted demo daily, own the operator card and the Esc fallback | Three cold-boot rehearsals in a row with no restart |
| ESP32 | 1-4 | Section 5 stage 1: port found by USB VID/PID, reconnect on unplug, clear the IMU window on an I2C error, brake foot switch; headrest IMU, seat FSR and grip pads on a chair | `--serial` turns the IMU and seat chips LIVE and `tests/test_hardware.py` passes |
| MATLAB | 2-5 | Read `--record` session files; recompute every 0x120 MAC with an independent AES-CMAC checked against RFC 4493 vectors; plot the session timeline | Zero disagreements with the gateway's verdicts on a recorded run |
| CAN bench | 3-6 | Buy two adapters; run `run_realtime.py` and `run_gateway.py` on a physical 500 kbit/s bus with 120 Ω at both ends; read it in MATLAB Vehicle Network Toolbox | The forged-frame attack is rejected on the wire |
| Talk and paper | 1-7 | The 4-minute talk; the Phase 2 paper (the fault matrix was re-run in Colab after the shoulder stop and 0x121: 140 of 140 runs pass); a screen recording of a full rehearsal as the last fallback | Talk timed at 4:00 with the 2-minute demo inside |

This plan merges the four proposals, keeps what each judge rated highest, and corrects every factual error the judges found. A final critic pass found further errors; those checked against the code and PyPI are folded into the text, and Appendix B lists all of them. Appendix A lists the earlier corrections with their evidence.

- **Base design.** It starts from Proposal 4 (the "bench-continuous" demo), which had the highest average judge score (8.2/10). It is the only proposal that handles evidence classes and replay of public-dataset recordings honestly.
- **From Proposal 1:** robustness (crash isolation, a safe default profile, a scripted "act" engine) and the live demonstration of the two-sensor rule.
- **From Proposal 2:** the road scene, the "What was real in this run" panel, and the parking-brake (EPB) standstill fix.
- **From Proposal 3:** MATLAB as an independent checker of the CAN security verdicts, the attack labels, and the fault-matrix report.

Abbreviations used throughout: MRM = minimum-risk manoeuvre; SecOC = the AUTOSAR scheme that adds a freshness counter (FV) and a truncated message authentication code (MAC) to each CAN frame; MEC = the 76-byte encrypted medical data the car sends to the emergency call centre (PSAP); DENM = the V2X warning broadcast to nearby cars; pw = person-weeks.

---

## 1. Recommendation in 5 lines

1. **One program.** A single Python 3.12 program, `prototype/run_jury_demo.py`, runs the existing CabinGuardECU, gateway, SecOC, eCall and DENM code unchanged at a 100 ms wall-clock rate. The default profile needs only a Windows laptop: no GPU, no internet, no MATLAB, no CARLA, no ROS.
2. **One projector page.** The jury sees:
   - a car on a highway (CARLA 0.9.16 if an NVIDIA GPU with 6 to 8 GB is available, otherwise a built-in view that needs no GPU);
   - the cabin (live webcam and ESP32 seat/wheel, or synthetic signal traces);
   - posterior and evidence bars;
   - a decoded CAN trace with a SecOC verdict on every frame;
   - a PSAP console that decrypts and verifies the 76-byte MEC.
3. **Each input labelled by where it comes from.** The four inputs are pulse, face, headrest IMU, and seat+wheel. Each one is independently:
   - **SYNTHETIC** (grey);
   - **DATASET REPLAY** (blue), run through models that never saw that recording during training, with dataset, record and model named on screen;
   - **LIVE** (green).

   The software computes every badge; nobody types one in.
4. **Live attacks and faults.** The operator injects forged, replayed, tampered and valid-MAC-but-implausible frames, a blinded or covered camera, an unplugged IMU, an ECU hang, and a cellular outage. The jury watches the real gateway and watchdog code respond.
5. **Phase 2 continuity.** The same command with `--imu esp32:auto --seat esp32:auto --can gs_usb:0 --role ecu` runs on real sensors and a real 500 kbit/s CAN bus. CARLA, MATLAB and ROS 2 are optional plug-ins. Any of them can fail without stopping the demo.

---

## 2. Architecture

### 2.1 Layers and process model

```
 INPUT CHANNELS  (each one independently:  sim | replay:<episode> | live)
 +-----------+ +-------------+ +--------------+ +---------------+     OPERATOR PAGE (laptop)
 | pulse     | | face / eyes | | headrest IMU | | seat + wheel  |     acts.toml, buttons, hotkeys
 | sim       | | sim         | | sim          | | sim           |              |
 | replay    | | live webcam | | replay       | | live ESP32    |              | commands
 | live rPPG | |  (child     | | live ESP32   | |  (serial,     |              v (queue, applied
 |           | |   process)  | |  (serial)    | |   100 Hz)     |                 at cycle start)
 +-----+-----+ +------+------+ +------+-------+ +-------+-------+
       +--------------+-------+-------+-----------------+
                              v
        ChannelMux: re-stamp onto time.monotonic(), EvidenceTag per channel,
                    replayed pulse gated by the live camera's face/SNR health
                              v  one SensorSnapshot every 100 ms
        FaultOverlay: operator-injected faults (INJECTED tag)
                              v
 +--------------------------- CORE (decision code unchanged) --------------------------+
 | CabinGuardECU.step: FeatureExtractor -> CrossSensorWatchdog/FusionClassifier        |
 |   -> VehicleSafetyController;  sends 0x120 MRM_Cmd (SecOC) + new 0x121 Health       |
 +--------------------------------------+---------------------------------------------+
                                        | BusPort (send / drain)
     CAN transport, selected by --can:
       virtual (python-can, in-process, DEFAULT)
       kvaser:0 / udp_multicast:239.74.163.2 (cross-process, opt-in)
       gs_usb:0 / slcan:COMx@115200 / pcan:PCAN_USBBUS1 (physical, 500 kbit/s)
     +--------------+----------------+--------------+---------------+
     v              v                v              v               v
  Gateway node   Telematics       Attacker       CAN tap        (Phase 2 option:
  dispatch by    0x122 status,    forge/replay/  cantools +      ESP32 TWAI
  CAN ID, SecOC, MEC seal (ECDSA  tamper; valid- verdict join    actuator node)
  plausibility,  + ECIES), PSAP,  MAC implausible
  alive, verdict DENM             runs inside ECU
     | actuation: phase, decel, hazards, EPB
     v
  VehiclePlant:  PointMassPlant (always)  |  CarlaPlant (child process, opt-in)
     | speed, accel, jerk, lateral offset, standstill  -> ECU on the next cycle
     v
  TickRecord (one per cycle) -> "latest" slot + ring buffer
     +-> NiceGUI stage page (projector) + operator page
     +-> recorder (JSONL + npz inputs, under git-ignored data/) -> recorded-run replay
     +-> TCP JSON-lines on 127.0.0.1 -> MATLAB monitor / shadow verifier (read-only)
     +-> optional MCAP (foxglove-sdk) -> Lichtblick;  optional ROS 2 mirror
```

**Process model**

- **One tick thread owns all mutable state.** On each 100 ms deadline (absolute targets `t0 + k*0.1`, as in `run_realtime.py`) it:
  1. applies queued operator commands;
  2. builds the snapshot;
  3. runs `CabinGuardECU.step`, then the attacker, the gateway node, the plant and the tap;
  4. publishes a single TickRecord.
- **The UI runs in its own process.** Under the GIL a UI thread still competes with the 100 ms ECU, which fails silent after three overruns, so NiceGUI runs as a separate process fed by the TCP JSON-lines feed (2.2 e) and sends operator commands back over the same socket. Use `reload=False` and a plain `if __name__ == "__main__"` guard; keep worker entry points in modules that never import the UI, because `spawn` children import the parent's main module as `__mp_main__`.
- **Clocks.** Use `time.perf_counter()` for camera frame stamps and every timing figure: on Python 3.12 for Windows `time.monotonic()` has about 15.6 ms resolution (QueryPerformanceCounter only from 3.13), which would quantise rPPG beat times and inflate ibi_cv.
- **Crash isolation.** The two native-crash-prone parts run in supervised `multiprocessing` children started with `spawn`:
  - MediaPipe/OpenCV (`camera_worker`);
  - the CARLA client (`carla_worker`).

  If a child's heartbeat stops, its channel goes stale. The watchdog then shows a designed degraded mode, and the child restarts. This matters because the ECU deliberately fails silent after three consecutive deadline overruns. That rule stays; it is not weakened for the demo.
- **Measured headroom so far.** `results/fault_matrix.json` (Colab re-run after the shoulder stop and 0x121) gives ECU compute of 5.8 ms median, 11.0 ms p99 and 81.2 ms max on synthetic signals, all within the 100 ms deadline. That was not measured on the jury PC with the camera and UI running, so it must be re-measured there.
- **Roles.** `--role all` is the default. `--role ecu` and `--role vehicle` split the same nodes across two PCs for the Phase 2 bench.

### 2.2 Message and topic contract between the core and the front ends

**(a) TickRecord.** One JSON object per 100 ms. It is the only thing front ends consume.

| Field group | Contents |
|---|---|
| `k`, `t_mono`, `wall` | cycle index, monotonic time, wall-clock time |
| `provenance` | per channel (`pulse`, `face`, `imu`, `seat`): `{class, source, detail, model}`; plus `vehicle`, `bus`, `comms`, `key` |
| `inputs` | EAR, pitch_deg, optical_snr_db, face_detected, new beats, IMU RMS and a 2 s strip (decimated), FSR, grip state, steering torque, brake pedal |
| `health` | camera_ok / imu_ok / seat_ok; ESP32 frame rate, CRC errors, lost frames, IMU I2C error flag; measured camera fps |
| `decision` | posteriors {Normal, Syncope, Seizure}; `branch_llr` per branch (capped at ±3.0, `fusion.BRANCH_CAP`); corroborating physical sensors; persistence timer; degraded level; spoof flag; override suppressed; new security-log lines |
| `ecu` | alive/failed, MRM phase, transmit FV, compute_ms, overruns |
| `can` | rows: `{t, id, name, sender (instrumentation only), signals, fv8, fv_reconstructed, mac_hex, verdict}` |
| `gateway` | state (INIT/OK/ALIVE_TIMEOUT), applied phase/decel/hazards/EPB, ecu_fault, fail_operational, counters {mac, replay, data_id, implausible} |
| `vehicle` | speed, longitudinal accel, jerk, lateral offset, standstill, real-time factor (CARLA) |
| `telematics` | MEC lifecycle (Idle/Sending/Acknowledged/Queued), attempts, bearer log, sealed blob hex (137 B), PSAP-verified fields, PSAP counters, DENM body |
| `timing` | loop gap, jitter, overruns this session |

**(b) Operator commands.** These go into a queue and are applied only at cycle boundaries:

- `act <name>`
- `source <channel> <spec>`
- `attack forge|replay|tamper|implausible|mec_replay`
- `fault blind|cover|imu_drop|seat_freeze|ecu_hang|ecu_restart|cellular_down|all_bearers_down on|off`
- `driver_brake on|off`
- `mark_onset`
- `reset`
- `record on|off`

**(c) CAN contract.** The product DBC (`prototype/cabinguard_mrm.dbc`) is unchanged. A new **demo** DBC (`prototype/demo/cabinguard_demo.dbc`) is labelled as bench and instrumentation, not as part of the CabinGuard interface.

| ID | Name | DBC | Sender to receiver | Rate | Protection |
|---|---|---|---|---|---|
| 0x120 | MSG_CabinGuard_MRM_Cmd | product | ECU to gateway | 100 ms (also the alive signal) | SecOC profile 1 layout: 8-bit FV, 24-bit MAC |
| 0x121 | MSG_CabinGuard_Health | product (defined, **not sent today**) | ECU to gateway | 100 ms | SecOC, Data ID 0x121 |
| 0x122 | MSG_CabinGuard_Telematics_Status | product (defined, **not sent today**) | telematics to HMI | 1 s | none (DBC has no SecOC fields) |
| 0x1A0 | VEH_State: speed, standstill, driver brake, plant source | demo | vehicle to ECU | 50 ms | SecOC, Data ID 0x1A0 |
| 0x7F0 | GW_Verdict: last verdict, applied phase/decel/hazards/EPB, counters | demo, instrumentation | gateway to sniffers | on event + 1 s | none |

The MAC is the first 3 bytes of AES-128-CMAC over `DataID (2 B big-endian) || payload (4 B) || FV (8 B big-endian)` (`secoc._mac`). Byte 3 bit 31 of 0x120 is the only free payload bit.

Computed bus load (not measured): about 43 frames/s at no more than 135 bits each comes to about 5.8 kbit/s, roughly 1.2% of 500 kbit/s.

**(d) VehiclePlant interface:**

- `reset(speed_ms)`
- `apply(actuation, dt) -> PlantState`
- `close()`

`actuation` is the gateway output (phase, decel_mss, hazards, epb, doors_unlock). PointMassPlant reuses the integration that `VehicleSide.step` already does. CarlaPlant lives behind a pipe to its child process.

**(e) Export.** Python is the TCP server: JSON lines on `127.0.0.1:<port>`, carrying the TickRecord plus raw CAN bytes. MATLAB therefore only needs base `tcpclient`, not `tcpserver` or `udpport`, which appear to need Instrument Control Toolbox.

**(f) Evidence vocabulary.** Every panel shows one of these:

| Tag | Meaning |
|---|---|
| `SYNTHETIC` | MultimodalSensorSimulator signal; exercises the software path, not detection performance |
| `REPLAY:<dataset> <record>` + `FOLD:<model>` | public recording, run through an out-of-fold model that excluded that record or patient |
| `LIVE` | webcam or ESP32 now |
| `STAGED` | consented team member acting an event (never clinical) |
| `INJECTED` | operator-triggered fault or attack |
| `MODEL:<training>` / `EXPERT-SET` | read from the model's `training` metadata; vision and posture branches are expert-set, not trained |
| `SIM-VEHICLE:<point-mass \| CARLA 0.9.16>` | never vehicle performance |
| `SIM-BUS:<in-process \| udp-multicast \| kvaser-virtual>` / `PHYS-BUS:<adapter>@500k` | virtual buses model no arbitration or bit timing, so no bus latency is quoted from them |
| `SIM-COMMS` / `REAL-LINK` | simulated bearers and PSAP, or a PSAP on a second device over IP |
| `MEASURED-HERE` | compute or loop timing on this laptop only |
| `DEMO KEY` | the public SecOC demo key, unless `--key-file` was given |
| `RECORDED RUN <date>` | a replayed rehearsal; keeps the original tags and recomputes the decisions |

### 2.3 Fixes the core needs before 0x121, 0x122 or a restart button exist (all verified in the code)

1. **Dispatch frames by CAN ID.** `VehicleSide.step` and `run_gateway.py` pass every frame to `MRMCommandRx`. A 0x121 frame would therefore be counted as `rejected["data_id"]` and logged as "rejected: authentication or freshness", which would show the jury a false attack.
2. **Per-frame verdicts.** Add an enum (`INIT, OK, MAC_FAIL, REPLAY, DATA_ID, IMPLAUSIBLE, ALIVE_TIMEOUT`) and a bounded verdict log. Keep the existing `bool` returns and counters, so the tests and the fault-matrix checks do not change.
3. **INIT state before the first valid frame.** The spurious "ECU alive timeout" at t=0 happens only when the gateway ticks before any frame arrives, as in the cross-process `run_gateway.py` or `--role vehicle`. In-process, `VehicleSide.step` receives before it ticks, so it does not occur there.
4. **Standstill threshold on the fail-operational path.** In normal operation the EPB comes from the ECU's Phase 4 command, and the ECU enters Phase 4 at a measured speed of 0.05 m/s or less. Only `VehicleGateway.tick`'s fail-operational branch tests `speed_ms > 0.0` and `<= 0.0`. CARLA's residual speed never reaches exactly 0, so that branch would never clamp the EPB. Use about 0.05 m/s.
5. **Continue the freshness counter on an ECU restart.** A new `SecOCSender` starts at FV 0. The receiver reconstructs a newer counter, so every new frame fails as `rejected["mac"]`; it is not counted as a replay. Restart with `start_fv = last_fv + margin` and keep the margin well below 256, since `SecOCReceiver.max_gap = 255`. For a real process kill on the bench, persist the counter periodically, as an ECU would to non-volatile memory.
6. **Bitrate for all physical interfaces.** `CanBus` passes `bitrate` only for `socketcan`. Pass 500000 for `slcan`, `gs_usb`, `pcan` and `kvaser` too; an slcan adapter otherwise keeps whatever bitrate is stored on it. Also expose `receive_own_messages` and Vector's `app_name`.

---

## 3. Dashboard screens

**Stage page (projector, 1920x1080, with a 1366x768 fallback layout)**

```
+---------------------------------------------------------------------------------------------+
| EVIDENCE STRIP  pulse[REPLAY PhysioNet vfdb rec. | FOLD k] face[LIVE webcam] imu[LIVE ESP32]  |
|                 seat[LIVE ESP32]  vehicle[SIM point-mass|CARLA 0.9.16]  bus[SIM in-process]  |
|                 comms[SIM]  key[DEMO KEY]                                                    |
+---------------------------------------------------------------------------------------------+
| PHASE STEPPER   NORMAL > P1 alert (3 s) > P2 takeover + hazards > P3 brake -3.2 > P4 stop    |
+---------------------------------------------+-----------------------------------------------+
| ROAD VIEW                                    | CABIN                                         |
| CARLA chase camera, or built-in view         | webcam + landmark overlay, EAR / pitch / pulse|
| HUD: speed, decel commanded vs measured,     +-----------------------------------------------+
| hazards, EPB, doors-unlock icon, ECU fault,  | DECISION                                      |
| real-time factor                             | posteriors + Gamma 0.85 line, 2 s persistence |
|                                              | ring, branch LLR bars, "imu + seat: 2 of 3"   |
+---------------------------------------------+-----------------------------------------------+
| CAN TRACE (decoded, FV8, FV, MAC, verdict, counters) | PSAP / V2X (switches in on eCall)     |
+---------------------------------------------------------------------------------------------+
```

| Panel | What it shows | Real vs simulated |
|---|---|---|
| Evidence strip + footer | One badge per channel, plus vehicle model, CAN transport, comms and key provenance | Computed from runtime provenance |
| Phase stepper + timers | NORMAL, then P1 (3 s alert, cancel by brake or >4 Nm unless clonic or clenched), P2 at 3 s (takeover, hazards, eCall), P3 at 10 s from alert start (-3.2 m/s²), P4 at ≤0.05 m/s (EPB, doors) | Real controller state |
| Road view | Built-in default: SVG top-down view (always) plus a NiceGUI `ui.scene` (three.js) chase view built from primitives, only if WebGL is reported. Optional: CARLA chase camera. Shows lanes, brake lights, blinking hazards, a follower car (illustrative), a DENM ripple, the decel trace (labelled "plant = command" on the point mass; "commanded vs measured" only with CARLA, still synthetic), and the real-time factor | SIMULATED vehicle, badge `SIM-VEHICLE:point-mass` or `CARLA 0.9.16` |
| Cabin | Live: webcam JPEG (640x360) with SVG landmarks (eye contours, forehead rPPG patch, nose, chin), EAR/pitch/pulse strips, IMU RMS, FSR, grip, torque. Synthetic: a schematic, clearly non-photoreal driver figure driven only by SensorSnapshot values (eyelid opening from EAR, head pitch, slump from seat psi, hands from grip), permanently badged SYNTHETIC, next to the seat-and-wheel sensor map and the snapshot traces | LIVE / STAGED / SYNTHETIC per channel; the synthetic view is captioned "synthetic signals, no camera image" |
| Decision | Posteriors with the Γ = 0.85 line; 2 s persistence ring; branch LLR bars (cardiac, motion, vision, posture) capped at ±3, coloured by physical sensor and labelled with provenance; corroboration chip; mode banner (Nominal / Degraded 1 camera lost / 2 IMU lost / 3 fewer than two sensors); spoof-interlock lamp and security-log line; override-suppressed chip; ECU compute ms | Real model outputs. Cardiac: `MODEL: PhysioNet ECG-trained, not validated on rPPG`. Motion: `MODEL: SeizeIT2 + UEA mimics + PhysioNet + MHEALTH`. Vision and posture: `EXPERT-SET`. Compute: `MEASURED-HERE` |
| CAN trace | Time, ID, message name, decoded signals, FV8, reconstructed FV, MAC hex, verdict; rejected rows coloured with an icon; counters; "rejected only" filter; `sender` column marked as instrumentation | Real frames and real SecOC code on a `SIM-BUS` or `PHYS-BUS` |
| PSAP / V2X | MEC lifecycle; bearer timeline (cellular backoff, then SMS fallback); 137-byte sealed blob (33 B ephemeral key, 12 B nonce, 76 B ciphertext, 16 B tag); then decrypt OK, ECDSA OK, freshness OK and the 76-byte MEC fields; a "not in the MEC: identity, location, raw signals" list; PSAP rejection counters; signed DENM (cause 93, sub-cause 0, no etiology). Ego position shown separately as "MSD position (simulated)" | Real cryptography; `SIM-COMMS` bearers, PSAP and radio (`REAL-LINK` only if the PSAP runs on a second device) |
| Results tab | Numbers read at startup from committed `prototype/results/*.json`, each with its `scope` string verbatim; this session's ECU compute p50/p99/max; the committed fault-matrix report (14 cases × 10 seeds, synthetic); and an auto-generated **"What was real in this run"** list built from the session's tags | As each file's scope says, plus `MEASURED-HERE`. `external_checks.json` has no `scope` and `cardiac_branch.joblib` has no `training` key: add both at the next Colab run |

**Operator page (laptop screen).** Act list, from `prototype/demo/acts.toml`; each act sets source per channel, seed, scheduled injections, focus panel and a one-line caption. It also has a per-channel source selector, attack and fault buttons, a driver brake, an onset-marker hotkey (so live latencies are labelled "operator-marked, staged"), record, a preflight status column, and **Esc to reset to safe synthetic normal driving in under 1 s**. Hotkeys can be mapped to a presenter clicker.

**Launch.** Run NiceGUI headless on `127.0.0.1` and open two Microsoft Edge windows with `--app=http://127.0.0.1:<port>/stage --start-fullscreen --autoplay-policy=no-user-gesture-required` and `--app=.../operator`. This avoids NiceGUI's `native=True`, which needs pywebview, an optional NiceGUI dependency that the proposals' pins left out. Give each Edge window its own `--user-data-dir` and `--window-position` (a second window with the same profile joins the running process and may ignore its switches), and make Esc reset work from both pages. Binding to 127.0.0.1 also means the Windows firewall never prompts.

---

## 4. Role of MATLAB, CARLA and ROS 2

### 4.1 MATLAB: an independent measurement node, never in the control path

**Step 0: check the licence before building anything.**

- Run `ver` and `license('test','Vehicle_Network_Toolbox')` (and the same for each toolbox below), and open License Center. An installed toolbox is not necessarily a licensed one.
- MathWorks' Home terms say "not for government, academic, research, commercial, or other organizational use". An IEEE student-branch challenge with a published paper plausibly falls under that.
- Since 1 Jan 2026, perpetual Home and Student licences cannot get new add-ons.
- The routes to toolboxes are MathWorks' student-competition programme (request form, can take up to 48 business hours) or the university Campus-Wide License.
- Every MathWorks fact in this plan comes from search excerpts, because mathworks.com was unreachable from the research session. Confirm on the live pages before spending money.

| Product | Concrete use in the demo | If it is missing |
|---|---|---|
| **Base MATLAB** (R2020b+ for `tcpclient` with `configureCallback`) | **Shadow verifier and monitor**, `prototype/matlab/CabinGuardMonitor.m` (programmatic `uifigure`, which diffs better in git than `.mlapp`). It reads the JSON-lines feed, decodes the 0x120/0x121/0x122/0x1A0/0x7F0 bytes with its own `bitand`/`bitshift` decoder, and **recomputes the 24-bit AES-128-CMAC** with its own RFC 4493 implementation on `javax.crypto.Cipher("AES/ECB/NoPadding")`. A "Python vs MATLAB verdict disagreements" counter must read 0. FV state is bootstrapped once from 0x7F0, then tracked independently. Display: `uigauge` speed/decel, `uilamp` phase/hazards/EPB/eCall/spoof, `uiaxes` decel and jerk against -3.2 and the -4.0 limit. Plus `analyze_session.m`, which reads the recorded JSONL with `fileread` + `jsondecode` (base MATLAB cannot read `.npz`). Only the decoding and the CMAC are independent; the capture is Python's TCP tap unless VNT listens on a physical bus, and the screen says so. | No independent verifier. Python `cantools` plus SavvyCAN or CANgaroo cover the monitor role. If the JVM is unavailable (MATLAB started with `-nojvm`), calling `py.cabinguard.crypto` works but is **not independent**, and must be labelled so. |
| **Simulink (base)** | Post-run requirements check, `post_run_check.slx`: From Workspace into Model Verification blocks (Assertion, Check Static Range, Check Discrete Gradient). Checks: P2 at **3 s** (`PHASE_1_DURATION_S`; `PHASE_2_START_S = 4.0` is unused), P3 at 10 s, decel within [-4.0, 0] m/s², EPB only at standstill, eCall requested by P2. No jerk bound until the controller gets a jerk-limited ramp (with a test and a paper update): today the command steps from 0 to -3.2 m/s² in one cycle, about 32 m/s³ on the point mass. Prints measured margins. Far below the 1000-block cap reported for Home/Student. | The same assertions in a `.m` script |
| **Vehicle Network Toolbox** | Tier 1: CAN Explorer with `canDatabase` on both DBCs as a second, MathWorks-native live monitor, listen-only. Channel options: the free Kvaser virtual driver (device string from `canChannelList`, untested), or a physical **PEAK or Kvaser** adapter. On Windows VNT does not support CANable or gs_usb adapters. MathWorks virtual channels cannot reach a Python process. | Stay on the Tier 0 TCP feed |
| Instrument Control Toolbox | Not needed: Python is the TCP server | n/a |
| Simulink 3D Animation + Vehicle Dynamics Blockset / Automated Driving Toolbox | **Not recommended** as the 3D view: two paid add-ons, VR-class GPU with 8 GB VRAM recommended, a reported R2025b/UE 5.3 incompatibility, and no driver avatar | Built-in view or CARLA |
| RoadRunner Scenario | No: separate licence (reportedly not for Student licences), and its CARLA co-simulation guide targets CARLA 0.9.13 | n/a |
| ROS Toolbox | No: adds nothing over the CAN tap | n/a |

**Why MATLAB never hosts the gateway.** Windows timer and GUI jitter has been reported at tens of milliseconds, occasionally above 100 ms. That would trip `ALIVE_TIMEOUT_S = 0.3` and produce false ECU faults. MATLAB also never opens the webcam: Python owns it.

**If `py.` interop is ever used,** the Python must be 3.11 or 3.12 for R2025a/b (R2026a also supports 3.13), and not the Microsoft Store build.

### 4.2 CARLA: optional plant behind the same interface, with automatic fallback

**Version.**

- Use **CARLA 0.9.16 (Unreal Engine 4)**: Windows `CARLA_0.9.16.zip`, run `CarlaUE4.exe -quality-level=Low`, map **Town04** (in the main package; it has a highway loop).
- Client: `pip install carla==0.9.16`. Windows wheels exist for cp310, cp311 and cp312, so use Python 3.12.
- Not 0.10.0 (Unreal Engine 5.5): it needs Windows 11, a 16 GB-VRAM RTX card and 130 GB of disk, and its client is not on PyPI. Not `ue58-dev`: unreleased.
- GPU: 8 GB VRAM (RTX 2070 class) recommended, 6 GB is the stated minimum. No laptop FPS figures are published, so measure on the actual PC with `PythonAPI/util/performance_benchmark.py` before promising anything.

**The PyPI wheel does not include the agents package.** `pip install carla==0.9.16` installs only `carla/` and `carla.libs/`. `LocalPlanner` and `VehiclePIDController` come from the CARLA zip's `PythonAPI/carla/agents`. Point `CARLA_ROOT` at it and add it to `sys.path`, and import only the controller and local-planner modules. (From memory, not verified: `BasicAgent` and the global route planner also need `shapely` and `networkx`.)

**Control mapping** (`prototype/cabinguard/demo/carla_plant.py` plus `carla_worker.py`, replacing `prototype/carla_bridge.py`):

| Gateway output | CARLA action |
|---|---|
| NORMAL, P1 (driver still in control) | Traffic Manager autopilot as the **labelled driver stand-in**: `set_desired_speed(100)` (km/h), `auto_lane_change(False)`, no per-vehicle percentage (it overrides the desired speed), `update_vehicle_lights(False)` |
| P2 (takeover, decel 0, hazards) | Autopilot off. Lane hold with the vendored lateral PID; speed hold; `set_light_state(VehicleLightState(LeftBlinker \| RightBlinker))` on a blueprint with working lights (check the Lincoln MKZ 2020) |
| P3 / fail-operational | Lateral PID keeps the lane. A PI loop on acceleration measured from `get_velocity`, plus a per-blueprint brake feed-forward map, tracks the gateway's decel (-3.2 m/s²). Brake lights on. **Never `add_emergency_stop`**, which is full brake |
| Standstill | Latch below 0.05 m/s with a brake hold (so VEH_State reports 0 and the ECU enters P4) |
| P4 | `hand_brake=True` stands in for the EPB. Door unlock is a **HUD icon only**, never `open_door` |

**Timing.**

- Synchronous mode with `fixed_delta_seconds = 0.05` and **two ticks per 100 ms ECU cycle**. Avoid 0.1 s, which sits exactly at the 0.01 × 10 substep limit.
- `tm.set_synchronous_mode(True)` for the Traffic Manager.
- Each `world.tick` has a timeout.
- Synchronous mode is switched off in `finally` and `atexit`, or the server stays blocked waiting for a tick.
- The child reports its real-time factor. Below 0.8×, or if its state is older than 300 ms, the orchestrator **hot-swaps to PointMassPlant at the current speed**, and the road badge changes on screen.

**Views.**

- Chase camera: `SpringArmGhost` at (-2·bound_x, 2·bound_z, pitch 8), 960x540, JPEG-encoded in the child.
- The spectator can follow the ego on the CARLA window on a second screen.
- Camera images are never streamed over a network: 720p BGRA at 20 Hz is about 590 Mbit/s.

**Two-PC variant.** The GPU desktop runs `CarlaUE4.exe`. The laptop connects over **wired** Ethernet on TCP 2000-2001; the Traffic Manager runs client-side. Do not spawn the chase camera from the laptop client: CARLA streams raw BGRA to the client (960x540x4 B at 20 Hz is about 330 Mbit/s). Show the server's own spectator window on the projector instead. A CARLA-to-point-mass hot swap is marked in the recorder and on every decel trace, so no plot mixes two plants unlabelled.

**What CARLA cannot show.** The cabin: stock CARLA has no seated driver, and DReyeVR is tied to 0.9.13 and a source build.

**The stop is in-lane.** 0x120 carries no lateral request, yet line 152 of the paper says "a lateral move to the shoulder", `safety_controller.py` computes `lateral_pos_m` toward -7 m, and `fault_matrix.py` says "stop on shoulder". The team must choose one (see section 9):

- **A (recommended for the MVP):** in-lane stop everywhere. Change the paper sentence, the state names and the fault-matrix text.
- **B:** add `Shoulder_Req` on 0x120 bit 31 and let the vendored LocalPlanner change lanes in CARLA. Update the DBC, the encoder test and the paper together.

**Measured numbers.** `prototype/experiments/carla_mrm_profile.py` runs N MRMs in lockstep on the user's GPU PC (not in Colab, not in a Claude session). It writes `prototype/results/carla_mrm_profile.json` with worst-case decel, jerk, lateral offset from lane centre and stopping distance. These are quoted only as "synthetic simulation (CARLA 0.9.16 vehicle model)".

**Hardware fallback ladder:**

1. Built-in view on the point mass (the default; always rehearsed).
2. CARLA on a second PC.
3. CARLA `no_rendering_mode.py` 2D map: server running, GPU unused.
4. sumo-gui (`pip install eclipse-sumo`, 1.28.0): 2D traffic only.

BeamNG.tech is not lighter (RTX 3060 8 GB class recommended, plus an academic application of up to 5 business days).

**Fix the CARLA docstring.** It currently says "UNECE R157 safety controller". Rule 35 requires "aligned with". The same fix applies to the `safety_controller.py` header.

### 4.3 ROS 2: recommended against for the jury path

Nothing the jury must see needs ROS 2. On a Windows jury laptop in October 2026 it adds risk:

- **Humble and Jazzy:** no more Windows binaries. The Humble Patch 15 (2026-09-14) and Jazzy Patch 8 (2026-06-18) notes both cite Windows 10 end of life.
- **Humble also** runs Python 3.10, and CabinGuard needs 3.11+ (`enum.StrEnum`).
- **Kilted** reaches end of life in November or December 2026; REP 2000 and the docs disagree by a month.
- **Lyrical Luth** (May 2026) is Tier 1 on Windows 11 only, as an archive install. It needs `C:\pixi_ws`, `pixi shell` in every terminal, and a pinned Python 3.12.3 / numpy 1.26.4 / conda OpenCV environment that the ML stack would have to share.
- **carla-ros-bridge** is pinned to CARLA 0.9.13; its last commit was in July 2022.
- **CARLA's native `--ros2`** is documented only for Linux, and there is an open issue (#9551) about Jazzy Fast-DDS stalls.
- **ros2_socketcan** is Linux-only.

**Cheaper alternative for ROS-literate jurors.** Write the TickRecord stream as MCAP with `foxglove-sdk` 0.29.0 (MIT, Windows wheel, no ROS install). Put the evidence class in the topic names (`/sim/...`, `/replay/seizeit2/...`, `/live/esp32/...`) and open the file in **Lichtblick 1.29.1** (MPL-2.0, offline, no account). The proprietary Foxglove app expects a sign-in.

**Optional `--ros2` mirror (about 1 pw), only if the jury explicitly values ROS.** A separate `rclpy` node consumes the TCP feed, so the ML stack never shares the ROS Python environment. It publishes only standard messages:

- `sensor_msgs/Imu`
- `sensor_msgs/CompressedImage` (≤10 Hz)
- `std_msgs/Float32MultiArray` (posteriors)
- `std_msgs/String` (phase)
- `diagnostic_msgs/DiagnosticArray`
- `nav_msgs/Odometry`

Use Lyrical natively on Windows 11, or Jazzy in WSL2 Ubuntu 24.04 if MATLAB ROS Toolbox (R2025a-R2026a recommend Jazzy) must join. Never Humble. Drop it if it fails any of three cold-boot rehearsals.

---

## 5. ESP32 and the Phase 2 path

| Stage | What changes | Effort |
|---|---|---|
| **0: now** | `--imu sim --seat sim`; the demo is complete without hardware | 0 |
| **1: sensor node on USB serial (Phase 2 core)** | The existing firmware streams a 24-byte CRC-16 frame at 100 Hz, 921600 baud, into `SerialSensorNode`. Changes: (1) find the COM port by USB VID/PID (CP210x `10C4:EA60`, CH340 `1A86:7523`) plus a valid-CRC probe; (2) wrap `ser.read` and reconnect on `SerialException`, since today the reader thread dies on unplug; (3) **clear the IMU window on an I2C error**, because today the deque keeps old samples and splices them with new ones on recovery; (4) a brake foot switch. The gateway must sense it itself (`_plausible` accepts leaving a manoeuvre only on the gateway's own driver observation, never on ECU say-so), so on the two-PC bench it belongs on the vehicle side and reaches the ECU in SecOC-protected 0x1A0. On a one-PC demo the ESP32 can carry it in status-flag **bit 1**, and the orchestrator passes it to both `snap.brake_pedal` and `VehicleSide.step(driver_brake=...)`; today `run_realtime.py` never passes `driver_brake`. Change the firmware, `NodeParser`, `encode_node_frame` and `tests/test_hardware.py` together. Each channel goes live on its own (IMU live while the seat is still synthetic) | 1 pw |
| **2: two-PC bench on real CAN** | ECU laptop (webcam + ESP32) `--role ecu`, vehicle PC (gateway + plant) `--role vehicle`, two USB-CAN adapters at 500 kbit/s, 120 Ω at both ends, twisted pair. Adapters: STM32F072 candleLight on `gs_usb` (Windows binds WinUSB without a driver) or CANable 2.x on `slcan:COMx@115200`; not an STM32G431 board, which mainline candleLight does not support. SecOC-protected 0x1A0 closes the speed and brake loop over the wire. **Keep a third node that ACKs**: a sniffer adapter in normal mode, or the attacker adapter. Otherwise, once you pull or kill the ECU, the vehicle PC's frames get no ACK. Keep the jury dashboard on the vehicle-side PC, or fed by local telemetry. The ESP32 stays on serial to the ECU host, as an in-cabin sensor bus would | 1.5 pw |
| **3: ESP32 actuator node (optional)** | A second ESP32 with its TWAI controller (one per chip, classic CAN only, which is all the DBCs need) and an SN65HVD230 3.3 V transceiver. It drives hazard LEDs, a Phase 1 buzzer and an EPB LED from SecOC-verified 0x120 (verified on the node), not from unauthenticated 0x7F0; if driven from 0x7F0 they are badged status indicators only. Stretch goal: verify 0x120 SecOC on the node with mbedTLS AES-CMAC (check that `MBEDTLS_CMAC_C` is enabled in the chosen core), validated against vectors exported by a pytest from `cabinguard.secoc` | 2 pw |
| **4: future only** | Sensor node on CAN, or micro-ROS (`micro_ros_platformio` on esp32dev, Jazzy or Kilted). micro-ROS's own README says it is not production or safety ready, and it adds an agent process. Present it as a migration path | n/a |

**Phase 2 acceptance risk.** The spec book asks for an "approved physical or simulated vehicle environment". Ask the organisers whether a point mass on an in-process bus qualifies. Stage 2 (a real wire), and CARLA where a GPU exists, are the mitigations.

---

## 6. The 7-minute jury storyline

**Rules for every act:**

- Real time, no time compression.
- No demo-only thresholds or models.
- Any live beat is kept only if three rehearsals reproduced it, and is narrated as what was observed.

| Time | Act | Operator action | What the jury sees | Badges |
|---|---|---|---|---|
| 0:00-0:35 | **Legend** | none | Car cruising at 100 km/h. Presenter reads the evidence strip and states the rule: "Every panel says where its data comes from. Synthetic runs exercise the software. Performance numbers come only from named public datasets, at the end." | All |
| 0:35-1:30 | **Live normal driving + the two-sensor rule** | Volunteer in the rig | Landmarks, EAR dips on blinks, rPPG pulse, headrest IMU, grip pads. CAN: 0x120 and 0x121 at 10 Hz, FV incrementing, verdict OK. The volunteer then closes their eyes and nods while staying upright with hands on the wheel: the vision bar rises, the chip reads "camera only: 1 of 3 physical sensors", **no MRM**. Keep only if rehearsed | LIVE |
| 1:30-3:00 | **Act 1: cardiac syncope (hybrid)** | Before onset, toggle "cellular down" (INJECTED). Switch the pulse channel to a PhysioNet VF-onset replay with its fold model; the volunteer closes their eyes, drops the head and releases the wheel | Pulse goes flat; the cardiac bar (fold model named) and the posture bar rise; Syncope crosses Γ = 0.85 with 2 of 3 sensors; 2 s ring fills. P1: chime, 3 s cancel window. P2 at 3 s: takeover, hazards, eCall; the PSAP panel shows cellular retries with backoff, then **delivery over SMS**, the 137-byte blob, then the verified MEC (etiology Syncope; no identity, location or raw signals). P3 at 10 s: in-lane braking at -3.2 m/s², commanded vs measured decel; DENM cause 93 sub-cause 0; the follower car slowing is a scripted animation, badged illustrative (no V2X receiver is modelled). P4: EPB, doors icon. **Caveat:** the replayed pulse is gated by the live camera's face and SNR health, as real rPPG would be. If the head drop loses the face, the cardiac branch drops out. Rehearse a moderate head drop; the fallback is the synthetic syncope scenario | pulse REPLAY (blue), badged "PhysioNet ECG R-peak times, pulseless intervals removed, substituted for camera pulse"; the forehead rPPG patch is greyed while the pulse is replayed; face and seat LIVE (green); vehicle SIM |
| 3:00-4:05 | **Act 2: convulsive seizure + ECU death after takeover** | Act preset: IMU is a SeizeIT2 neck-accelerometer replay with a fold model excluding that patient; face and seat synthetic from the seizure scenario (mirroring the paper's composite episodes). At P2 press **Hang ECU** | Motion branch rises and the class is **Seizure, not Syncope** (point at the branch bars). Clonic torque above 4 Nm shows "override suppressed". MEC etiology Seizure, DENM still sub-cause 0. Press Hang ECU **in Phase 3**, the tested path (`fault_matrix` "processing failure during MRM", `test_pipeline` at 34 s). The ECU goes silent after three missed deadlines; the gateway declares ALIVE_TIMEOUT 0.4 s after the injected overrun (measured in-process here; re-measure on wall clock on the jury PC and quote that number), stays **fail-operational** (hazards, -3.2 m/s²), stops the car, EPB at standstill. A hang in Phase 2 would give no DENM and no door unlock, because the gateway never raises the phase itself | IMU REPLAY (badge text: "SeizeIT2 neck sensor, 25 Hz upsampled with the training resampler, replayed into the headrest input"); pulse SYNTHETIC (seizure-scenario ictal tachycardia) unless an szdb replay is selected; face/seat SYNTHETIC; hang INJECTED (simulated deadline overrun). Optional rehearsed STAGED beat: a team member performs the bench convulsion mimic on the instrumented seat with the LIVE headrest IMU (hardware/README validation plan), never called clinical |
| 4:05-5:05 | **Act 3: attacks on the bus** (Esc back to normal driving first) | Forge, Replay, Tamper, Implausible | **Forge** (wrong key): MAC_FAIL, car unaffected. **Replay** (captured genuine frame): shown as REPLAY via a display-only ring buffer of accepted frames; the counter shows `mac`, and the panel says why (the reconstructed FV is newer, so the MAC fails). **Tamper**: labelled "modified copy injected", because a frame cannot be edited in flight on a shared bus; byte 0 XOR 0x0B flips **three** bits, and the attacker advances the freshness byte by one so the copy is not just a replay; MAC_FAIL. Align the fault-matrix wording, which assumes in-flight replacement. **Implausible**: labelled "compromised-ECU model", injected inside the ECU process with the valid key; phase 0 to 3 at -6 m/s² gives IMPLAUSIBLE. If MATLAB is up: disagreements = 0. If the physical bench is up: plug in the rogue adapter; SavvyCAN shows the same frames and 0x7F0 verdicts with no CabinGuard code | INJECTED on SIM-BUS or PHYS-BUS |
| 5:05-6:05 | **Act 4: sensor faults and spoofing** | Torch; then the "Blind camera" button; unplug the MPU6050; Hang ECU in normal driving; Restart ECU | **Torch into the webcam:** saturated patch, SNR -20 dB < -15, camera lost, Degraded 1, no MRM. This is *not* the spoof interlock. **Blind camera (INJECTED, -5 dB, EAR 0.05, no beats)** while the seat and wheel show active upright steering: the **spoof interlock** fires, a security-log line appears, the camera is distrusted for 10 s, no MRM. **Unplug the MPU6050:** I2C flag, IMU unavailable, Degraded 2. **Hang ECU in normal driving** (badge: simulated deadline overrun): fault telltale about 0.4 s after the injection (quote the value measured on the jury PC), fail-silent, the driver drives. **Reset/restart:** the ECU, the gateway with its SecOC receiver, the plant and the notifier are rebuilt together (after Phase 4 the gateway accepts only phase 4, so a fresh ECU alone would be rejected as implausible), or the FV is continued; no false rejections | LIVE + INJECTED |
| 6:05-7:00 | **Evidence close** | Results tab | Committed numbers with their scope strings; the fault-matrix report (14 cases × 10 seeds, synthetic); ECU compute p50/p99/max measured here; "What was real in this run". State what is not claimed: no clinical performance; no vehicle performance from the point mass or from CARLA. Close: "same command, only `--imu/--seat/--can` change: that is the Phase 2 bench" | All |

**5-minute cut:** legend 0:30; live + two-sensor beat 0:45; syncope 1:30; attacks 1:00; torch + injected blinding 0:45; close 0:30.

**Q&A fallbacks:**

- A recorded rehearsal run through the same pipeline, badged `RECORDED RUN <date>`, with decisions recomputed.
- Scrub the recording to the detection instant.
- A screen recording of a full rehearsal, presented as a recording.

**Untested option for a live spoof beat:** hold a printed closed-eye face or a tablet video in front of the webcam while the volunteer steers upright on the live rig. The face is found and SNR is about +10 dB, so `camera_ok` stays true and `_spoof_check` can run. It also needs grip ACTIVE, torque above 1 Nm and seat ψ < 0.35 from the live ESP32. Only add it if rehearsals reproduce it.

---

## 7. Phased roadmap

**Effort.** About 12 pw is required for the jury; the optional increments are about 8.5 pw more. That is about 3 calendar weeks of required work for four people.

**Gate:** no optional increment is merged until the required core passes three cold-boot rehearsals.

### MVP (calendar weeks 1-2, about 6 pw): a complete jury demo with no GPU

| Step | Work | Files |
|---|---|---|
| M0 Environment (0.5 pw) | python.org CPython 3.12 x64 venv; exact pins: `scikit-learn==1.6.1`, **mediapipe 0.10.32 or later with `CameraFrontEnd` ported to the Tasks `FaceLandmarker`** (checked on PyPI: 0.10.21 requires `numpy<2`, which cannot load the committed models because they were pickled with NumPy 2; 0.10.30 and later accept NumPy 2 but no longer ship `mp.solutions.face_mesh`, so the port is required, not optional; the 478 FaceLandmarker points keep the Face Mesh numbering, so the indices in `vision.py` stay valid; ship `face_landmarker.task` locally), `opencv-contrib-python` only (never also `opencv-python`), `libusb-package` (the libusb DLL that `gs_usb` needs on Windows), `python-can[multicast]==4.6.1` (the extra brings msgpack), `cantools` 44.2.x, `nicegui` (pin the 3.x current at the freeze two weeks before the jury; 3.18.0 is one day old today), `pyserial`, `numpy`, `cryptography`; offline win_amd64 cp312 wheelhouse | `prototype/requirements-demo.txt` (new); `prototype/pyproject.toml` (`[demo]` extra, `[carla]` extra with `carla==0.9.16`, hardware extra mediapipe pin, package discovery (`[tool.setuptools.packages.find]`) so `cabinguard.demo.ui` is included); `prototype/requirements.txt` (scikit-learn ==1.6.1) |
| M1 Core fixes (1.5 pw) | Section 2.3 items 1-6; send 0x121 and 0x122; extract the attacks so `run_scenario` and the demo share them; fix documentation | `cabinguard/pipeline.py`, `vehicle_gateway.py`, `secoc.py` (verdict reason, keep bool), `can_messages.py` (HealthTx, TelematicsStatusTx), `hardware.py` (CanBus), new `cabinguard/attacks.py`; `run_gateway.py` (dispatch, INIT, docstring); `hardware/README.md` line 50 ("`--can virtual` on both commands" does not cross processes); "aligned with UNECE R157" in `safety_controller.py`; motion training set in the `fusion.py` docstring (it still names only UEA mimics). Tests: new `tests/test_gateway_verdicts.py`; extend `tests/test_security_comm.py::test_dbc_matches_encoder` to 0x121/0x122 |
| M2 Orchestrator, headless (1.5 pw) | Tick thread, command queue, TickRecord, ChannelMux (sim + current in-process webcam + ESP32), FaultOverlay, recorder (JSONL + npz to `data/demo_sessions/`, already git-ignored, with the git commit, the resolved pip freeze, the SHA-256 of every model file, seeds, `acts.toml`, CAN transport and key provenance in each session header), `--headless` prints the `run_realtime.py` trace | `prototype/run_jury_demo.py`; `prototype/cabinguard/demo/{__init__,telemetry,sources,faults,nodes,orchestrator,plants,recorder,can_tap}.py`; `tests/test_demo_mux.py` (an all-sim mux reproduces the simulator's decisions; re-stamping keeps the 0.3 s freshness behaviour) |
| M3 Dashboard (2.5 pw) | Stage and operator pages, built-in road view (SVG + `ui.scene`), cabin panel (SVG sensor map when synthetic), decision, CAN trace, PSAP/V2X, Results tab (scope strings), Edge `--app` launcher, Esc reset, act engine | `prototype/cabinguard/demo/ui/{stage,operator,road_view,cabin,decision,can_panel,psap,results}.py`; `prototype/demo/acts.toml` (stdlib `tomllib`, so no PyYAML); `prototype/demo/CabinGuard_Demo.bat` |

**Exit test for the MVP:** `python -m pytest prototype/tests` is green, and the 7-minute storyline runs with the synthetic, injected and (where available) live channels.

### Required increments (about 6 pw)

| Increment | Effort | Work | Files |
|---|---|---|---|
| I1 Cabin robustness | 1.5 pw | Camera worker as a supervised spawn child; RPPGTracker built with the **measured** frame rate (today a nominal 30 fps; Windows webcams can drop to 15 fps in low light); sleep and reopen on a failed `read()` (today it busy-loops); 640x360 JPEG + landmark subset; staged-video file source with signed consent | `cabinguard/demo/camera_worker.py`; `cabinguard/hardware.py` (`CameraFrontEnd`); `cabinguard/vision.py` if needed |
| I2 ESP32 hardening | 1 pw | Section 5, stage 1 | `cabinguard/hardware.py`; `hardware/esp32_sensor_node/esp32_sensor_node.ino`; `tests/test_hardware.py` |
| I3 Replay tier with fold models | 1.5 pw | Script run **in the user's Colab notebook** (it downloads data; colab-compute skill). It picks 2-3 episodes per class (PhysioNet drivedb normal, vfdb/cudb VF onset with pulseless beats removed, szdb ictal tachycardia; SeizeIT2 motor seizures over PhysioNet walk-climb-drive driving accelerometry). It saves beat times, 100 Hz accelerometry and metadata, plus **fold models** built with `evaluate_fusion.cardiac_models()` / `motion_models()`. The deployed joblibs were fit on every record (`train_motion_real.py`: "trained with every source"). Loaded via `FusionClassifier(cardiac_model=..., motion_model=...)`. Check each dataset's licence before bundling | `prototype/experiments/colab/build_replay_pack.py`, a cell in `CabinGuard_Colab.ipynb`; packs to `data/replay/` (git-ignored); small fold models + manifest in `prototype/models/replay/` if size allows; add `scope` to `external_checks.json` and `training` to `cardiac_branch.joblib` in the same run |
| I4 Evidence close | 0.5 pw | "What was real in this run"; fault-matrix report view; MEASURED-HERE timing summary | `cabinguard/demo/ui/results.py` |
| I5 Rehearsal hardening | 1.5 pw | Preflight (Python version, pins, model load, webcam opens, CRC-valid ESP32 frames, CAN opens, CARLA client/server versions match plus FPS, free port); 1 h soak with zero consecutive overruns; three cold boots with Wi-Fi off; operator checklist card | `cabinguard/demo/preflight.py`; `prototype/demo/CHECKLIST.md` |

### Optional increments (in this order, each gated)

| Increment | Effort | Work | Files |
|---|---|---|---|
| O1 CARLA plant | 2.5 pw | Section 4.2; **delete `prototype/carla_bridge.py`** (no module imports it) | `cabinguard/demo/{carla_plant,carla_worker}.py`; `prototype/experiments/carla_mrm_profile.py` writing `prototype/results/carla_mrm_profile.json` (run on the GPU PC, commit the output) |
| O2 Two-PC / physical CAN bench | 1.5 pw | `--role`, demo DBC, SecOC-protected 0x1A0, persisted FV, third ACKing node, SavvyCAN V220 or CANgaroo v0.16.0 with both DBCs, gateway reaction measured from BLF timestamps | `prototype/demo/cabinguard_demo.dbc`; `cabinguard/demo/nodes.py`; `run_realtime.py` / `run_gateway.py` as thin wrappers |
| O3 MATLAB Tier 0 (+Tier 1 if VNT) | 1.5 pw (+0.5) | Section 4.1; CMAC validated against RFC 4493 and Python-exported vectors | `cabinguard/demo/export.py` (TCP server); `prototype/matlab/{CabinGuardMonitor,cg_decode,cg_cmac,cg_cmac_selftest,analyze_session,post_run_check}.m`, `post_run_check.slx`; `prototype/tests/data/secoc_vectors.json` |
| O4 Lateral decision B | 1 pw | `Shoulder_Req` on bit 31, CARLA lane change, paper sentence | `cabinguard_mrm.dbc`, `can_messages.py`, test, `.tex` line 152 (run `tools/check_manuscript.py` after editing) |
| O5 ESP32 actuator node | 2 pw | Section 5, stage 3 | `hardware/esp32_actuator_node/` |
| O6 MCAP export / ROS 2 mirror | 0.5 / 1 pw | Section 4.3 | `cabinguard/demo/mcap_export.py`; separate `ros2_mirror/` |

---

## 8. Risks and demo-day checklist

### Risks

| Risk | Mitigation |
|---|---|
| Fresh install breaks the webcam path: the repo's `mediapipe>=0.10` resolves to 1.1.0 without `mp.solutions.face_mesh` (an existing bug), and 0.10.21 needs `numpy<2`, which cannot load the NumPy 2 models | Port `CameraFrontEnd` to the Tasks FaceLandmarker in M0, pin mediapipe 0.10.32+, ship the `.task` file locally, install from the wheelhouse |
| A deadline overrun becomes a real fail-silent on stage | Camera and CARLA in child processes; UI off the tick thread; 1 h soak; p99 shown on screen. Do not weaken the rule |
| A synthetic number is read as real performance | Computed badges on every panel; Results tab reads committed JSON only; CARLA figures always "synthetic simulation (CARLA 0.9.16 vehicle model)"; no bus latency from a virtual bus |
| Replay shows models scoring their own training data | Fold models only (I3), named on screen |
| False security alarms | Section 2.3 fixes, with tests, before 0x121/0x122 or a restart button exist |
| Live beats do not reproduce (a healthy presenter has a pulse; a staged convulsion is not a clinical seizure; venue lighting breaks rPPG) | Syncope pulse and seizure IMU come from replay or synthetic; live beats only if rehearsed; IR ring or desk lamp; never quote live detection rates |
| Cross-process CAN on Windows | Single process by default. `udp_multicast` gained Windows support in python-can 4.6.0 (PR #1914) although its docs page still says otherwise; untested on Windows here, best-effort delivery. Prefer the Kvaser virtual driver or physical adapters for a second process |
| CARLA: unknown GPU, version mismatch, sync mode left on, slow motion | Optional only; preflight FPS; tick timeout; `finally`/`atexit`; automatic visible fallback to the point mass |
| MATLAB licence or jitter | Read-only consumer; licence check first |
| Lateral mismatch (paper vs CAN) | Decide A or B before the Phase 2 paper |
| Privacy | Frames shown, never stored; landmarks only unless consent; staged video needs signed consent; nothing biometric in git |
| Scope creep | Required core first; optional increments gated by rehearsal |

### Demo-day checklist

- Mains power, high-performance power plan; sleep, USB selective suspend, Windows Update and notifications off.
- Wi-Fi off. Firewall prompts accepted earlier (the default profile binds 127.0.0.1 only).
- Camera privacy switch on, no other app holding the webcam, IR ring or lamp in place.
- CP210x or CH340 driver installed; ESP32 found by VID/PID; MPU6050 lead seated; spare ESP32, USB cable and adapter.
- Preflight all green or deliberately grey.
- `python -m pytest prototype/tests` passes on this laptop.
- Projector tested at 1920x1080 and 1366x768; speaker volume checked for the chime.
- CARLA (if used): server started and warmed up; client/server versions match; FPS measured that day; second screen ready.
- Recorded rehearsal sessions on the laptop and a USB stick; screen recording as the last resort.
- A spare laptop cloned from the wheelhouse.
- Esc reset rehearsed. The fallback ladder card printed: physical bus, then in-process bus; CARLA, then built-in view; live, then replay/synthetic; everything, then the recorded run, then the video.

---

## 9. Open questions for the user

1. **GPU.** Exact model and VRAM on the jury PC, if any? Is there a separate desktop with an NVIDIA card at 6 GB or more (8 GB recommended) that can come to the venue? This decides whether CARLA is on the projector or on a second screen.
2. **OS.** Windows 10 or 11 on the jury machine? Laptop or desktop? How many video outputs?
3. **MATLAB.** Release (R2025a/b or R2026a)? Licence type (Home, Student, Campus-Wide, or competition)? Output of `ver`, and which of Vehicle Network Toolbox, Simulink and Instrument Control are licensed? Is the team willing to apply for MathWorks competition software?
4. **Hardware on hand.** A second laptop? Any USB-CAN adapters (model: CANable, candleLight, PEAK, Kvaser)? Is the ESP32 rig built, and which sensors work today? Which webcam? Is there a car seat or office chair with a headrest?
5. **Lateral manoeuvre.** Option A (in-lane stop; fix paper line 152, the state names and the `fault_matrix.py` text) or option B (`Shoulder_Req` on bit 31)?
6. **Jury format.** Slot length (5, 7 or 10 min)? One projector or two? Does the jury expect ROS or MATLAB specifically? Does a point mass or CARLA count as an "approved simulated vehicle environment" for Phase 2?
7. **Team and time.** How many people, and how many weeks until the jury and until the Phase 2 paper deadline?
8. **Consent.** Will a team member consent to a recorded staged video and to recorded biometric-derived features for rehearsals?

---

## Appendix A: corrections to the proposals and the research, checked against the repo

| Claim | Correction | Evidence |
|---|---|---|
| A live torch into the webcam fires the spoof interlock (Proposals 1, 2, 4) | It gives SNR -20 dB < -15, so `camera_ok` is false and `_spoof_check` returns false: Degraded 1 only. The interlock needs the simulator's -5 dB model or the INJECTED overlay | `hardware.py` line 198; `config.py` line 20; `feature_extraction.py` lines 66-67; `watchdog.py` lines 68-70 |
| "Phase 2 at 4 s" (Proposal 3) | Phase 2 starts at `PHASE_1_DURATION_S = 3.0`; `PHASE_2_START_S = 4.0` is unused | `safety_controller.py` lines 82-83 |
| Tamper flips one bit | XOR 0x0B on byte 0 flips three bits | `pipeline.py` line 232 |
| Replay is always counted as `replay` / always as `mac` | Replaying an older captured frame counts under `mac`; replaying the most recently accepted frame reconstructs to last_fv + 256 > max_gap and counts under `replay` | `secoc.py` `reconstruct` / `verify` |
| An ECU restart is rejected "as replays" (Proposal 1) | Counted under `mac` until the FV is continued (`start_fv` exists) | `secoc.py` `SecOCSender(start_fv)` |
| The gateway EPB only clamps at speed ≤ 0.0 (Proposal 2) | True only on the fail-operational path; normally the EPB follows the ECU's Phase 4 command at ≤0.05 m/s | `vehicle_gateway.py` `tick`; `safety_controller.py` line 110 |
| "ECU alive timeout at t=0" always | Only when the gateway ticks before the first frame (cross-process); in-process, receive runs before tick | `pipeline.py` `VehicleSide.step` |
| 100 IMU frames/s is about 4% bus load (Proposal 3) | About 2.2-2.7% of 500 kbit/s (≤135 bits per 8-byte standard frame) | arithmetic |
| `udp_multicast` does not work on Windows (research digest) | Windows support was added in python-can 4.6.0; the docs page is out of date; untested on Windows here | python-can 4.6.1 source and changelog |
| mediapipe 0.10.21 is "the last release" with face_mesh | Not established (only 0.10.21, 0.10.30 and 1.1.0 were inspected; issue #6192 says the removal came in 0.10.31). Superseded by Appendix B item 1: 0.10.21 needs `numpy<2`, so port to the FaceLandmarker instead | research digest; PyPI metadata |
| NiceGUI `native=True` with plain pins | Needs pywebview, which is not in the pins; this plan uses Edge `--app` instead | NiceGUI `ui_run` |
| CARLA agents come with `pip install carla` | They do not; take them from the CARLA zip's `PythonAPI/carla/agents` | wheel contents |
| Dataset replay through the deployed models is a held-out demo (Proposal 2, Proposal 1 optional) | It is in-sample; use `evaluate_fusion.cardiac_models()` / `motion_models()` fold models | `train_motion_real.py` line 40 |
| "`train_motion_real.fit` does not exist" (honesty judge) | It does exist (`train_motion_real.py` line 271). The fold-model recipe is still `evaluate_fusion.cardiac_models` / `motion_models` | `train_motion_real.py` line 271 |
| SavvyCAN shows MAC_FAIL (Proposal 3) | No open tool verifies SecOC; SavvyCAN shows raw FV/MAC and the decoded 0x7F0 verdict signal only | SavvyCAN, Wireshark sources |
| "VNT does not support CANable/gs_usb" | True on Windows; on a Linux host VNT's SocketCAN support (reported since R2023b) can reach them | MathWorks excerpts |
| Pull the ECU's CAN connector on a two-node bus with a listen-only sniffer (Proposal 3) | The remaining node's frames get no ACK; keep a third ACKing node and a dashboard fed from local telemetry | CAN protocol |
| `hardware/README.md` line 50: `--can virtual` on both commands | python-can `virtual` is in-process only; two processes never see each other's frames | `hardware/README.md` line 50; `run_realtime.make_bus` |
## Appendix B: findings of the final critic pass

"Verified" means checked against the repository code or PyPI before this plan was committed. "Critic" means reported by the critic with its own evidence, not re-checked. Every item is folded into the text above unless it says otherwise.

| # | Finding | Status | Where it changed the plan |
|---|---|---|---|
| 1 | mediapipe 0.10.21 requires `numpy<2`; the committed models were pickled with NumPy 2 and `motion_branch.joblib` fails to load under NumPy 1.26, so the ECU cannot start | Verified on PyPI (0.10.21 metadata: `numpy<2`); load failure reported by the critic | M0: port `CameraFrontEnd` to the Tasks FaceLandmarker with mediapipe 0.10.32+ |
| 2 | mediapipe 0.10.30 and later accept NumPy 2 but ship no `mp.solutions.face_mesh`; the repo's `mediapipe>=0.10` therefore installs a version the current `hardware.py` cannot use | Verified on PyPI (0.10.30, 0.10.31, 0.10.32 wheels: no `solutions/face_mesh`, `face_landmarker` present) | M0, Risks. **This is an existing bug in the repository, independent of the demo** |
| 3 | Install `opencv-contrib-python` only; mediapipe depends on it and two cv2 distributions conflict | Critic (mediapipe metadata verified) | M0 |
| 4 | Fault reaction time is not "within 0.3 s" | Verified: in-process, hang injected at 8.0 s, last valid frame 8.1 s, ALIVE_TIMEOUT logged at 8.4 s, i.e. 0.4 s after the injection | Acts 2 and 4: quote 0.4 s, re-measure on the jury PC (rule 28) |
| 5 | A hang in Phase 2 gives no DENM and no door unlock: fail-operational never raises `GatewayState.phase`, and `VehicleSide` builds the DENM only at phase 3 or above | Verified in `vehicle_gateway.py` `tick` and `pipeline.py` `VehicleSide.step` | Act 2 hangs in Phase 3, the tested path |
| 6 | After Phase 4, `ALLOWED_NEXT_PHASE[4] = {4}`, so a fresh or restarted ECU's phase-0 frames are rejected as implausible | Verified in `vehicle_gateway.py` | Reset rebuilds ECU, gateway, plant and notifier together |
| 7 | A tamper "copy injected" after the genuine frame reconstructs to a stale FV and counts as `replay`, not `mac` | Critic | Attacker advances the FV byte; align the fault-matrix wording |
| 8 | `time.monotonic()` on Python 3.12 for Windows has about 15.6 ms resolution | Critic (consistent with CPython 3.13 release notes) | `time.perf_counter()` for frame stamps and timing |
| 9 | The gateway, not the ECU, must sense the brake | Verified (`_plausible` comment and logic) | ESP32 stage 1, 0x1A0 |
| 10 | The ESP32 actuator node must not act on unauthenticated 0x7F0 | Design review | Stage 3 |
| 11 | Two-PC CARLA: a client-side camera streams raw frames over the network | Critic | Use the server's spectator window |
| 12 | The point mass makes "commanded vs measured" decel circular, and the 0 to -3.2 m/s² step gives about 32 m/s³ jerk | Verified (`safety_controller.py` sets the decel in one step) | Road view label; no jerk assertion until a ramp exists |
| 13 | A UI thread is not isolated from the 100 ms ECU under the GIL; `spawn` children re-import the main module | Critic | UI as its own process on the TCP feed |
| 14 | Edge windows sharing one profile ignore launch switches | Critic (untested) | Separate `--user-data-dir` |
| 15 | MATLAB cannot read `.npz`; its "independent" check shares Python's capture | Design review | `jsondecode` on JSONL; on-screen caveat |
| 16 | `gs_usb` on Windows needs a libusb DLL | Critic (gs-usb depends only on pyusb) | `libusb-package` in M0 |
| 17 | `cabinguard.demo.ui` would be dropped from a non-editable install | Critic | Package discovery |
| 18 | Recorded runs need provenance (commit, pip freeze, model hashes, seeds, acts, transport, key) for the Phase 2 reproducibility criterion | Design review | Recorder |
| 19 | Replayed "pulse" is ECG R-peak times, not a pulse recording; the live rPPG patch must not look like it measured the replay | Verified (`extract_cardiac.py` uses ECG beats) | Act 1 badge, greyed patch |
| 20 | The cardiac model is ECG-trained and not validated on rPPG | Verified (`extract_cardiac.py`) | Decision panel badge |
| 21 | The follower car slowing after the DENM is not modelled | Verified (no V2X receiver in the repo) | Badged illustrative |
| 22 | "Hang ECU" adds 1 s to the measured compute time; it is a simulated deadline overrun, not a process stall | Verified (`pipeline.py` `step`) | Badges in Acts 2 and 4 |
| 23 | SeizeIT2 is recorded at 25 Hz; the replay must use the training resampler and say so | Verified (`extract_seizeit2.py`, `train_motion_real.py`) | Act 2 badge, I3 |
| 24 | Live spoof-interlock hazard: with eyes closed, head level, grip ACTIVE and torque above 1 Nm, `_spoof_check` fires and distrusts the camera for 10 s, which can bleed into the next act | Critic | **Not yet folded in:** add to the act notes and rehearse with the potentiometer centred |
| 25 | Each Phase 2 event class should have at least one beat driven by live sensors | Design review | Optional STAGED seizure beat with the live headrest IMU |
| 26 | The user asked for a cabin view; the synthetic profile showed none | Design review | Schematic avatar, badged SYNTHETIC |
| 27 | MATLAB could also replay recorded gateway commands through a Simulink vehicle model for Q&A | Design review | **Not folded in:** optional, offline, badged SIM-VEHICLE |
| 28 | Documentation errors beyond `hardware/README.md` line 50: line 21 ("same PC on a virtual channel") and the `run_gateway.py` docstring repeat the claim that python-can `virtual` crosses processes | Critic | M1 documentation fixes |
| 29 | The committed `fault_matrix.json` still says "stop on shoulder" and models tamper as in-flight replacement, which contradicts an in-lane demo stop and a "copy injected" attack | Verified (`fault_matrix.py` expected strings) | Resolve option A/B (section 9, question 5) before showing the Results tab |
