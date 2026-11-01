# Closed-loop MATLAB/Simulink simulation

The CabinGuard take-over chain in closed loop with a vehicle that drives a
Driving Scenario Designer road, with radar and camera perception of other road
users. It asks whether the minimum-risk manoeuvre behaves as designed in
traffic. It does not measure detection: the AI is replaced by a surrogate
detector with a fixed delay.

Evidence class: **synthetic simulation**. Other cars and pedestrians follow
fixed scripts and do not react to the ego vehicle.

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

### Run one case yourself

```matlab
o = struct('type','highway','seed',1,'sys',1,'t_on',2,'ev',1,'profile','github');   % ev: 1 syncope, 2 seizure, 0 conscious
r = cg_auto_run(o);          % opens figures, prints the timeline
```

Main options (all listed by `help cg_auto_opts`):

- `type` highway, rural or city, and `seed` (scene number). A scene depends on
  seed, type and stop time `T`: quote them together.
- `ev` 1 syncope, 2 seizure, 0 conscious driver; `t_on` the onset time.
- `fault`: 1 camera lost, 2 IMU lost, 3 seat lost, 4 host hang, 5 forged
  command, 6 replayed, 7 implausible deceleration, 8 cellular down, 9 camera
  blinded, 10 all bearers down, 11 phase skipped; `t_fault` when it starts.
- `fa = [start duration mode]` false detector evidence (mode 1 camera only,
  2 all sensors); `t_can` the time the conscious driver brakes.
- `mode` `'full'` (brake and move right when free) or `'brake_only'`;
  `plant` 1 detailed plant, 0 simple plant.

Many scenes at once:
`cg_auto_batch(3, {'highway','rural','city'}, {'full','brake_only'}, 1:3, struct('sys',1,'ev',1,'profile','github'))`.
Your own road: export a scenario from Driving Scenario Designer as a function
and run `cg_auto_run(struct('file','yourScenarioFunction','ego',1,'sys',1,'ev',1))`.

### Reading the results

- `results/suite_system.txt` and `.csv`: one row per case with take-over time,
  eCall time, rejected frames, collision, smallest gap and pass.
- A collision row names the actor, the side (ahead or behind) and the impact
  speed. A collision counts as unavoidable only if the deceleration needed at
  the take-over is 8.0 m/s² or more (the car's limit is about 8.5).
- An "invalid scene" is a contact before the driver became unresponsive; it is
  discarded, not counted as a failure.

### Known errors and fixes

| Message | Fix |
|---|---|
| `Unrecognized function or variable 'cg_sys_detector'` | the folder is not on the path: `cd` into it and `addpath(pwd)` |
| `Unrecognized field name "fault"` | call `cg_auto_run` or `cg_auto_suite`, not the block code directly (they fill in the defaults) |
| Scenario Reader reads `cabinguard.mat` or complains about the file | `bdclose all; clear all; cg_auto_build` (the run script resets the source to the workspace variable `ca_scn`) |
| `Jerk FallingSlewLimit supports only negative or zero` | `cg_auto_defaults(true)`, then run again |
| A different result after changing `T` | expected: the scene changes with `T` |

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

Two sets of timings (option `profile`):

| | design values (default) | `profile = 'github'` (Python system) |
|---|---|---|
| detector delay | 1.0 s, plus a 3 s evidence ramp and verification | 9.0 s syncope, 9.5 s seizure, so the alert comes 12.0 or 12.5 s after onset (the median latency in `fusion_metrics.json`, not a result of this model) |
| alert to hazards | 2 s | 4 s |
| alert to braking (take-over) | 4 s | 10 s |
| minimum-risk deceleration | −3 m/s² | −3.2 m/s² |
| speed and run length | scene value (25.8 m/s), 40 s | 100 km/h, 45 s |

## Closed-loop test results

Five tests run in the full Simulink model with the detailed plant
(`cg_auto_suite('github')`): highway scene 1, 100 km/h, 45 s, incapacitation
at 2 s, and the Python system's timings. When everything works the timeline is
alert at 14 s, hazards and eCall at 18 s, take-over at 24 s and standstill at
about 33 s. The raw numbers, one chain figure (`suiteNN_chain.png`) and one
vehicle figure (`auto_suiteNN.png`) per test, and the overview are in
[`results_final/suite_github/`](results_final/suite_github).

![All five test cases: speed, take-over time, emergency message delivery and gateway rejections](results_final/suite_github/suite_overview.png)

| # | Test | Injected | Must show | Alert | Hazards and eCall | Take-over | eCall delivered | Outcome |
|---|---|---|---|---|---|---|---|---|
| 1 | Syncope | syncope at 2 s | take-over near 24 s, controlled stop | 14.0 s | 18.0 s | 24.0 s | 18.0 s | stopped in 8.8 s over 123 m; rear-end touch by the scripted follower at 30.5 s, 0.7 m/s |
| 2 | Seizure | seizure at 2 s | same chain with its own detector delay (9.5 s), take-over near 24.5 s | 14.5 s | 18.5 s | 24.5 s | 18.5 s | stopped in 8.8 s over 123 m, no collision (smallest gap 0.11 m) |
| 3 | Conscious driver | nothing | no alert, no take-over | none | none | none | none | no alert and no take-over, as required |
| 4 | Camera lost | camera fails at 2 s | take-over still happens, a little later (degraded mode) | 14.6 s | 18.6 s | 24.6 s | 18.6 s | degraded mode, +0.6 s, stopped, no collision |
| 5 | Cellular down | cellular unavailable | take-over unchanged; eCall falls back to SMS | 14.0 s | 18.0 s | 24.0 s | 26.0 s by SMS | stop unchanged; same follower touch as test 1 |

Source: [`results_final/suite_github/suite_system.csv`](results_final/suite_github/suite_system.csv).
The gateway rejected no frame in any test (no attack was injected here; the
attack cases are in the Python fault matrix).

**What each test proves.**

1. **Syncope:** the whole chain end to end: detector, host verification,
   alert, hazards with the eCall, gateway-approved braking, stop.
2. **Seizure:** the second incapacitation type follows the same chain with its
   own detector latency.
3. **Conscious driver:** no false take-over when nothing is wrong.
4. **Camera lost:** graceful degradation: the host keeps working with the
   remaining sensors and reports a degraded mode, at a cost of 0.6 s.
5. **Cellular down:** the manoeuvre never waits for the eCall: the stop is
   unchanged and the message falls back to SMS.

![Syncope test: host state, gateway phase, take-over request and emergency call over time, with speed and acceleration command](results_final/suite_github/suite01_chain.png)

**The two collision flags.** Tests 1 and 5 are flagged only because the
scripted car behind, which does not react to the ego car, touches it at
0.7 m/s after the take-over; at the take-over only 0.3 m/s² of braking was
needed for anything ahead. In test 1 the right side was flagged as occupied,
so the car braked in its lane rather than moving to the shoulder. The contact
is reported, not tuned away. Test 3's contact with a slow car ahead at 33.6 s
happens with no take-over, because the simulated conscious driver does not
brake for traffic; the scene is marked invalid and not counted.

**What follows from it.** With these timings the car keeps its speed without
driver control for about 22 s (about 600 m at 100 km/h) before braking begins,
and the model has no emergency braking of its own in that interval. Phase 2
adds the real detector in the loop, reactive traffic, protection of that
interval (emergency braking and a follower warning) and more scenes. One scene
per test: the results are indications, not statistics.

## Limits

1. Simulation only: no hardware, no vehicle tests.
2. The detector is a surrogate with a fixed delay; the 12 s latency is the
   median of the Python evaluation, not a result of this model.
3. All timings are design values or values taken from the Python system.
4. Other cars follow scripts and do not react, including the follower behind.
5. The simulated driver does not brake for traffic.
6. Between onset and take-over the car holds its speed and has no emergency
   braking of its own: about 22 s with the Python system's timings.
7. Authentication is a pass/fail flag: SecOC, ECDSA and ECIES are implemented
   and tested only in the Python prototype.
8. As in the Python gateway, a frame with a valid MAC and the next phase number
   is accepted early, and if the host dies before the hazards phase nothing is
   actuated.
9. The MATLAB and Python implementations of the chain are kept in step by
   hand.
10. Few scenes: the results are indications, not statistics.
