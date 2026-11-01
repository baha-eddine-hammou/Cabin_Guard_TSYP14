# Closed-loop MATLAB/Simulink simulation

`CabinGuard_MATLAB_simulation.slx` (MATLAB R2024a) runs the CabinGuard response
logic in closed loop with a vehicle that drives a scenario from the Driving
Scenario Designer, with radar and camera perception of other road users. It
asks whether the minimum-risk manoeuvre behaves as designed in traffic. It does
not measure detection: its detector is a stand-in.

Evidence class: **synthetic simulation**. Other cars and pedestrians follow
fixed scripts and do not react to the ego vehicle.

## What is inside

The `CabinGuard` subsystem has six MATLAB Function blocks:

| Block | Role | Matches |
|---|---|---|
| `Det` | stand-in for the AI detectors: after the incapacitation onset and a set delay, the evidence for the true class ramps to +4 and the other class to −2 on all four branches; it can also inject a false alarm on the camera branches or on all branches | replaces the trained branches of [`3_Detection_AI_Methodology`](../../3_Detection_AI_Methodology) |
| `Drv` | driver model (lane keeping and speed hold) and the incapacitation: flaccid driver for syncope; clenched grip, then clonic torque for a seizure; a conscious driver can cancel a false alarm | the scenario simulator in Python |
| `Flt` | fault and attack injector: camera, IMU or seat lost; host hang; forged, replayed, implausible or phase-skipping frames; cellular or all bearers down; camera blinding | the 14-case fault matrix |
| `Host` | bounded-evidence fusion (c = 3, Γ = 0.85, prior 0.8/0.1/0.1), 2 s verification, two-sensor rule, camera interlock, degraded modes and the MRM state machine | `cabinguard/fusion.py`, `watchdog.py`, `safety_controller.py` |
| `Gw` | gateway: accepts a frame only if authentic and fresh, in phase order, and with braking between 0 and −4 m/s²; 300 ms alive timeout; completes a manoeuvre already under way if the host is lost | `cabinguard/vehicle_gateway.py` |
| `Tel` | emergency message delivery timing: cellular retries with 1, 2 and 4 s backoff, then SMS, then every 30 s | `cabinguard/emergency_link.py` |

Around it: a Scenario Reader, three radar detection generators (front, rear,
right side) and a vision lane detector, per-object in-path and required-braking
checks, a Lane Keeping Assist (MPC) controller with a PID speed loop, and a
vehicle plant with longitudinal wheel blocks. Fixed step 0.01 s, stop time
45 s. Signals are logged to `calog` and `syslog`.

The cryptography is abstracted to "MAC valid" and "fresh" flags; the real
SecOC, ECDSA and ECIES are implemented and tested in the Python prototype.

## Requirements

Simulink, Automated Driving Toolbox (scenario reader, radar and vision
detection generators), Model Predictive Control Toolbox (Lane Keeping Assist
System block), and the vehicle wheel library blocks (Vehicle Dynamics
Blockset).

## Running it

The model reads its scenario and parameters from the MATLAB workspace:
`ca_scn` (the driving scenario), `ca_pv` (event, onset time, speed, fault and
manoeuvre parameters), `ca_det` (detector delay and false alarm), `ca_plant`,
`ca_sys`, `ca_ego_id`, `ca_X0`, `ca_Y0`, `ca_psi0`, `ca_v0`, `ca_t_act`,
`ca_a_comf`, `ca_a_lo`, `ca_d0`, `ca_edge`, `ca_clear`, `ca_hw`, `ca_absvel`,
`ca_wn`, `ca_vlat`, `ca_min_shift`, `ca_lw0`, `ca_kfeas`, `ca_jup`, `ca_jdn`,
`ca_go_phase` and the `ca_lka_*` settings. The MATLAB scripts that set them
and run the scenarios (`cg_auto_*.m`) are not in this folder yet, so the model
does not run on its own; add them here together with the result files they
write.

## Caveats

- `Det` is not the trained detector, so these runs say nothing about
  detection performance.
- Only the response logic is shared with the Python prototype; the two
  implementations are kept in step by hand.
- Results are tendencies from a limited set of scenes, not statistics.
