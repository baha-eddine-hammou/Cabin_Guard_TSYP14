"""Reproducible synthetic benchmark for the CabinGuard prototype.

This evaluates five deterministic scenarios across configurable seeds.  It is
not a clinical or vehicle certification benchmark: all sensor streams are
synthetic and the safety response is software-only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from cabinguard.classifier import BayesianEtiologyClassifier
from cabinguard.feature_extraction import FeatureExtractor
from cabinguard.safety_controller import VehicleSafetyController, MRMState
from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
from cabinguard.telematics import TelematicsEngine
from cabinguard.watchdog import CrossSensorWatchdog


SCENARIOS = {
	ScenarioType.NORMAL_DRIVING: "Normal",
	ScenarioType.CARDIAC_SYNCOPE: "Syncope",
	ScenarioType.EPILEPTIC_SEIZURE: "Seizure",
	ScenarioType.OPTICAL_BLINDING_ATTACK: "Normal",
	ScenarioType.IMU_HARDWARE_FAULT: "Normal",
}
EVENT_ONSET_S = 4.0


def _safe_div(numerator: float, denominator: float) -> float:
	return numerator / denominator if denominator else 0.0


def _classification_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
	labels = ["Normal", "Syncope", "Seizure"]
	matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
	for row in rows:
		actual = str(row["expected_class"])
		predicted = str(row["predicted_class"])
		matrix[actual][predicted] += 1

	per_class: dict[str, dict[str, float]] = {}
	for label in labels:
		tp = matrix[label][label]
		fp = sum(matrix[other][label] for other in labels if other != label)
		fn = sum(matrix[label][other] for other in labels if other != label)
		precision = _safe_div(tp, tp + fp)
		recall = _safe_div(tp, tp + fn)
		f1 = _safe_div(2 * precision * recall, precision + recall)
		per_class[label] = {
			"precision": round(precision, 4),
			"recall": round(recall, 4),
			"f1": round(f1, 4),
			"support": tp + fn,
		}

	total = sum(sum(row.values()) for row in matrix.values())
	correct = sum(matrix[label][label] for label in labels)
	return {
		"labels": labels,
		"confusion_matrix": matrix,
		"per_class": per_class,
		"accuracy": round(_safe_div(correct, total), 4),
		"macro_f1": round(
			sum(values["f1"] for values in per_class.values()) / len(labels), 4
		),
	}


def run_trial(scenario: ScenarioType, seed: int) -> dict[str, object]:
	expected = SCENARIOS[scenario]
	simulator = MultimodalSensorSimulator(scenario, duration_s=32.0, seed=seed)
	extractor = FeatureExtractor()
	watchdog = CrossSensorWatchdog(BayesianEtiologyClassifier())
	controller = VehicleSafetyController(initial_speed_kmh=100.0)
	telematics = TelematicsEngine()

	predictions: list[str] = []
	first_trigger_s: float | None = None
	final_state = MRMState.NORMAL
	final_lateral = 0.0
	final_mec_length = 0
	final_frame_valid = False

	for frame in simulator:
		features = extractor.process_frame(frame)
		decision = watchdog.evaluate(features)
		dynamics = controller.step(
			mrm_trigger=decision.mrm_trigger_flag,
			etiology=decision.active_class,
			steering_torque=features.steering_torque_nm,
			brake_pressed=frame.brake_pedal_pressed,
		)
		final_state = dynamics.mrm_state
		final_lateral = dynamics.lateral_pos_m
		if frame.timestamp >= EVENT_ONSET_S:
			predictions.append(decision.active_class)
		if first_trigger_s is None and decision.mrm_trigger_flag:
			first_trigger_s = frame.timestamp
			mec = telematics.generate_76byte_mec(
				decision.active_class, decision.top_confidence,
				int(decision.persistence_seconds * 1000),
			)
			final_mec_length = len(mec.raw_76_bytes)
			command = telematics.generate_can_fd_mrm_frame(
				dynamics.longitudinal_accel_mss, dynamics.hazard_flashers_active, 3
			)
			final_frame_valid = telematics.verify_can_fd_mrm_frame(command)

	predicted = Counter(predictions).most_common(1)[0][0] if predictions else "Normal"
	safe_attack = scenario in {
		ScenarioType.NORMAL_DRIVING,
		ScenarioType.OPTICAL_BLINDING_ATTACK,
		ScenarioType.IMU_HARDWARE_FAULT,
	}
	return {
		"scenario": scenario.name,
		"seed": seed,
		"expected_class": expected,
		"predicted_class": predicted,
		"mrm_triggered": first_trigger_s is not None,
		"detection_latency_s": (
			round(first_trigger_s - EVENT_ONSET_S, 3)
			if first_trigger_s is not None else None
		),
		"safe_no_mrm_expected": safe_attack,
		"safe_no_mrm_observed": safe_attack and first_trigger_s is None,
		"standstill_reached": final_state == MRMState.PHASE_4_STANDSTILL,
		"final_lateral_position_m": round(final_lateral, 3),
		"mec_length_bytes": final_mec_length,
		"prototype_can_verification": final_frame_valid,
	}


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--seeds", type=int, default=10,
						help="number of seeds per scenario (default: 10)")
	parser.add_argument("--output-dir", type=Path, default=Path("results"))
	args = parser.parse_args()

	rows = [
		run_trial(scenario, seed)
		for seed in range(args.seeds)
		for scenario in SCENARIOS
	]
	args.output_dir.mkdir(parents=True, exist_ok=True)

	with (args.output_dir / "benchmark_50_trials.csv").open("w", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
		writer.writeheader()
		writer.writerows(rows)

	classification_rows = [
		row for row in rows
		if row["scenario"] in {
			ScenarioType.NORMAL_DRIVING.name,
			ScenarioType.CARDIAC_SYNCOPE.name,
			ScenarioType.EPILEPTIC_SEIZURE.name,
		}
	]
	latencies = [
		row["detection_latency_s"] for row in rows
		if row["detection_latency_s"] is not None
	]
	safe_rows = [row for row in rows if row["safe_no_mrm_expected"]]
	metrics = {
		"benchmark_scope": "synthetic software simulation; not clinical or vehicle certification evidence",
		"total_trials": len(rows),
		"seeds_per_scenario": args.seeds,
		"scenarios": [scenario.name for scenario in SCENARIOS],
		"classification": _classification_metrics(classification_rows),
		"detection_latency_s": {
			"count": len(latencies),
			"mean": round(sum(latencies) / len(latencies), 4) if latencies else None,
			"min": min(latencies) if latencies else None,
			"max": max(latencies) if latencies else None,
		},
		"false_positive_count": sum(
			row["predicted_class"] != "Normal"
			for row in rows if row["expected_class"] == "Normal"
		),
		"false_negative_count": sum(
			row["predicted_class"] == "Normal"
			for row in rows if row["expected_class"] != "Normal"
		),
		"safe_scenario_count": len(safe_rows),
		"mec_length_bytes": sorted({row["mec_length_bytes"] for row in rows}),
		"mec_scope_note": "76 bytes generated exclusively upon verified medical crisis (syncope/seizure); suppressed (0 bytes) during normal driving and non-emergency fault modes",
		"prototype_can_valid_count": sum(row["prototype_can_verification"] for row in rows),
	}
	(args.output_dir / "benchmark_metrics.json").write_text(
		json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
	)
	print(json.dumps(metrics, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())
