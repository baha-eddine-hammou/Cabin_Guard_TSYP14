"""Write every number the paper quotes as LaTeX macros (paper_numbers.tex).

The paper never types a result by hand: it uses these macros, so re-running
the experiments and this script updates the manuscript consistently.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = ROOT.parent / "paper_numbers.tex"


def fmt(x, nd=2):
    return f"{x:.{nd}f}"


def main() -> None:
    b = json.loads((RES / "branch_metrics.json").read_text())
    f = json.loads((RES / "fusion_metrics.json").read_text())
    m = json.loads((RES / "fault_matrix.json").read_text())
    macros: dict[str, str] = {}

    c = b["cardiac"]
    macros["NcardRecords"] = str(c["n_records"])
    macros["NcardNormal"] = f"{c['n_windows']['Normal']:,}".replace(",", "{,}")
    macros["NcardSeizure"] = str(c["n_windows"]["Seizure"])
    macros["NcardCardiac"] = f"{c['n_windows']['Cardiac']:,}".replace(",", "{,}")
    macros["DriveHours"] = fmt(c["drive_hours"], 1)
    for key, name in (("GaussianNB", "Nb"), ("LogReg", "Lr"), ("GBDT", "Gb")):
        e = c["models"][key]
        macros[f"Card{name}AucCardiac"] = fmt(e["auc_ovr"]["Cardiac"], 3)
        macros[f"Card{name}AucSeizure"] = fmt(e["auc_ovr"]["Seizure"], 3)
        macros[f"Card{name}RecNormal"] = fmt(e["recall"]["Normal"], 2)
        macros[f"Card{name}SzRecords"] = str(sum(e["per_record_seizure_hit"].values()))
    macros["SzRecords"] = str(len(c["models"]["LogReg"]["per_record_seizure_hit"]))

    L = b["motion"]["locations"]["lh"]
    macros["AccDriveHours"] = fmt(L["driving_hours"], 1)
    macros["BaseSerDriveFA"] = fmt(L["baseline_ser_rule"]["driving"], 1)
    macros["BaseSerWalkFA"] = fmt(L["baseline_ser_rule"]["walking"], 0)
    for amp, tag in (("0.02", "Two"), ("0.05", "Five"), ("0.1", "Ten"), ("0.2", "Twenty"), ("0.5", "Fifty")):
        macros[f"BaseSerSens{tag}"] = fmt(L["baseline_ser_rule_sensitivity"][amp], 2)
    for key, name in (("GaussianNB", "Nb"), ("LogReg", "Lr"), ("GBDT", "Gb")):
        e = L["models"][key]
        macros[f"Mot{name}Auc"] = fmt(e["auc_drive_vs_clonic"], 3)
        macros[f"Mot{name}DriveFA"] = fmt(e["false_alarms"]["driving"]["false_alarms_per_hour"], 1)
        macros[f"Mot{name}WalkFA"] = fmt(e["false_alarms"]["walking"]["false_alarms_per_hour"], 1)
        for amp, tag in (("0.02", "Two"), ("0.05", "Five"), ("0.1", "Ten"), ("0.2", "Twenty"), ("0.5", "Fifty")):
            macros[f"Mot{name}Sens{tag}"] = fmt(e["sensitivity_by_amplitude_g"][amp]["episode_sensitivity"], 2)
    macros["MotGbLatTwenty"] = fmt(L["models"]["GBDT"]["sensitivity_by_amplitude_g"]["0.2"]["median_latency_s"], 1)
    macros["MotEpisodes"] = str(L["models"]["GBDT"]["sensitivity_by_amplitude_g"]["0.2"]["episodes"])

    names = {
        "cardiac only (uncapped)": "OnlyCard", "motion only (uncapped)": "OnlyMot",
        "vision only (uncapped)": "OnlyVis", "posture only (uncapped)": "OnlyPos",
        "real branches: cardiac + motion": "Real", "full fusion": "Full",
        "camera lost (motion + posture)": "NoCam", "IMU lost (cardiac + vision + posture)": "NoImu",
    }
    macros["FusionHours"] = fmt(f["configs"]["full fusion"]["driving_hours"], 1)
    for cfg, tag in names.items():
        s = f["configs"][cfg]
        macros[f"Fa{tag}"] = fmt(s["false_mrm_per_hour"], 2)
        sz = [s["events"][k] for k in s["events"] if k.startswith("Seizure")]
        sy = s["events"]["Syncope"]
        macros[f"Sz{tag}"] = f"{sum(e['detected'] for e in sz)}/{sum(e['n'] for e in sz)}"
        macros[f"Sy{tag}"] = f"{sy['detected']}/{sy['n']}"
        lat_sz = [e["median_latency_s"] for e in sz if e["median_latency_s"] is not None]
        macros[f"LatSz{tag}"] = fmt(sorted(lat_sz)[len(lat_sz) // 2], 1) if lat_sz else "--"
        macros[f"LatSy{tag}"] = fmt(sy["median_latency_s"], 1) if sy["median_latency_s"] is not None else "--"
        macros[f"Wrong{tag}"] = str(sum(e["wrong_class"] for e in sz) + sy["wrong_class"])
    full = f["configs"]["full fusion"]
    macros["FullFalseCount"] = str(sum(full["false_by_class"].values()))
    # Rule-of-three style 95 % upper bound when no event is observed; otherwise
    # the exact Poisson upper bound would be needed, so only the zero case is exported.
    if sum(full["false_by_class"].values()) == 0:
        macros["FaFullUpper"] = fmt(3.0 / full["driving_hours"], 2)
    macros["NSyncopeEp"] = str(full["events"]["Syncope"]["n"])
    macros["PctSyFull"] = fmt(full["events"]["Syncope"]["p90_latency_s"], 1)
    macros["PctSzFull"] = fmt(max(full["events"][k]["p90_latency_s"] for k in full["events"] if k.startswith("Seizure")), 1)
    for w, tag in (("0", "Zero"), ("2", "Two"), ("4", "Four"), ("8", "Eight")):
        a = f["configs"][f"sweep: full fusion, smoothing {w} s"]
        r = f["configs"][f"sweep: real branches, smoothing {w} s"]
        macros[f"SweepFull{tag}"] = fmt(a["false_mrm_per_hour"], 2)
        macros[f"SweepReal{tag}"] = fmt(r["false_mrm_per_hour"], 2)
        macros[f"SweepLat{tag}"] = fmt(a["events"]["Syncope"]["median_latency_s"], 1)

    cases = m["cases"]
    macros["FaultCases"] = str(len(cases))
    macros["FaultSeeds"] = str(m["seeds"])
    macros["FaultPassed"] = str(sum(v["passed"] for v in cases.values()))
    macros["FaultRuns"] = str(sum(v["runs"] for v in cases.values()))
    macros["CycleMedian"] = fmt(m["cycle_compute_ms"]["median"], 1)
    macros["CycleP"] = fmt(m["cycle_compute_ms"]["p99"], 1)
    macros["CycleMax"] = fmt(m["cycle_compute_ms"]["max"], 0)

    lines = ["% Generated by prototype/experiments/export_paper_numbers.py; do not edit by hand."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(macros.items())]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"{len(macros)} macros -> {OUT}")


if __name__ == "__main__":
    main()
