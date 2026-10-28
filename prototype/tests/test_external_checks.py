"""Loaders and checks of experiments/realdata/external_checks.py on fixture archives."""
import importlib.util
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "external_checks", Path(__file__).resolve().parents[1] / "experiments" / "realdata" / "external_checks.py")
ec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ec)


def _series(rng, label, n=206):
    t = np.arange(n) / 16.0
    if label == "EPILEPSY":
        x = 1.5 * np.sin(2 * np.pi * 3.5 * t)[:, None] * np.ones(3)
    elif label == "RUNNING":
        x = 0.8 * np.sin(2 * np.pi * 2.6 * t)[:, None] * np.ones(3)
    else:
        x = 0.3 * np.sin(2 * np.pi * 1.8 * t)[:, None] * np.ones(3)
    x = x + rng.normal(0, 0.05, (n, 3))
    return ":".join(",".join(f"{v:.4f}" for v in x[:, k]) for k in range(3)) + f":{label}"


def _ts(rng, n_each):
    lines = ["@problemName Epilepsy", "@dimensions 3", "@classLabel true EPILEPSY RUNNING SAWING WALKING", "@data"]
    for lab in ("EPILEPSY", "RUNNING", "SAWING", "WALKING"):
        lines += [_series(rng, lab) for _ in range(n_each)]
    return "\n".join(lines)


@pytest.fixture
def fixtures(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    ext = tmp_path / "external"
    ext.mkdir()
    with zipfile.ZipFile(ext / "Epilepsy.zip", "w") as z:
        z.writestr("Epilepsy/Epilepsy_TRAIN.ts", _ts(rng, 6))
        z.writestr("Epilepsy/Epilepsy_TEST.ts", _ts(rng, 4))
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        arr = np.zeros((1500, 24))
        arr[:, 0:3] = rng.normal(0, 1.0, (1500, 3)) + [0, 0, 9.8]
        arr[:750, 23], arr[750:, 23] = 10, 2
        buf = io.StringIO()
        np.savetxt(buf, arr)
        z.writestr("MHEALTHDATASET/mHealth_subject1.log", buf.getvalue())
    with zipfile.ZipFile(ext / "mhealth.zip", "w") as z:
        z.writestr("mhealth+dataset.zip", inner.getvalue())
    with zipfile.ZipFile(ext / "har.zip", "w") as z:
        for split in ("train", "test"):
            for a in "xyz":
                buf = io.StringIO()
                np.savetxt(buf, rng.normal(0, 0.1, (5, 128)))
                z.writestr(f"UCI HAR Dataset/{split}/Inertial Signals/total_acc_{a}_{split}.txt", buf.getvalue())
            z.writestr(f"UCI HAR Dataset/{split}/y_{split}.txt", "1\n4\n5\n6\n2\n")
            z.writestr(f"UCI HAR Dataset/{split}/subject_{split}.txt", "1\n1\n1\n1\n1\n")
    monkeypatch.setattr(ec, "DATA", tmp_path)
    return tmp_path


def test_parse_ts_shape(fixtures):
    parts = ec.load_epilepsy()
    X, y = parts["TRAIN"]
    assert X.shape == (24, 3, 206) and set(y) == {"EPILEPSY", "RUNNING", "SAWING", "WALKING"}


def test_resample_to_100hz():
    x = np.zeros((160, 3))
    assert ec.to_100hz(x, 16.0).shape == (1000, 3)
    assert ec.to_100hz(np.zeros((100, 3)), 50.0).shape == (200, 3)


def test_checks_run_end_to_end(fixtures):
    if not (Path(ec.ROOT) / "models" / "motion_branch_injected.joblib").exists():
        pytest.skip("motion branch not trained")
    e = ec.check_epilepsy()
    assert set(e["transfer"]) == {"EPILEPSY", "RUNNING", "SAWING", "WALKING"}
    assert e["within_dataset"]["EPILEPSY"]["rate"] >= e["within_dataset"]["WALKING"]["rate"]
    m = ec.check_mhealth()
    assert {"jogging", "sitting"} <= set(m["by_activity"])
    h = ec.check_har()
    assert h["by_activity"]["walking"]["windows"] == 2
