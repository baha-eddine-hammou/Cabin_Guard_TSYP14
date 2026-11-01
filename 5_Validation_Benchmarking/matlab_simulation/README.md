# Closed-loop MATLAB/Simulink simulation

The CabinGuard take-over chain in closed loop with a vehicle that drives a
Driving Scenario Designer road, with radar and camera perception of other road
users. It asks whether the minimum-risk manoeuvre behaves as designed in
traffic. It does not measure detection: the AI is replaced by a surrogate
detector with a fixed delay.

Evidence class: **synthetic simulation**. Other cars and pedestrians follow
fixed scripts and do not react to the ego vehicle.

`MANUAL_SIMULATION.md` is the full user manual; `RESULTS_github_profile.md`
gives the closed-loop results with the Python system's timings.

## Run it

Requirements: MATLAB with Simulink, Automated Driving Toolbox (driving
scenario, Scenario Reader, radar and vision detection generators), Model
Predictive Control Toolbox (Lane Keeping Assist System block), Vehicle Dynamics
Blockset (wheel and disc-brake blocks of the detailed plant). No GPU, hardware
or internet.

```matlab
cd 5_Validation_Benchmarking/matlab_simulation
bdclose all; clear all; clc
cg_auto_build                 % builds CabinGuardAuto.slx from the scripts
cg_sys_unittest               % 28 checks of the chain without Simulink: expect "28 passed, 0 FAILED"
cg_auto_suite('quick')        % 6 closed-loop runs; figures, csv and txt go to results/
cg_final_run('fast')          % the scenarios used for the write-up, collected in results_final/
```

`CabinGuard_MATLAB_simulation.slx` is a built copy of the model (MATLAB
R2024a), kept so the block diagram can be opened without running the build;
`cg_auto_build` regenerates the same model as `CabinGuardAuto.slx`. Opened
directly, the model needs the workspace variables (`ca_*`) that `cg_auto_run`
sets, so start from the scripts.

## What is simulated

![Top level of the Simulink model: ego plant, scenario reader, sensors and guidance; the CabinGuard supervisor; monitoring and logging](figures/simulink_top_level.png)

The top level of the model has three areas:

1. **Ego plant, state packaging, scenario reader, sensors, GNC:** the vehicle
   plant (`Vehicle`) feeds its pose to the Scenario Reader (`SR`), which drives
   the vision lane detector and three radar detection generators (front, rear,
   right side); guidance, navigation and control (`GNC`) turns their detections
   into the steering and acceleration commands.
2. **Supervisor (CabinGuard) and go command:** the `CabinGuard` subsystem (the
   chain in the `cg_sys_*` scripts) decides when the car takes over; `SysSel`
   switches between that decision and a fixed timer (`TimerGo`).
3. **Monitoring, stop condition and logging:** signals are logged to `calog`,
   and the run stops if a steering or acceleration command becomes NaN.


Driver incapacitated (syncope or seizure) → surrogate detector → fault
injection → host (bounded-evidence fusion, 2 s verification, two-sensor rule,
camera interlock, MRM state machine) → gateway (authenticated commands, 300 ms
alive timeout, deceleration limited to −4 to 0 m/s², phase order, jerk limit) →
take-over → perception, decision, guidance and control from Simulink blocks →
detailed longitudinal plant and bicycle lateral model. Telemetry: eCall by
cellular with retries, then SMS.

| Script group | Role |
|---|---|
| `cg_sys_*.m` | the CabinGuard chain: `cg_sys_detector` (surrogate), `cg_sys_driver`, `cg_sys_faults`, `cg_sys_host`, `cg_sys_gateway`, `cg_sys_telem`; `cg_sys_unittest` checks them without Simulink |
| `cg_auto_*.m` | the closed-loop vehicle model: build, plant, scenes, options, single runs, batches, evaluation |
| `cg_final_run.m` | the scenarios used for the write-up |
| `cg_dsd_*.m` | an earlier Driving Scenario Designer model with a behaviour-cloning controller, kept for comparison |

With `profile = 'github'` the timings follow the Python system: alert 12 s
after onset (the median latency of `fusion_metrics.json`, not a result of this
model), hazards 4 s later, braking at −3.2 m/s² 10 s after the alert, 100 km/h.

## Results reported by the team (one scene, profile 'github')

From `RESULTS_github_profile.md`, produced by `cg_auto_suite('github')`; the
result files themselves are written to `results/` when the suite is run and
are not committed.

- The chain timeline matches the Python system: alert at onset + 12 s, hazards
  + 4 s, take-over + 10 s; the stop took 8.8 s over 123 m.
- In a syncope run and in the cellular-down run, the scripted car behind
  rear-ended the ego car at 0.7 m/s; it does not react to the ego car braking.
  With a camera lost, the alert came 0.6 s later (degraded mode).
- With a conscious driver, CabinGuard raised no alert.
- With these timings the car has no driver control for about 22 s (about 600 m
  at 100 km/h) before braking begins, and has no emergency braking of its own
  in that interval.

One scene, so these are indications, not statistics.

## Limits

The detector is a surrogate; the latency is taken from the Python evaluation.
Authentication is a pass/fail flag: SecOC, ECDSA and ECIES are implemented and
tested only in the Python prototype. Other traffic follows scripts. The two
implementations of the chain (MATLAB and Python) are kept in step by hand.
