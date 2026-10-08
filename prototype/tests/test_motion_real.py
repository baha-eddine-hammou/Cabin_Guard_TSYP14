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
    acc |= {"X_bl": acc["X"] + 0.1, "subject_bl": acc["subject"]}
    mh = {"X": rng.normal(size=(10, 6)), "X_bl": rng.normal(size=(10, 6)), "subject": np.repeat(["m1", "m2"], 5)}
    epi = {"TRAIN": {"X": rng.normal(size=(8, 6)), "label": np.array(["EPILEPSY"] * 3 + ["WALKING"] * 5)}}
    return acc, mh, epi


def test_classes_weigh_equally_and_sources_share_negatives():
    acc, mh, epi = _sources(np.random.default_rng(0))
    X, y, w = tmr.training_set(acc, mh, epi)
    assert len(X) == len(y) == len(w) == 3 + 5 + 40 + 40 + 10 + 10
    assert np.isclose(w[y == 1].sum(), w[y == 0].sum())
    # five negative sources, each with the same total weight
    assert np.isclose(w[3:8].sum(), w[8:48].sum()) and np.isclose(w[8:48].sum(), w[88:98].sum())


def test_held_out_subjects_are_excluded():
    acc, mh, epi = _sources(np.random.default_rng(1))
    X, y, _ = tmr.training_set(acc, mh, epi, acc_subjects={"a"}, mh_subjects={"m2"})
    assert len(X) == 3 + 5 + 20 + 20 + 5 + 5
    assert not any(np.allclose(row, acc["X"][25]) for row in X)


def test_alarm_runs_need_persistence():
    assert tmr.runs(np.array([1, 1, 1, 0, 1, 1, 1, 1, 1], bool), 4) == 1
