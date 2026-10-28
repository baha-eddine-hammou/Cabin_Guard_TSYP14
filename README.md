# CabinGuard-ADI

In-cabin detection of acute driver incapacitation (cardiac syncope and
convulsive seizure versus normal driving), connected to an authenticated
minimum-risk manoeuvre and a privacy-preserving emergency call. Submission for
the IEEE VTS TSYP14 CabinGuard-ADI challenge.

```
camera (eyes, head, rPPG) ─┐                                       ┌─▶ gateway ─▶ brakes, hazards, EPB
headrest IMU ──────────────┼─▶ features ─▶ fusion ─▶ watchdog ─▶ MRM ─┤   (SecOC CAN, plausibility, alive timeout)
seat FSR, wheel grip ──────┘   (per sensor)  (bounded)  (modes,      └─▶ eCall: signed, encrypted 76-byte MEC
                                              evidence)  spoofing)        DENM without the etiology
```

## What is evidence and what is not

| Claim | Evidence | Where |
|---|---|---|
| Pulse-rhythm branch separates VT/VF and ictal tachycardia from normal rhythm | 130 PhysioNet records (drivedb, szdb, vfdb, cudb, mitdb), leave-one-record-out | `prototype/results/branch_metrics.json` |
| Motion branch detects convulsive seizure motion | Trained on recorded motion only: SeizeIT2 clinical motor seizures (neck accelerometer, OpenNeuro ds005873) and UEA Epilepsy mimics against SeizeIT2 background, PhysioNet walk-climb-drive and UCI MHEALTH; patients and subjects held out in five folds, UCI HAR never trained on. Alone it raises alarms during real driving; the two-sensor fusion absorbs them. Modelled clonic jerks (Conradsen et al. 2013) are a test only | `prototype/results/motion_real.json`, `motion_labelling_iterations.json` |
| Fused detector: false MRM starts per hour, sensitivity, latency | Composite episodes: real cardiac and motion branches, modelled eye/head/seat channels, out-of-fold models, 22 h of real driving | `prototype/results/fusion_metrics.json` |
| Fault and attack handling | Full software pipeline with synthetic sensors, 14 cases x 10 seeds | `prototype/results/fault_matrix.json` |

Not claimed: clinical validation, measured seizure motion at a vehicle seat
(no public dataset has it), real camera rPPG in a moving vehicle, certified
ISO 26262 / UNECE R157 compliance, an HSM, or a deployed eCall/V2X link. The
eye, head and seat channels use expert-set likelihoods until Phase 2 data
exists. See `hardware/README.md` for the Phase 2 bench and validation plan.

## Layout

```
prototype/
  cabinguard/            package: features, fusion, watchdog, MRM controller,
                         SecOC CAN, gateway, eCall/MEC, simulator, hardware front ends
  experiments/realdata/  PhysioNet extraction, branch training, fused evaluation
  experiments/fault_matrix.py   failure and attack scenarios
  experiments/colab/     auxiliary dataset scripts (MHEALTH, UCI HAR, PhysDrive, MIT-BIH)
  models/                trained branch models (cardiac_branch, motion_branch; motion_branch_injected is the baseline)
  results/               every number quoted in the paper
  tests/                 pytest suite
  run_demo.py            scenarios through the full pipeline
  run_realtime.py        10 Hz real-time ECU loop (simulated or hardware sensors, CAN)
  run_gateway.py         actuator-side gateway for the CAN bench
  run_jury_demo.py       jury dashboard (cabinguard/demo: engine, runner, web server, static page)
  cabinguard_mrm.dbc     CAN database, bit-exact with cabinguard/can_messages.py
hardware/                ESP32 sensor-node firmware, BOM, wiring, Phase 2 plan
tools/check_manuscript.py   manuscript style checker (rules in CLAUDE.md)
IEEE_Research_Paper_CabinGuard.tex   the paper
```

## Quick start

Python 3.11 or newer.

```
pip install -e "prototype[dev]"
cd prototype
python -m pytest -q                 # 47 tests: features, fusion rules, pipeline, faults, CAN, crypto
python run_demo.py                  # all scenarios
python run_demo.py --scenario seizure
python run_demo.py --scenario normal --attack forge
python run_realtime.py --scenario syncope --can virtual
python experiments/fault_matrix.py --seeds 10
```

## Jury demo

A local dashboard that runs the same ECU, gateway, SecOC, eCall and DENM code
at 10 Hz on wall clock, with every input switchable between the scenario
simulator and live hardware. It needs no GPU and no internet, and binds to
127.0.0.1 only.

```
pip install -e "prototype[demo]"                    # add ,hardware for the webcam and the ESP32
cd prototype
python run_jury_demo.py                             # all synthetic; opens http://127.0.0.1:8765
python run_jury_demo.py --camera 0                  # live face channel from the laptop webcam
python run_jury_demo.py --camera 1 --serial COM5    # USB webcam and the ESP32 sensor node
python run_jury_demo.py --record                    # also writes every cycle to data/demo_sessions/*.jsonl
```

Keys in the browser: P plays the scripted run (forged frame at 6 s, seizure
at 14 s, stop on the hard shoulder about 45 s after play), S seizure, Y
syncope, F/R/T/I CAN attacks (forge, replay, tamper, compromised ECU),
B/U/H/C faults (blinded camera, IMU unplugged, ECU hang, cellular down), Esc
reset, L light or dark theme.

Every input carries a chip the engine computes: SYNTHETIC (simulator signals,
which exercise the software and are not detection performance), LIVE (a device
now) or INJECTED (an operator fault or attack). The vehicle is a point mass
with a kinematic lateral model on an in-process bus, and the bearers and the
emergency centre are simulated; the dashboard says so on each panel. The
recorded session file holds the derived signals and decisions, never camera
frames.

## Reproduce the real-data results

The datasets are downloaded from PhysioNet (official site, or its AWS open
data mirror when the site is unreachable), OpenNeuro (SeizeIT2, ds005873, CC0),
timeseriesclassification.com (UEA Epilepsy) and the UCI repository (MHEALTH,
HAR) into `data/`, which git ignores.

```
cd prototype
python -m cabinguard.physionet_fetch drivedb szdb vfdb cudb mitdb accelerometry-walk-climb-drive
python experiments/realdata/extract_cardiac.py      # ~2 min
python experiments/realdata/extract_motion.py       # ~2 min
python experiments/realdata/extract_motion.py --branch        # ~2 min; windows as the motion branch sees them
python experiments/realdata/extract_seizeit2.py               # ~30 min; SeizeIT2 seizure minutes (OpenNeuro)
python experiments/realdata/train_branches.py       # ~7 min; cardiac branch, injected-jerk motion baseline
python experiments/realdata/train_motion_real.py    # ~2 min; downloads UEA Epilepsy, MHEALTH, HAR (~140 MB)
                                                    # writes models/motion_branch.joblib, results/motion_real.json
python experiments/realdata/external_checks.py      # optional: injected-jerk baseline on the same data
python experiments/realdata/evaluate_fusion.py      # ~3 min; writes results/fusion_metrics.json
python experiments/fault_matrix.py --seeds 10       # ~4 min
python experiments/export_paper_numbers.py          # refresh ../paper_numbers.tex for the paper
```

## Run the training on Google Colab

Open `prototype/experiments/colab/CabinGuard_Colab.ipynb` in Colab
(File > Upload notebook, or open it from GitHub). It clones this branch,
downloads every dataset, reruns all experiments, adds the checks that need open
internet (UEA Epilepsy seizure mimics, UCI MHEALTH and HAR, optionally
PhysDrive from Kaggle), and downloads a zip with the new `models/`,
`results/` and `paper_numbers.tex`. The older scripts in
`experiments/colab/` (`colab_uci_real_datasets.py`, `colab_mitbih_replay.py`)
train activity and beat classifiers that the detector does not use; they are
kept for reference only.

## Datasets

All open access on PhysioNet (Goldberger et al., Circulation 2000):
Stress Recognition in Automobile Drivers (drivedb), Post-Ictal Heart Rate
Oscillations in Partial Epilepsy (szdb), MIT-BIH Malignant Ventricular
Ectopy (vfdb), CU Ventricular Tachyarrhythmia (cudb), MIT-BIH Arrhythmia
(mitdb), and Labeled raw accelerometry data captured during walking, stair
climbing and driving. Each keeps its own licence; none is redistributed here.

Downloaded only in Colab: UEA Epilepsy (timeseriesclassification.com),
UCI MHEALTH (dataset 319) and UCI HAR (dataset 240), both CC BY 4.0, and
PhysDrive (Kaggle `xiaoyang274/physdrive`, subject to its release agreement).
