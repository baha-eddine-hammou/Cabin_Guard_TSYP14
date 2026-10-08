"""Training-set assembly of experiments/realdata/train_motion_real.py."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1] / "experiments" / "realdata"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("train_motion_real", HERE / "train_motion_real.py")
tmr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tmr)


def _sources(rng):
    acc = {"X": rng.normal(size=(40, 6)), "subject": np.repeat(["a", "b"], 20)}
    mh = {"X": rng.normal(size=(10, 6)), "subject": np.repeat(["m1", "m2"], 5)}
    epi = {"TRAIN": {"X": rng.normal(size=(8, 6)), "label": np.array(["EPILEPSY"] * 3 + ["WALKING"] * 5)}}
    # SeizeIT2: 6 motor ictal windows, 2 pre-ictal, 4 background, 3 non-motor ictal (never trained on)
    sz = {"X": rng.normal(size=(15, 6)),
          "group": np.array(["convulsive"] * 8 + ["background"] * 4 + ["non-motor"] * 3),
          "inside": np.array([True] * 6 + [False] * 2 + [False] * 4 + [True] * 3),
          "t_rel": np.array([5.0] * 6 + [-30.0] * 2 + [np.nan] * 4 + [5.0] * 3),
          "subject": np.array(["p1"] * 8 + ["p2"] * 4 + ["p1"] * 3)}
    return acc, mh, epi, sz


def test_classes_weigh_equally_and_sources_share():
    acc, mh, epi, sz = _sources(np.random.default_rng(0))
    X, y, w = tmr.training_set(acc, mh, epi, sz)
    assert (y == 1).sum() == 6 + 3 and (y == 0).sum() == 5 + 40 + 6 + 10
    assert np.isclose(w[y == 1].sum(), w[y == 0].sum())
    assert np.isclose(w[:6].sum(), w[6:9].sum())             # SeizeIT2 and mimic positives share equally


def test_non_motor_seizures_are_never_trained_on():
    acc, mh, epi, sz = _sources(np.random.default_rng(1))
    X, _, _ = tmr.training_set(acc, mh, epi, sz)
    assert not any(np.allclose(row, sz["X"][13]) for row in X)


def test_held_out_people_are_excluded():
    acc, mh, epi, sz = _sources(np.random.default_rng(2))
    X, y, _ = tmr.training_set(acc, None, epi, sz, keep={"acc:a", "sz:p2"})
    assert (y == 1).sum() == 3                               # only the mimics remain positive
    assert len(X) == 3 + 5 + 20 + 4


def test_seizure_groups():
    assert tmr.seizure_group("sz_foc_f2b") == "convulsive"
    assert tmr.seizure_group("sz_foc_ia_m_hyperkinetic") == "hyperkinetic"
    assert tmr.seizure_group("sz_uo_m_tonicMyio") == "tonic or myoclonic"
    assert tmr.seizure_group("sz_foc_ia_m_automatisms") == "automatisms"
    assert tmr.seizure_group("sz_foc_ia_nm") == "non-motor"


def test_alarm_runs_need_persistence():
    assert tmr.runs(np.array([1, 1, 1, 0, 1, 1, 1, 1, 1], bool), 4) == 1
    assert tmr.first_alarm(np.array([0, 1, 1, 1, 1], bool), 4) == 4
