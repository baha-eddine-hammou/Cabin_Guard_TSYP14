# 3. Detection & AI Methodology

Every 100 ms the system assigns the driver to one of three classes (normal
driving, cardiac syncope, convulsive seizure) and decides whether to start the
minimum-risk manoeuvre. Section V of the paper gives the equations.

## Features

| Channel | Features | Code |
|---|---|---|
| Pulse rhythm (camera rPPG; ECG R-peaks in the training data) | rate from the median inter-beat interval, difference from the driver's running baseline, coefficient of variation, fraction of the 10 s window without a beat | `cabinguard/cardiac_features.py`, `cabinguard/vision.py` (POS rPPG) |
| Eyes and head (camera) | eye aspect ratio from six eyelid landmarks, head pitch | `cabinguard/vision.py`, `cabinguard/hardware.py` (MediaPipe FaceLandmarker) |
| Headrest motion (IMU) | 2–6 Hz spectral energy ratio from Welch spectra, band RMS, peak frequency, total RMS, rhythmicity, peakiness | `cabinguard/motion_features.py` |
| Seat and wheel | postural slump from seatback pressure, grip state (active, disengaged, clenched), steering torque | `cabinguard/feature_extraction.py` |

## Evidence branches

| Branch | Model | Trained on | Model file |
|---|---|---|---|
| Cardiac | multinomial logistic regression, class-balanced | PhysioNet: driving study (drivedb), partial-epilepsy seizures (szdb), ventricular arrhythmia (vfdb, cudb, mitdb); validated leaving one record out | `models/cardiac_branch.joblib` |
| Motion | gradient-boosted trees with histogram splits (scikit-learn), class- and source-balanced | recorded motion only: SeizeIT2 clinical motor seizures (neck accelerometer), UEA Epilepsy seizure mimics, against patient background, PhysioNet walk-climb-drive and UCI MHEALTH; people held out in five folds; UCI HAR never trained on | `models/motion_branch.joblib` |
| Vision | expert-set Gaussian class densities on eye opening and head pitch | none: no public recording of incapacitated drivers | `cabinguard/fusion.py` |
| Posture | expert-set densities on slump and grip | none, as above | `cabinguard/fusion.py` |

`models/face_landmarker.task` is Google's pretrained MediaPipe face model; it
is not trained here. The other `.joblib` files in `models/` are comparison
models from earlier experiments and are not used by the detector.

## Bounded-evidence fusion and decision

- Each branch's posterior becomes a log-likelihood ratio against normal driving
  by dividing out its training prior.
- Each branch's evidence for an event is bounded to c = 3, so one branch can
  never reach the decision threshold Γ = 0.85 on its own and two agreeing
  branches can (the bound follows from Γ and the prior; it holds for
  1.91 < c < 3.81).
- Branches are combined with the product rule, averaged over W = 2 s; W was
  chosen out of fold (every fold chose 2 s).
- The manoeuvre starts when one event class stays above Γ for 2 s and at least
  two physical sensors agree. The camera feeds two branches but counts as one
  sensor, so a blinded lens cannot decide alone.
- Losing a sensor removes its branches (degraded modes 1 and 2); with fewer
  than two sensors no manoeuvre may start (degraded mode 3). A camera that
  contradicts an upright, steering driver is distrusted for 10 s.

Code: `cabinguard/fusion.py` (branches and fusion), `cabinguard/watchdog.py`
(decision rule, degraded modes, spoofing interlock), `cabinguard/config.py`
(thresholds), all under
[`6_Proof_of_Concept_Prototype/prototype`](../6_Proof_of_Concept_Prototype/prototype).

Training scripts: `experiments/realdata/train_branches.py` (cardiac) and
`experiments/realdata/train_motion_real.py` (motion); results and how to
reproduce them are in [`5_Validation_Benchmarking`](../5_Validation_Benchmarking).
