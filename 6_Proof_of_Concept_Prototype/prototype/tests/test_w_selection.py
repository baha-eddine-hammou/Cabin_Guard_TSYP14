"""Nested choice of the smoothing window W in evaluate_fusion: no episode chooses its own W."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "realdata"))
import evaluate_fusion as ef  # noqa: E402


def _syncope(fold, hit):
    return (fold, "Syncope", 180, 60, [(64, "Syncope")] if hit else [])


def test_tally_counts_detections_false_alarms_and_latency():
    outs = [(0, "Normal", 7200, None, [(10, "Seizure")]), _syncope(0, True), _syncope(1, False),
            (1, "Seizure@0.2g", 300, 240, [(100, "Seizure"), (250, "Syncope")])]
    t = ef.tally(outs)
    assert t["false_mrm_per_hour"] == 1.0 and t["false_by_class"] == {"Seizure": 1}
    assert t["events"]["Syncope"]["sensitivity"] == 0.5 and t["events"]["Syncope"]["median_latency_s"] == 2.0
    sz = t["events"]["Seizure@0.2g"]
    assert sz["pre_onset_false"] == 1 and sz["wrong_class"] == 1 and sz["detected"] == 0


def test_each_fold_is_scored_with_the_w_chosen_on_the_other_folds():
    # W = 2 detects every syncope in folds 0-2 but none in fold 3; W = 4 detects only in fold 3.
    per_w = {0.0: [_syncope(f, False) for f in range(4)],
             2.0: [_syncope(f, f != 3) for f in range(4)],
             4.0: [_syncope(f, f == 3) for f in range(4)]}
    sel = ef.select_w_out_of_fold(per_w)
    assert sel["chosen_by_fold_s"] == {"0": 2.0, "1": 2.0, "2": 2.0, "3": 2.0}
    assert sel["held_out"]["events"]["Syncope"]["sensitivity"] == 0.75       # fold 3 pays for its own miss


def test_ties_go_to_the_shortest_window():
    per_w = {w: [_syncope(f, True) for f in range(3)] for w in (8.0, 0.0, 2.0)}
    assert set(ef.select_w_out_of_fold(per_w)["chosen_by_fold_s"].values()) == {0.0}
