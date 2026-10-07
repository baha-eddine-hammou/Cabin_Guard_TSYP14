"""
CabinGuard-ADI: Scientific Results Visualization
Generates publication-quality multi-panel figures using matplotlib.
Covers all 5 evaluation scenarios: feature timeseries, posteriors, vehicle dynamics, and MEC payload.
"""
import sys
import math
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for CI/server environments
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from pathlib import Path

from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
from cabinguard.feature_extraction import FeatureExtractor
from cabinguard.classifier import BayesianEtiologyClassifier
from cabinguard.watchdog import CrossSensorWatchdog
from cabinguard.safety_controller import VehicleSafetyController, MRMState
from cabinguard.telematics import TelematicsEngine

# ── Color palette ──────────────────────────────────────────────────────────────
C_NORMAL  = "#2ecc71"
C_SYNCOPE = "#e74c3c"
C_SEIZURE = "#e67e22"
C_DEGRADE = "#3498db"
C_MRM     = "#9b59b6"
C_BUS     = "#c0392b"

OUTPUT_DIR = Path(__file__).parent / "results"
OUTPUT_DIR.mkdir(exist_ok=True)


def _run_scenario(scenario: ScenarioType, duration_s: float = 30.0):
    """Run a full simulation and collect telemetry into lists for plotting."""
    sim = MultimodalSensorSimulator(scenario, duration_s=duration_s, seed=42)
    ext = FeatureExtractor()
    clf = BayesianEtiologyClassifier()
    wd  = CrossSensorWatchdog(clf)
    ctl = VehicleSafetyController(initial_speed_kmh=100.0)

    ts, ears, pitches, hrs, sers, psis = [], [], [], [], [], []
    p_norms, p_syncs, p_seizes = [], [], []
    confidences, entropies, persists = [], [], []
    speeds, accels, laterals = [], [], []
    modes, mrm_flags, spoof_flags = [], [], []

    for frame in sim:
        feat = ext.process_frame(frame)
        dec  = wd.evaluate(feat)
        dyn  = ctl.step(dec.mrm_trigger_flag, dec.active_class,
                        feat.steering_torque_nm, frame.brake_pedal_pressed,
                        override_suppressed=dec.override_suppressed)

        ts.append(frame.timestamp)
        ears.append(feat.ear)
        pitches.append(feat.pitch_deg)
        hrs.append(feat.rppg_hr_bpm)
        sers.append(feat.ser_2_6hz)
        psis.append(feat.psi)

        post = dec.raw_classification.posteriors
        p_norms.append(post["Normal"])
        p_syncs.append(post["Syncope"])
        p_seizes.append(post["Seizure"])
        confidences.append(dec.top_confidence)
        entropies.append(dec.shannon_entropy)
        persists.append(dec.persistence_seconds)

        speeds.append(dyn.speed_kmh)
        accels.append(dyn.longitudinal_accel_mss)
        laterals.append(dyn.lateral_pos_m)
        modes.append(dec.operational_mode)
        mrm_flags.append(dyn.mrm_state != MRMState.NORMAL)
        spoof_flags.append(dec.laser_spoofing_detected)

    return {
        "ts": np.array(ts), "ears": np.array(ears), "pitches": np.array(pitches),
        "hrs": np.array(hrs), "sers": np.array(sers), "psis": np.array(psis),
        "p_norms": np.array(p_norms), "p_syncs": np.array(p_syncs),
        "p_seizes": np.array(p_seizes), "confidences": np.array(confidences),
        "entropies": np.array(entropies), "persists": np.array(persists),
        "speeds": np.array(speeds), "accels": np.array(accels),
        "laterals": np.array(laterals), "modes": modes,
        "mrm_flags": mrm_flags, "spoof_flags": spoof_flags,
    }


def _shade_event(ax, ts, event_onset=4.0, color="salmon", label="Event Onset"):
    ax.axvspan(event_onset, ts[-1], alpha=0.08, color=color, label=label)
    ax.axvline(event_onset, color="red", lw=1.2, ls="--", alpha=0.7)


def _shade_mrm(ax, ts, mrm_flags):
    """Gray band wherever MRM is active."""
    in_mrm = False
    t_start = None
    for i, (t, f) in enumerate(zip(ts, mrm_flags)):
        if f and not in_mrm:
            t_start = t
            in_mrm = True
        if not f and in_mrm:
            ax.axvspan(t_start, t, alpha=0.12, color=C_MRM)
            in_mrm = False
    if in_mrm:
        ax.axvspan(t_start, ts[-1], alpha=0.12, color=C_MRM,
                   label="MRM Active")


# ── Figure 1 : Cardiac Syncope Full Pipeline ───────────────────────────────────
def plot_syncope_pipeline(data: dict, save_path: Path):
    ts = data["ts"]
    fig = plt.figure(figsize=(14, 11))
    gs  = GridSpec(5, 2, figure=fig, hspace=0.45, wspace=0.30)

    fig.suptitle(
        "CabinGuard-ADI · Cardiac Syncope Scenario — Full Detection Pipeline",
        fontsize=14, fontweight="bold", y=0.98
    )

    # ── Row 0 L : EAR + Head Pitch ─────────────────────────────────────────
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(ts, data["ears"], color=C_SYNCOPE, lw=1.5, label="EAR")
    ax.axhline(0.15, color="gray", lw=0.9, ls="--", label="Syncope threshold (0.15)")
    _shade_event(ax, ts)
    ax.set_ylabel("Eye Aspect Ratio", fontsize=9)
    ax.set_title("Eyelid Closure (EAR)", fontsize=10)
    ax.legend(fontsize=7)
    ax.set_ylim(0, 0.45)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(ts, data["pitches"], color=C_SYNCOPE, lw=1.5)
    ax2.axhline(-25, color="gray", lw=0.9, ls="--", label="Slump threshold")
    _shade_event(ax2, ts)
    ax2.set_ylabel("Pitch (degrees)", fontsize=9)
    ax2.set_title("Cranial Pitch Angle", fontsize=10)
    ax2.legend(fontsize=7)

    # ── Row 1 L : rPPG HR  ─────────────────────────────────────────────────
    ax = fig.add_subplot(gs[1, 0])
    ax.plot(ts, data["hrs"], color=C_SYNCOPE, lw=1.5, label="rPPG HR")
    ax.axhline(40, color="gray", lw=0.9, ls="--", label="Bradycardia (<40 BPM)")
    _shade_event(ax, ts)
    ax.set_ylabel("Heart Rate (BPM)", fontsize=9)
    ax.set_title("Optical rPPG Cardiac Rate", fontsize=10)
    ax.legend(fontsize=7)

    # ── Row 1 R : Postural Slump Index ─────────────────────────────────────
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(ts, data["psis"], color=C_SYNCOPE, lw=1.5, label="PSI")
    ax.axhline(0.75, color="gray", lw=0.9, ls="--", label="Slump threshold (0.75)")
    _shade_event(ax, ts)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("PSI", fontsize=9)
    ax.set_title("Postural Slump Index (Eq. 6)", fontsize=10)
    ax.legend(fontsize=7)

    # ── Row 2 : Bayesian Posteriors ─────────────────────────────────────────
    ax = fig.add_subplot(gs[2, :])
    ax.stackplot(ts, data["p_norms"], data["p_syncs"], data["p_seizes"],
                 labels=["P(Normal)", "P(Syncope)", "P(Seizure)"],
                 colors=[C_NORMAL, C_SYNCOPE, C_SEIZURE], alpha=0.75)
    ax.axhline(0.85, color="black", lw=1.0, ls=":", label="Confidence threshold Γ=0.85")
    _shade_event(ax, ts)
    _shade_mrm(ax, ts, data["mrm_flags"])
    ax.set_ylabel("Posterior Probability", fontsize=9)
    ax.set_title("Bayesian Multi-Etiology Posterior Probabilities (Eq. 7)", fontsize=10)
    ax.legend(fontsize=8, loc="lower left", ncol=4)
    ax.set_ylim(0, 1.05)

    # ── Row 3 L : Vehicle Speed ─────────────────────────────────────────────
    ax = fig.add_subplot(gs[3, 0])
    ax.plot(ts, data["speeds"], color=C_MRM, lw=2.0, label="Vehicle Speed")
    ax.fill_between(ts, 0, data["speeds"], alpha=0.15, color=C_MRM)
    ax.axhline(0, color="gray", lw=0.8, ls=":")
    ax.set_ylabel("Speed (km/h)", fontsize=9)
    ax.set_title("UNECE R157 Velocity Profile v(t)", fontsize=10)
    ax.legend(fontsize=7)
    ax.set_ylim(0, 110)

    # ── Row 3 R : Lateral Position ──────────────────────────────────────────
    ax = fig.add_subplot(gs[3, 1])
    ax.plot(ts, data["laterals"], color=C_MRM, lw=2.0)
    ax.axhline(-7.0, color="red", lw=0.9, ls="--", label="Target shoulder y = −7 m")
    ax.axhline(0.0,  color=C_NORMAL, lw=0.9, ls="--", label="Lane centre y = 0 m")
    ax.set_ylabel("Lateral Position y (m)", fontsize=9)
    ax.set_title("Lateral Shoulder Trajectory y(t)", fontsize=10)
    ax.legend(fontsize=7)
    ax.set_ylim(-8.5, 1.5)
    ax.invert_yaxis()

    # ── Row 4 : Uncertainty / Shannon Entropy ───────────────────────────────
    ax = fig.add_subplot(gs[4, :])
    ax.plot(ts, data["entropies"], color="steelblue", lw=1.5, label="Shannon Entropy H(X) [bits]")
    ax.fill_between(ts, 0, data["entropies"], alpha=0.15, color="steelblue")
    ax.plot(ts, data["persists"], color="darkorange", lw=1.5, ls="--",
            label="Persistence Timer t_persist [s]")
    ax.axhline(2.0, color="darkorange", lw=0.8, ls=":", alpha=0.7, label="T_ver = 2.0 s")
    ax.set_xlabel("Simulation Time (s)", fontsize=9)
    ax.set_ylabel("Bits / Seconds", fontsize=9)
    ax.set_title("Predictive Uncertainty (Shannon Entropy) & Verification Timer", fontsize=10)
    ax.legend(fontsize=8, ncol=3)

    for ax in fig.get_axes():
        ax.set_xlim(ts[0], ts[-1])
        ax.grid(True, alpha=0.3)

    fig.savefig(save_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved -> {save_path}")


# ── Figure 2 : Epileptic Seizure ────────────────────────────────────────────────
def plot_seizure_pipeline(data: dict, save_path: Path):
    ts = data["ts"]
    fig, axes = plt.subplots(4, 2, figsize=(13, 10))
    fig.suptitle(
        "CabinGuard-ADI · Epileptic Seizure Scenario — SER Spectral Energy & MRM",
        fontsize=13, fontweight="bold"
    )
    fig.subplots_adjust(hspace=0.42, wspace=0.30)

    axs = axes.flatten()

    # SER Spectral Energy Ratio
    axs[0].plot(ts, data["sers"], color=C_SEIZURE, lw=1.8, label="SER (2–6 Hz)")
    axs[0].axhline(0.65, color="gray", lw=0.9, ls="--", label="Seizure threshold (0.65)")
    axs[0].axhline(0.20, color="green", lw=0.9, ls=":", label="Normal ceiling (0.20)")
    _shade_event(axs[0], ts)
    axs[0].set_title("Seizure Spectral Energy Ratio SER(2–6 Hz)  (Eq. 5)", fontsize=9)
    axs[0].set_ylabel("SER", fontsize=8); axs[0].legend(fontsize=7)

    # Heart Rate (sympathetic tachycardia)
    axs[1].plot(ts, data["hrs"], color=C_SEIZURE, lw=1.8, label="rPPG HR")
    axs[1].axhline(100, color="gray", lw=0.9, ls="--", label="Tachycardia threshold")
    _shade_event(axs[1], ts)
    axs[1].set_title("Sympathetic Tachycardia via rPPG", fontsize=9)
    axs[1].set_ylabel("HR (BPM)", fontsize=8); axs[1].legend(fontsize=7)

    # EAR flutter
    axs[2].plot(ts, data["ears"], color=C_SEIZURE, lw=1.5, label="EAR (ictal flutter)")
    _shade_event(axs[2], ts)
    axs[2].set_title("Eyelid Flutter / Nystagmus (EAR)", fontsize=9)
    axs[2].set_ylabel("EAR", fontsize=8); axs[2].set_ylim(0, 0.45)

    # PSI — rhythmic torso rebound
    axs[3].plot(ts, data["psis"], color=C_SEIZURE, lw=1.5, label="PSI")
    _shade_event(axs[3], ts)
    axs[3].set_title("Postural Slump Index (Rhythmic Clonic Rebound)", fontsize=9)
    axs[3].set_ylabel("PSI", fontsize=8); axs[3].set_ylim(0, 1.05)

    # Bayesian posteriors (all 3 classes stacked consistently)
    axs[4].stackplot(ts, data["p_norms"], data["p_syncs"], data["p_seizes"],
                     labels=["P(Normal)", "P(Syncope)", "P(Seizure)"],
                     colors=[C_NORMAL, C_SYNCOPE, C_SEIZURE], alpha=0.75)
    axs[4].axhline(0.85, ls=":", lw=0.8, color="black", label="Γ = 0.85")
    _shade_event(axs[4], ts)
    _shade_mrm(axs[4], ts, data["mrm_flags"])
    axs[4].set_title("Bayesian Posterior Probabilities (Eq. 7)", fontsize=9)
    axs[4].set_ylabel("Probability", fontsize=8); axs[4].legend(fontsize=7, loc="lower left")
    axs[4].set_ylim(0, 1.05)

    # Confidence + Gamma threshold
    axs[5].plot(ts, data["confidences"], color="darkorange", lw=1.8, label="Top confidence")
    axs[5].axhline(0.85, ls="--", lw=0.9, color="black", label="Γ = 0.85")
    axs[5].fill_between(ts, 0, data["persists"] / 2.0, alpha=0.25, color="purple",
                        label="Persist progress (norm.)")
    _shade_event(axs[5], ts)
    axs[5].set_title("Confidence & Verification Window Progression", fontsize=9)
    axs[5].set_ylabel("Confidence / Progress", fontsize=8)
    axs[5].set_ylim(0, 1.05); axs[5].legend(fontsize=7)

    # Vehicle speed
    axs[6].plot(ts, data["speeds"], color=C_MRM, lw=2.0)
    axs[6].fill_between(ts, 0, data["speeds"], alpha=0.15, color=C_MRM)
    axs[6].set_title("MRM Velocity Profile v(t)", fontsize=9)
    axs[6].set_ylabel("Speed (km/h)", fontsize=8); axs[6].set_ylim(0, 110)

    # Lateral position
    axs[7].plot(ts, data["laterals"], color=C_MRM, lw=2.0)
    axs[7].axhline(-7.0, ls="--", lw=0.9, color="red", label="Shoulder target")
    axs[7].set_title("Lateral Shoulder Trajectory y(t)", fontsize=9)
    axs[7].set_ylabel("y (m)", fontsize=8); axs[7].set_ylim(-8.5, 1.5)
    axs[7].invert_yaxis(); axs[7].legend(fontsize=7)

    for ax in axs:
        ax.set_xlim(ts[0], ts[-1]); ax.grid(True, alpha=0.3)
        ax.set_xlabel("Time (s)", fontsize=8)

    fig.savefig(save_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved -> {save_path}")


# ── Figure 3 : Anti-Spoofing Interlock & Degraded Mode Scenarios ───────────────
def plot_fault_scenarios(data_attack: dict, data_fault: dict, save_path: Path):
    fig, axes = plt.subplots(2, 3, figsize=(15, 7))
    fig.suptitle(
        "CabinGuard-ADI · Fault Scenarios — Anti-Spoofing Interlock & Degraded Mode Fallback",
        fontsize=13, fontweight="bold"
    )
    fig.subplots_adjust(hspace=0.45, wspace=0.30)

    # ── Top Row : Optical Blinding Attack ──────────────────────────────────
    ts_a = data_attack["ts"]

    axes[0, 0].plot(ts_a, data_attack["hrs"], color="darkred", lw=1.8, label="Injected rPPG (spoofed)")
    axes[0, 0].axhline(1.0, color="gray", ls="--", lw=0.9)
    _shade_event(axes[0, 0], ts_a, color="red")
    axes[0, 0].set_title("Spoofed rPPG HR ← Laser Injection", fontsize=9)
    axes[0, 0].set_ylabel("Heart Rate (BPM)", fontsize=8)
    axes[0, 0].legend(fontsize=7)

    spoof_ts = [t for t, s in zip(ts_a, data_attack["spoof_flags"]) if s]
    axes[0, 1].scatter(spoof_ts, [1] * len(spoof_ts), color="red", s=22,
                       zorder=5, label=f"Spoofing Interlock Fires ({len(spoof_ts)}×)")
    axes[0, 1].plot(ts_a, data_attack["confidences"], color="orange", lw=1.5,
                    label="MRM Confidence (suppressed)")
    axes[0, 1].axhline(0.85, ls=":", color="black", lw=0.8, label="Γ = 0.85")
    _shade_event(axes[0, 1], ts_a, color="red")
    axes[0, 1].set_title("Algorithm 1 Interlock — MRM Suppressed", fontsize=9)
    axes[0, 1].set_ylabel("Confidence / Events", fontsize=8)
    axes[0, 1].set_ylim(0, 1.3)
    axes[0, 1].legend(fontsize=7)

    axes[0, 2].plot(ts_a, data_attack["speeds"], color=C_MRM, lw=2.0,
                    label="Speed (MRM NOT triggered)")
    axes[0, 2].set_ylim(0, 110)
    axes[0, 2].set_title("Vehicle Speed — No False MRM Activation", fontsize=9)
    axes[0, 2].set_ylabel("Speed (km/h)", fontsize=8)
    axes[0, 2].legend(fontsize=7)

    # ── Bottom Row : IMU Hardware Fault -> Degraded Mode 2 ─────────────────
    ts_f = data_fault["ts"]
    mode_colors = [C_DEGRADE if "Degraded" in m else C_NORMAL for m in data_fault["modes"]]

    axes[1, 0].scatter(ts_f, [1 if "Degraded" in m else 0 for m in data_fault["modes"]],
                       c=mode_colors, s=14, zorder=5)
    axes[1, 0].set_yticks([0, 1]); axes[1, 0].set_yticklabels(["Nominal", "Degraded"], fontsize=8)
    _shade_event(axes[1, 0], ts_f, color="steelblue", label="IMU Disconnect")
    axes[1, 0].set_title("Operational Mode: Nominal -> Degraded Mode 2", fontsize=9)
    axes[1, 0].set_ylabel("Mode", fontsize=8)

    axes[1, 1].plot(ts_f, data_fault["p_norms"], color=C_NORMAL, lw=1.5, label="P(Normal)")
    axes[1, 1].plot(ts_f, data_fault["p_syncs"], color=C_SYNCOPE, lw=1.5, label="P(Syncope)")
    axes[1, 1].plot(ts_f, data_fault["p_seizes"], color=C_SEIZURE, lw=1.5, label="P(Seizure)")
    _shade_event(axes[1, 1], ts_f, color="steelblue")
    axes[1, 1].set_title("Posteriors Under IMU Fault (rPPG+FSR+Grip Sufficient)", fontsize=9)
    axes[1, 1].set_ylabel("Probability", fontsize=8)
    axes[1, 1].set_ylim(0, 1.05); axes[1, 1].legend(fontsize=7)

    axes[1, 2].plot(ts_f, data_fault["entropies"], color="steelblue", lw=1.5,
                    label="Shannon Entropy H(X)")
    _shade_event(axes[1, 2], ts_f, color="steelblue")
    axes[1, 2].set_title("Classifier Uncertainty Under IMU Fault", fontsize=9)
    axes[1, 2].set_ylabel("Entropy (bits)", fontsize=8)
    axes[1, 2].legend(fontsize=7)

    for row in axes:
        for ax in row:
            ax.set_xlim(ts_a[0], ts_a[-1]); ax.grid(True, alpha=0.3)
            ax.set_xlabel("Time (s)", fontsize=8)

    fig.savefig(save_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved -> {save_path}")


# ── Figure 4 : All-Scenarios Benchmark Comparison ─────────────────────────────
def plot_benchmark_summary(all_data: dict, save_path: Path):
    colors = [C_NORMAL, C_SYNCOPE, C_SEIZURE, C_DEGRADE, C_DEGRADE]

    final_speeds   = [d["speeds"][-1]     for d in all_data.values()]
    peak_conf      = [d["confidences"].max() for d in all_data.values()]
    max_entropy    = [d["entropies"].max()  for d in all_data.values()]
    security_or_fault = [
        any(d["spoof_flags"]) or any(mode != "Nominal Mode" for mode in d["modes"])
        for d in all_data.values()
    ]

    fig, axes = plt.subplots(1, 4, figsize=(16, 5))
    fig.suptitle(
        "CabinGuard-ADI Phase 1 — Benchmark Validation Across All 5 Scenarios",
        fontsize=13, fontweight="bold"
    )

    short_labels = ["Normal", "Syncope", "Seizure", "Optical\nBlinding", "IMU\nFault"]
    x = np.arange(len(short_labels))

    def bar_plot(ax, values, ylabel, title, yline=None, yline_label=None):
        bars = ax.bar(x, values, color=colors, edgecolor="black", lw=0.7)
        ax.set_xticks(x); ax.set_xticklabels(short_labels, fontsize=8)
        ax.set_ylabel(ylabel, fontsize=9); ax.set_title(title, fontsize=9, fontweight="bold")
        if yline is not None:
            ax.axhline(yline, color="red", ls="--", lw=0.9, label=yline_label)
            ax.legend(fontsize=7)
        ax.grid(axis="y", alpha=0.3)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=7)

    bar_plot(axes[0], final_speeds, "Speed (km/h)", "Final Vehicle Speed\n(0 = Standstill)",
             yline=0, yline_label="Safe Stop")

    bar_plot(axes[1], peak_conf, "Peak Confidence", "Maximum Posterior Confidence",
             yline=0.85, yline_label="Γ = 0.85")

    bar_plot(axes[2], max_entropy, "Entropy (bits)", "Maximum Predictive Uncertainty")

    axes[3].bar(x, [1 if triggered else 0 for triggered in security_or_fault],
                color=colors, edgecolor="black", lw=0.7)
    axes[3].set_xticks(x); axes[3].set_xticklabels(short_labels, fontsize=8)
    axes[3].set_yticks([0, 1]); axes[3].set_yticklabels(["No", "Yes"], fontsize=9)
    axes[3].set_title("Security Interlock / Degraded\nMode Triggered", fontsize=9, fontweight="bold")
    axes[3].grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved -> {save_path}")


def main():
    print("\n" + "="*65)
    print("  CabinGuard-ADI — Generating Scientific Results Figures")
    print("="*65 + "\n")

    scenarios = {
        "Normal":     ScenarioType.NORMAL_DRIVING,
        "Syncope":    ScenarioType.CARDIAC_SYNCOPE,
        "Seizure":    ScenarioType.EPILEPTIC_SEIZURE,
        "Attack":     ScenarioType.OPTICAL_BLINDING_ATTACK,
        "IMU_Fault":  ScenarioType.IMU_HARDWARE_FAULT,
    }

    all_data = {}
    for name, sc in scenarios.items():
        print(f"  Running: {sc.value} ...")
        all_data[name] = _run_scenario(sc)
    print()

    plot_syncope_pipeline(all_data["Syncope"],
                          OUTPUT_DIR / "fig_syncope_full_pipeline.png")
    plot_seizure_pipeline(all_data["Seizure"],
                          OUTPUT_DIR / "fig_seizure_full_pipeline.png")
    plot_fault_scenarios(all_data["Attack"], all_data["IMU_Fault"],
                         OUTPUT_DIR / "fig_fault_scenarios.png")
    plot_benchmark_summary(all_data,
                           OUTPUT_DIR / "fig_benchmark_summary.png")

    print(f"\n  All figures saved to: {OUTPUT_DIR.resolve()}")
    print("="*65 + "\n")


if __name__ == "__main__":
    main()
