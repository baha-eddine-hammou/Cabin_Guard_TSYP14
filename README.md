# CabinGuard-ADI submission package

CabinGuard-ADI is a Phase 1 research prototype for multimodal detection of synthetic driver incapacitation scenarios and a modeled minimum-risk response.

## Scope and evidence

The current evidence is software-only. Sensor streams are synthetic, the vehicle response is modeled in Python, and the CAN/MEC messages are prototype formats. The project does not claim clinical validation, real camera or IMU capture, CARLA/ROS2 validation, real wireless eCall or DENM transmission, production HSM/ECDSA, AUTOSAR SecOC, or certified ASIL compliance.

## Environment

Use Python 3.12 or newer. Install the dependencies listed in `prototype/requirements.txt` in the selected environment.

## Run the demonstration

From the `prototype` directory, run `python run_demo.py`. The demo exercises normal driving, syncope, seizure, optical blinding, and IMU-fault scenarios through the simulator, feature extractor, watchdog, safety controller, and prototype telematics layer.

## Run regression tests

Run `python test_cabinguard.py` from `prototype`. The suite covers configuration, RFC 4493 CMAC vectors, synthetic classification, degraded modes, spoof suppression, prototype CAN integrity, replay rejection, unauthorized-key rejection, and class separation.

## Reproduce the benchmark

Run `python evaluate_50_trials.py` from `prototype`. It uses ten deterministic seeds for each of five synthetic scenarios and writes `results/benchmark_50_trials.csv` and `results/benchmark_metrics.json`. Use `--seeds N` to change the number of seeds. The output includes a confusion matrix, per-class precision/recall/F1, latency statistics, false-positive and false-negative counts, safe-failure counts, MEC lengths, and prototype CAN verification results.

## Replay PhysDrive data

PhysDrive is an external academic dataset. The official repository is at
`https://github.com/WJULYW/PhysDrive-Dataset`; its preprocessed version is also
listed at `https://www.kaggle.com/datasets/xiaoyang274/physdrive`. Download the
dataset separately and pass its root directory to `PhysDriveAdapter`:

```python
from cabinguard.physdrive_adapter import PhysDriveAdapter

adapter = PhysDriveAdapter(r"D:\\datasets\\PhysDrive")
for frame in adapter.iter_frames():
	# Pass frame to FeatureExtractor, CrossSensorWatchdog, and the controller.
	print(frame.timestamp, frame.rppg_hr_bpm, frame.imu_heartbeat_ok)
```

The adapter searches recursively for `Recording_Physiological_Data.csv` and
replays its timestamp and heart-rate columns. It also discovers `HR.mat`-only
sessions, as found in some PhysDrive Kaggle releases. PhysDrive does not contain CabinGuard seatback FSR, steering
grip, or headrest IMU channels, so those fields are explicitly unavailable or
neutral. This adapter validates real PhysDrive heart-rate replay through the
adapter, feature extractor, and degraded-mode watchdog. Because the missing
modalities are imputed, degraded classifier outputs are diagnostic only and
do not establish seizure or syncope classification performance.

## Real-dataset adapters

The first multi-dataset milestone adds provenance-aware windows through
`cabinguard.dataset_types`:

- `MHealthAdapter` reads UCI MHEALTH 50 Hz logs with chest ECG, inertial
	channels, activity labels, and subject identity.
- `UciHarAdapter` reads UCI HAR inertial windows, activity labels, and
	subject-disjoint metadata.
- `PhysDriveAdapter` reads PhysDrive CSV or `HR.mat` physiological sessions.
- `MitBihAdapter` reads MIT-BIH ECG records and preserves WFDB beat annotations.

Official sources:

- UCI MHEALTH: `https://archive.ics.uci.edu/dataset/319/mhealth+dataset`
- UCI HAR: `https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones`
- PhysDrive: `https://github.com/WJULYW/PhysDrive-Dataset`
- MIT-BIH Arrhythmia: `https://physionet.org/content/mitdb/1.0.0/`

For Colab, upload `prototype.zip` and run `colab_uci_real_datasets.py`. The
runner downloads the official MHEALTH and UCI HAR archives, parses them with
the adapters, and writes `uci_real_dataset_report.json`. Its metrics are
dataset-native ingestion/activity statistics, not medical-event performance.

These datasets validate inertial, ECG, activity, and provenance handling. They
do not provide driver syncope or seizure labels and must not be scored as the
current `Normal`/`Syncope`/`Seizure` medical classifier.

For MIT-BIH, install the optional `wfdb` dependency and run
`colab_mitbih_replay.py` in Colab. The runner streams records `100` and `101`
from PhysioNet, reports ECG windows and beat-annotation symbols, and writes
`mitbih_real_pipeline_report.json`. MIT-BIH results validate ECG and
arrhythmia preprocessing only; arrhythmia is not syncope.

## Submission limitations

The benchmark is not a clinical study and should not be interpreted as sensitivity, specificity, or regulatory evidence. Thresholds are literature-informed engineering assumptions. The target architecture still requires real-sensor validation, approved vehicle or simulator integration, security-key provisioning, production message security, privacy/legal review, and safety-case development.
