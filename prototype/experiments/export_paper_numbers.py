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
        # Seizure episodes: clinical seizure motion (SeizeIT2) when evaluated, recorded mimics,
        # and modelled jerk trains at every amplitude.
        ev = s["events"]
        rec = ev.get("Seizure@clinical", ev["Seizure@mimic"])
        mod = [ev[k] for k in ev if k.startswith("Seizure@") and k[8:9].isdigit()]
        sz = [rec] + mod
        sy = ev["Syncope"]
        macros[f"Sz{tag}"] = f"{rec['detected']}/{rec['n']}"
        macros[f"SzMim{tag}"] = f"{ev['Seizure@mimic']['detected']}/{ev['Seizure@mimic']['n']}"
        macros[f"SzMod{tag}"] = f"{sum(e['detected'] for e in mod)}/{sum(e['n'] for e in mod)}"
        macros[f"Sy{tag}"] = f"{sy['detected']}/{sy['n']}"
        macros[f"LatSz{tag}"] = fmt(rec["median_latency_s"], 1) if rec["median_latency_s"] is not None else "--"
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
    macros["PctSzFull"] = fmt(full["events"].get("Seizure@clinical", full["events"]["Seizure@mimic"])["p90_latency_s"], 1)
    for amp, tag in (("0.1", "Ten"), ("0.2", "Twenty"), ("0.5", "Fifty")):
        e = full["events"][f"Seizure@{amp}g"]
        macros[f"SzFull{tag}"] = f"{e['detected']}/{e['n']}"
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

    macros.update(motion_real())
    write_external()
    lines = ["% Generated by prototype/experiments/export_paper_numbers.py; do not edit by hand."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(macros.items())]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"{len(macros)} macros -> {OUT}")


def motion_real() -> dict[str, str]:
    """The deployed motion branch, trained on recorded motion (results/motion_real.json)."""
    r = json.loads((RES / "motion_real.json").read_text())
    m: dict[str, str] = {}
    cv = r.get("cross_validation", r)        # results saved before SeizeIT2 have no cross_validation key
    acc = cv["accelerometry"]
    m["MrDriveHours"] = fmt(acc["lh"]["driving"]["hours"], 1)
    m["MrDriveHip"] = str(acc["lh"]["driving"]["alarms"])
    m["MrDriveHipFA"] = fmt(acc["lh"]["driving"]["alarms_per_hour"], 1)
    m["MrDriveWrist"] = str(acc["lw"]["driving"]["alarms"])
    m["MrGaitMaxFA"] = fmt(max(v["alarms_per_hour"] for loc in acc.values() for a, v in loc.items()
                                if a != "driving"), 0)
    mh = cv["mhealth"]
    m["MrMhAlarms"] = str(sum(v["alarms"] for v in mh.values()))
    m["MrMhMin"] = fmt(sum(v["hours"] for v in mh.values()) * 60, 0)
    m["MrCyclingAlarms"] = str(mh["cycling"]["alarms"])
    epi = r["epilepsy_test"]
    others = [k for k in epi if k != "EPILEPSY"]
    m["MrEpiHit"] = str(epi["EPILEPSY"]["fired"])
    m["MrEpiN"] = str(epi["EPILEPSY"]["series"])
    m["MrEpiOther"] = str(sum(epi[k]["fired"] for k in others))
    m["MrEpiOtherN"] = str(sum(epi[k]["series"] for k in others))
    m["MrEpiAuc"] = fmt(r["epilepsy_test_auc_series"], 2)
    m["MrHarMax"] = fmt(100 * max(v["window_rate"] for v in r["har"].values()), 2)
    for amp, tag in (("0.05", "Five"), ("0.1", "Ten"), ("0.2", "Twenty"), ("0.5", "Fifty")):
        m[f"MrInj{tag}"] = fmt(cv["injected_clonic_lh"][amp]["sensitivity"], 2)
    if "seizeit2" in cv:
        m.update(_seizeit2(cv["seizeit2"], "MrSz"))
        alt = r["cross_validation_without_mhealth"]
        m.update(_seizeit2(alt["seizeit2"], "MrNoMhSz"))
        m["MrNoMhDriveHipFA"] = fmt(alt["accelerometry"]["lh"]["driving"]["alarms_per_hour"], 1)
        m["MrNoMhDriveWristFA"] = fmt(alt["accelerometry"]["lw"]["driving"]["alarms_per_hour"], 1)
        m["MrNoMhMhAlarms"] = str(sum(v["alarms"] for v in alt["mhealth"].values()))
        m["MrNoMhRunningAlarms"] = str(alt["mhealth"]["running"]["alarms"])
        m["MrNoMhCyclingAlarms"] = str(alt["mhealth"]["cycling"]["alarms"])
        m["MrDriveWristFA"] = fmt(acc["lw"]["driving"]["alarms_per_hour"], 1)
    return m


def _seizeit2(s: dict, prefix: str) -> dict[str, str]:
    """Per-type detection on held-out SeizeIT2 patients, and alarms per hour of patient background."""
    m = {}
    for group, tag in (("convulsive", "Conv"), ("hyperkinetic", "Hyper"), ("tonic or clonic", "Tonic"),
                       ("automatisms", "Auto"), ("non-motor", "NonMotor"), ("unclassified", "Unclass")):
        e = s[group]
        m[f"{prefix}{tag}"] = f"{e['detected']}/{e['seizures']}"
        m[f"{prefix}{tag}Lat"] = fmt(e["median_latency_s"], 0) if e["median_latency_s"] is not None else "--"
    m[f"{prefix}ConvPatients"] = str(s["convulsive"]["patients"])
    bg = s["background"]
    m[f"{prefix}BgFA"] = fmt(bg["alarms_per_hour"], 2)
    m[f"{prefix}BgHours"] = fmt(bg["hours"], 0)
    m[f"{prefix}BgPatients"] = str(bg["patients"])
    return m


def write_external() -> None:
    """Macros for the Colab-only checks, kept in their own file (paper_numbers_external.tex)."""
    path = RES / "external_checks.json"
    if not path.exists():
        return
    e = json.loads(path.read_text())
    m: dict[str, str] = {}
    epi = e["epilepsy"]
    others = [k for k in epi["transfer"] if k != "EPILEPSY"]
    m["EpiN"] = str(epi["transfer"]["EPILEPSY"]["series"])
    m["EpiTransferHit"] = str(epi["transfer"]["EPILEPSY"]["fired"])
    m["EpiTransferOther"] = str(sum(epi["transfer"][k]["fired"] for k in others))
    m["EpiOtherN"] = str(sum(epi["transfer"][k]["series"] for k in others))
    m["EpiWithinHit"] = str(epi["within_dataset"]["EPILEPSY"]["fired"])
    m["EpiWithinOther"] = str(sum(epi["within_dataset"][k]["fired"] for k in others))
    mh = e["mhealth"]["by_activity"]
    m["MhCyclingAlarms"] = str(mh["cycling"]["alarms"])
    m["MhCyclingMin"] = fmt(mh["cycling"]["hours"] * 60, 0)
    m["MhWalkingAlarms"] = str(mh["walking"]["alarms"])
    m["MhOtherAlarms"] = str(sum(v["alarms"] for k, v in mh.items() if k not in ("cycling", "walking")))
    har = e["har"]["by_activity"]
    m["HarMaxRate"] = fmt(100 * max(v["window_rate"] for v in har.values()), 1)
    lines = ["% Generated by prototype/experiments/export_paper_numbers.py from results/external_checks.json."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(m.items())]
    (ROOT.parent / "paper_numbers_external.tex").write_text("\n".join(lines) + "\n")
    print(f"{len(m)} external macros -> paper_numbers_external.tex")


if __name__ == "__main__":
    main()
