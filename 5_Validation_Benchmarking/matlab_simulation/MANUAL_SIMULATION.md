# CabinGuard-ADI: closed-loop simulation (MATLAB / Simulink) - user manual

This folder is a **simulation-only proof of concept** of the CabinGuard-ADI take-over chain. It does not contain the AI. The AI is replaced by a
**surrogate detector** with a fixed delay. The numbers it produces are simulation results, not vehicle results.

## 1. What you need
- MATLAB with Simulink. Products used by the model: Simulink, Automated Driving Toolbox (Driving Scenario, Scenario Reader, radar and vision
  detection generators), Vehicle Dynamics Blockset (wheel and disc-brake blocks of the detailed plant). Type `ver` to check what you have.
- No other files. Windows, macOS or Linux.
- Not needed: GPU, hardware, internet.

## 2. First run (about 10 minutes), step by step
1. Copy this folder to your PC and open MATLAB in it: `cd path\to\simulation`
2. `bdclose all; clear all; clc`
3. `cg_auto_build`  -> builds `CabinGuardAuto.slx` (wait for `Saved`).
4. `cg_sys_unittest` -> 28 checks of the CabinGuard chain without Simulink. Expected: `28 passed, 0 FAILED`.
5. `cg_auto_suite('quick')` -> 6 closed-loop runs in the full model. Results go to the `results` folder (figures, csv, txt).
6. `cg_final_run('fast')` -> the scenarios used in the paper. Everything is copied to `results_final`.

`cg_final_run('all')` adds the 20-case suite and nine random scenes (2 to 3 hours).

## 3. What is simulated (one line each)
Driver incapacitated (syncope or seizure) -> surrogate detector -> fault injection -> Host (bounded-evidence fusion, 2 s verification,
two-sensor rule, camera interlock, MRM state machine: normal, ALERT, HAZARD, BRAKE, STANDSTILL) -> Gateway (authenticated commands, 300 ms alive
timeout, deceleration limit -4 to 0 m/s^2, phase-order rule, jerk limit) -> take-over request -> Perception / Decision / Guidance / Control
built from Simulink blocks -> detailed longitudinal plant + bicycle lateral model on a Driving Scenario Designer road. Telemetry: e-call by
cellular with retries, then SMS.

## 4. Two sets of timings (option `profile`)
| | design values (default) | `profile = 'github'` (Python system) |
|---|---|---|
| detector delay | 1.0 s (+3 s evidence ramp and verification) | 9.0 s syncope / 9.5 s seizure, so ALERT = onset + 12.0 / 12.5 s (median of `fusion_metrics.json`) |
| ALERT to HAZARD | 2 s | 4 s |
| ALERT to BRAKE (take-over) | 4 s | 10 s |
| minimum-risk deceleration | -3 m/s^2 | -3.2 m/s^2 |
| highway speed, run length | scene value (25.8 m/s), 40 s | 100 km/h, 45 s |

## 5. Run one case yourself
```matlab
o = struct('type','highway','seed',1,'sys',1,'t_on',2,'ev',1,'profile','github');   % ev: 1 syncope, 2 seizure, 0 conscious
r = cg_auto_run(o);          % opens figures, prints the timeline
```
Main options (all listed in `help cg_auto_opts`):
- `type` highway / rural / city and `seed` (scene number). A scene depends on seed, type and stop time `T`: quote them together.
- `ev` 1 syncope, 2 seizure, 0 conscious driver. `t_on` onset time.
- `fault`: 1 camera lost, 2 IMU lost, 3 seat lost, 4 host hang, 5 forged command, 6 replayed, 7 implausible decel, 8 cellular down, 9 camera blinded,
  10 all bearers down, 11 phase skipped. `t_fault` when it starts.
- `fa = [start duration mode]` false detector evidence (mode 1 camera only, 2 all sensors); `t_can` time the conscious driver brakes.
- `mode` 'full' (brake and move right when free) or 'brake_only'.
- `plant` 1 detailed plant, 0 simple plant.

Many scenes: `cg_auto_batch(3, {'highway','rural','city'}, {'full','brake_only'}, 1:3, struct('sys',1,'ev',1,'profile','github'))`.

Your own road: export a scenario from Driving Scenario Designer as a function and run
`cg_auto_run(struct('file','yourScenarioFunction','ego',1,'sys',1,'ev',1))`. Keep your tuned model under another name so a rebuild does not overwrite it.

## 6. Reading the results
- `results/suite_system.txt` and `.csv`: one row per case. Columns: take-over time, e-call time, rejected frames, collision, minimum gap, pass.
- A collision row names the actor, the side (ahead or behind) and the impact speed.
- `suiteNN_chain.png`: top = chain states over time, bottom = speed and acceleration command.
- The rule for "unavoidable": a collision is called unavoidable only if the deceleration needed at the take-over is 8.0 m/s^2 or more (the car's limit is about 8.5).
- "invalid scene": contact before the driver became unresponsive. The scene is discarded, not counted as a failure.

## 7. Known errors and fixes
| Message | Fix |
|---|---|
| `Unrecognized function or variable 'cg_sys_detector'` | the folder is not on the path: `cd` into this folder, `addpath(pwd)` |
| `Unrecognized field name "fault"` | call `cg_auto_run` / `cg_auto_suite`, not the block code directly (they fill in defaults) |
| Scenario Reader reads `cabinguard.mat` or complains about the file | `bdclose all; clear all; cg_auto_build` (the run script resets the source to the workspace variable `ca_scn`) |
| `Jerk FallingSlewLimit supports only negative or zero` | `cg_auto_defaults(true)` then run again |
| A different result after changing `T` | expected: the scene changes with `T` |

## 8. Limits (state them whenever you quote a number)
1. Simulation only. No hardware, no vehicle tests.
2. The AI is not in the loop. The detector is a surrogate with a fixed delay; the 12 s latency is a median from the Python evaluation, not a result of this model.
3. All timings are design values or values taken from the Python system.
4. Other cars follow scripts and do not react, including the follower behind. Rear-end contacts by that follower are a limit of the scene, not of the take-over logic.
5. The simulated driver does not brake for traffic: a conscious-driver run at 100 km/h can run into a slow car; that is not counted as a CabinGuard failure.
6. During the unresponsive phase (onset to take-over) the car holds its speed and has no AEB. With the GitHub timings that is about 22 s.
7. Authentication is a pass/fail flag; the cryptography (SecOC, 76-byte signed frame) is not simulated, only its effect.
8. A frame with a valid MAC and the next phase number is accepted early (the Python gateway behaves the same). If the Host dies before HAZARD, nothing is actuated.
9. Few scenes. The results are indications, not statistics.
