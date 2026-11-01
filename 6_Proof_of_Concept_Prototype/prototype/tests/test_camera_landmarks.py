"""FaceLandmarker port: landmarks and face measures on a real photograph (skips without mediapipe)."""
import numpy as np
import pytest


def test_face_measures_on_a_real_face():
    pytest.importorskip("mediapipe")
    cv2 = pytest.importorskip("cv2")
    data = pytest.importorskip("skimage.data")
    from cabinguard.hardware import FACE_MODEL, FaceLandmarks, face_measures
    if not FACE_MODEL.exists():
        pytest.skip("face_landmarker.task not present")
    rgb = data.astronaut()
    lm = FaceLandmarks(video=False)
    try:
        p = lm(rgb)
    finally:
        lm.close()
    assert p is not None and p.shape == (478, 3)
    m = face_measures(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), p)
    assert 0.2 < m["ear"] < 0.45                  # eyes open
    assert abs(m["pitch"]) < 30 and m["snr"] == 10.0
    assert np.all(np.isfinite(m["rgb"]))
