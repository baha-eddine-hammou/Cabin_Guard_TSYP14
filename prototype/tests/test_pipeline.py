"""Detection, fusion rules, features and fault handling through the full pipeline."""
import numpy as np
import pytest

from cabinguard.cardiac_features import CardiacFeatures, window_features
from cabinguard.fusion import CLASSES, FusionClassifier, FusionInput
from cabinguard.motion_features import EMPTY, clonic_waveform, motion_features
from cabinguard.pipeline import run_scenario
from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
from cabinguard.vision import eye_aspect_ratio, pos_pulse, pulse_peaks

T = ScenarioType


@pytest.fixture(scope="module")
def clf():
    c = FusionClassifier()
    if c.cardiac is None or c.motion is None:
        pytest.skip("branch models not trained")
    return c


def test_cardiac_features_regular_and_absent_pulse():
    beats = np.arange(0, 30, 60 / 75)
    f = window_features(beats, 20.0, 75.0)
    assert f.hr_bpm == pytest.approx(75, abs=0.5) and f.pulse_absent < 0.05 and abs(f.hr_delta) < 1
    g = window_features(beats[beats < 12], 20.0, 75.0)
    assert g.pulse_absent > 0.6


def test_motion_features_separate_clonic_from_noise():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.03, (200, 3))
    jerks = clonic_waveform(2.0, 100.0, 0.3, 0.08, 0.05, rng) + noise
    a, b = motion_features(noise, 100.0), motion_features(jerks, 100.0)
    assert b.ser > a.ser and b.rhythmicity > a.rhythmicity and b.band_rms_g > 5 * a.band_rms_g


def test_single_branch_cannot_reach_gamma(clf):
    # Even a saturated branch alone must stay below the decision threshold.
    x = FusionInput(cardiac=CardiacFeatures(0, 0, 0, 1.0))
    r = clf.classify(x)
    assert r.top_confidence < 0.85 or r.predicted_class == "Normal"
    x = FusionInput(ear=0.05, pitch_deg=-35)
    assert not (clf.classify(x).is_confident and clf.classify(x).predicted_class != "Normal")


def test_two_sensors_reach_gamma_and_keep_class_contrast(clf):
    x = FusionInput(cardiac=CardiacFeatures(0, 0, 0, 1.0), motion=EMPTY, ear=0.06, pitch_deg=-30,
                    psi=0.8, grip="DISENGAGED")
    r = clf.classify(x)
    assert r.predicted_class == "Syncope" and r.is_confident
    assert r.corroborating_sensors() >= {"camera", "seat"}
    # Saturated evidence must still prefer the right event class.
    assert r.posteriors["Syncope"] > 5 * r.posteriors["Seizure"]


def test_camera_branches_count_as_one_sensor(clf):
    x = FusionInput(cardiac=CardiacFeatures(0, 0, 0, 1.0), ear=0.05, pitch_deg=-30)
    assert clf.classify(x).corroborating_sensors() == {"camera"}


@pytest.mark.parametrize("scenario,expected", [
    (T.NORMAL_DRIVING, "Normal"), (T.CARDIAC_SYNCOPE, "Syncope"), (T.EPILEPTIC_SEIZURE, "Seizure"),
    (T.OPTICAL_BLINDING_ATTACK, "Normal"), (T.IMU_HARDWARE_FAULT, "Normal"), (T.SEAT_SENSOR_STALE, "Normal"),
])
def test_scenarios_end_to_end(clf, scenario, expected):
    r = run_scenario(MultimodalSensorSimulator(scenario, 60, 3), classifier=clf)
    assert r.triggered_class == expected
    if expected != "Normal":
        assert r.records[-1].mrm_state == "PHASE_4_STANDSTILL"
        assert len(r.vehicle.received_mec) == 1 and r.vehicle.received_mec[0].etiology == expected
        assert r.vehicle.denm_sent and r.vehicle.denm_sent[0][4] == 93


def test_blinding_attack_is_logged(clf):
    r = run_scenario(MultimodalSensorSimulator(T.OPTICAL_BLINDING_ATTACK, 30, 1), classifier=clf)
    assert r.ecu.watchdog.security_log and any("camera lost" in x.mode for x in r.records)


def test_processing_failure(clf):
    r = run_scenario(MultimodalSensorSimulator(T.NORMAL_DRIVING, 20, 1), classifier=clf, ecu_hang_at=8.0)
    g = r.vehicle.gateway.state
    assert g.ecu_fault and not g.fail_operational and r.records[-1].speed_kmh > 99
    r = run_scenario(MultimodalSensorSimulator(T.CARDIAC_SYNCOPE, 70, 1), classifier=clf, ecu_hang_at=34.0)
    assert r.vehicle.gateway.state.fail_operational and r.records[-1].speed_kmh == 0


@pytest.mark.parametrize("attack", ["tamper", "replay", "forge", "implausible"])
def test_can_attacks_never_move_the_vehicle(clf, attack):
    r = run_scenario(MultimodalSensorSimulator(T.NORMAL_DRIVING, 15, 1), classifier=clf, attack=attack)
    assert r.records[-1].speed_kmh > 99
    gw = r.vehicle.gateway
    assert gw.rx.secoc.rejected["mac"] + gw.rejected_implausible >= r.attack_frames


def test_communication_failure_falls_back(clf):
    r = run_scenario(MultimodalSensorSimulator(T.CARDIAC_SYNCOPE, 70, 1), classifier=clf,
                     bearer_outage=(0.0, 1e9, False))
    assert len(r.vehicle.received_mec) == 1
    assert any(b == "sms" and ok for _, b, ok in r.vehicle.notifier.log)


def test_pos_rppg_recovers_pulse_rate():
    fs, hr = 30.0, 72.0
    t = np.arange(0, 12, 1 / fs)
    rng = np.random.default_rng(1)
    pulse = 0.5 * np.sin(2 * np.pi * hr / 60 * t)
    rgb = np.stack([100 + 0.3 * pulse, 80 + 1.0 * pulse, 60 + 0.5 * pulse], 1) + rng.normal(0, 0.05, (t.size, 3))
    peaks = pulse_peaks(pos_pulse(rgb, fs), fs)
    est = 60 / np.median(np.diff(t[peaks]))
    assert est == pytest.approx(hr, abs=3)


def test_eye_aspect_ratio():
    open_eye = np.array([[0, 0], [1, 1], [2, 1], [3, 0], [2, -1], [1, -1]], float)
    closed = open_eye * [1, 0.1]
    assert eye_aspect_ratio(open_eye) == pytest.approx(2 / 3)
    assert eye_aspect_ratio(closed) < 0.1


def test_class_order():
    assert CLASSES == ("Normal", "Syncope", "Seizure")


def test_rppg_tracker_follows_a_drifting_frame_rate():
    """72 bpm with the webcam dropping from 30 to 15 fps: one beat per pulse, no duplicates."""
    from cabinguard.vision import RPPGTracker
    rng = np.random.default_rng(0)
    pbv = np.array([0.33, 0.77, 0.53])                # blood-volume pulse colour signature (R, G, B)
    tr, t, beats = RPPGTracker(30.0), 0.0, []
    while t < 16.0:
        tr.push(t, np.array([150.0, 110.0, 90.0]) * (1 + 0.01 * pbv * np.sin(2 * np.pi * 1.2 * t))
                + rng.normal(0, 0.15, 3))
        beats += tr.new_beats()[0]
        t += 1 / (30.0 if t < 8.0 else 15.0)
    ibi = np.diff(beats)
    assert len(beats) >= 10 and ibi.min() >= 0.33
    assert abs(60 / np.median(ibi) - 72) < 4
    slow = RPPGTracker(6.0)
    for i in range(60):
        slow.push(i / 6.0, np.array([150.0, 110.0, 90.0]))
    assert slow.new_beats()[0] == []                  # below 7 Hz the pulse band cannot be resolved
