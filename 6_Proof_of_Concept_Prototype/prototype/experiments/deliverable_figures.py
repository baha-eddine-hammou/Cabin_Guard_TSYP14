"""Figures for the deliverable folders 3, 4 and 5, drawn from committed results and the paper's equations.

Nothing here trains or evaluates: the validation charts read the JSON files in
``results/``, the detection charts evaluate the fusion bound and the modelled
clonic jerk train, and the security charts read the CAN database file.

    python experiments/deliverable_figures.py

writes PNG files into ``3_Detection_AI_Methodology/figures``,
``4_Security_Threat_Model/figures`` and ``5_Validation_Benchmarking/figures``.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cabinguard import config  # noqa: E402
from cabinguard.fusion import BRANCH_CAP  # noqa: E402
from cabinguard.motion_features import clonic_waveform  # noqa: E402
from cabinguard.paths import REPO  # noqa: E402

RES = ROOT / "results"
# Class colours as in the dashboard (validated categorical slots 1-3); ink for all text.
NORMAL, SYNCOPE, SEIZURE = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#74736d", "#e3e2dd", "#fcfcfb"
GOOD = "#0ca30c"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": INK, "legend.frameon": False,
})


def save(fig, folder: str, name: str) -> None:
    out = REPO / folder / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out / name)


def note(fig, text: str, y: float = -0.02) -> None:
    fig.text(0.01, y, text, ha="left", va="top", fontsize=8.5, color=MUTED, wrap=True)


# ------------------------------------------------------------------ validation ---
def fused_detector() -> None:
    f = json.loads((RES / "fusion_metrics.json").read_text())["configs"]
    rows = [("Pulse only", "cardiac only (uncapped)"), ("Motion only", "motion only (uncapped)"),
            ("Eyes, head only", "vision only (uncapped)"), ("Seat, wheel only", "posture only (uncapped)"),
            ("Pulse + motion", "real branches: cardiac + motion"), ("All four", "full fusion"),
            ("Camera lost", "camera lost (motion + posture)"), ("IMU lost", "IMU lost (cardiac + vision + posture)")]
    labels = [r[0] for r in rows]
    y = np.arange(len(rows))[::-1]
    fa = [f[k]["false_mrm_per_hour"] for _, k in rows]
    sy = [f[k]["events"]["Syncope"] for _, k in rows]
    sz = [f[k]["events"]["Seizure@clinical"] for _, k in rows]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True, gridspec_kw={"wspace": 0.12})
    panels = [(axes[0], fa, None, NORMAL, "False manoeuvres per hour\nof real driving (22.2 h)", None),
              (axes[1], [e["detected"] / e["n"] for e in sy], sy, SYNCOPE, "Syncope episodes detected", 1.0),
              (axes[2], [e["detected"] / e["n"] for e in sz], sz, SEIZURE, "Clinical-motion seizures detected", 1.0)]
    for ax, vals, ev, colour, title, xmax in panels:
        ax.barh(y, vals, height=0.62, color=colour, edgecolor=SURFACE, linewidth=2)
        ax.set_title(title, loc="left", fontsize=10)
        ax.grid(axis="y", visible=False)
        top = xmax or max(vals) * 1.25
        ax.set_xlim(0, top * 1.18)
        for yi, v, i in zip(y, vals, range(len(vals))):
            txt = f"{v:.2f}" if ev is None else f"{ev[i]['detected']}/{ev[i]['n']}"
            ax.text(v + top * 0.02, yi, txt, va="center", fontsize=9, color=INK)
        if xmax:
            ax.set_xticks([0, 0.5, 1.0], ["0", "50 %", "100 %"])
    axes[0].set_yticks(y, labels, color=INK)
    for ax in axes:
        ax.axhspan(y[5] - 0.45, y[5] + 0.45, color="#f0efec", zorder=0)
    fig.suptitle("Fused detector on out-of-fold composite episodes", x=0.01, ha="left", fontweight="bold", color=INK, y=1.04)
    note(fig, "Public datasets for the pulse and motion branches (PhysioNet, SeizeIT2); eye, head and seat channels are modelled, "
              "so rows that use them are optimistic. 'Only' rows are uncapped single branches. Source: results/fusion_metrics.json.")
    save(fig, "5_Validation_Benchmarking", "fused_detector.png")


def w_sweep() -> None:
    f = json.loads((RES / "fusion_metrics.json").read_text())
    ws = [0, 2, 4, 8]
    cfg = [f["configs"][f"sweep: full fusion, smoothing {w} s"] for w in ws]
    chosen = sorted(set(f["w_selection"]["chosen_by_fold_s"].values()))
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw={"wspace": 0.3})
    lat_sy = [c["events"]["Syncope"]["median_latency_s"] for c in cfg]
    lat_sz = [c["events"]["Seizure@clinical"]["median_latency_s"] for c in cfg]
    ax = axes[0]
    ax.plot(ws, lat_sy, color=SYNCOPE, lw=2, marker="o", ms=7, label="syncope")
    ax.plot(ws, lat_sz, color=SEIZURE, lw=2, ls="--", marker="s", ms=7, label="clinical-motion seizure")
    for w, a, b in zip(ws, lat_sy, lat_sz):
        ax.text(w, a - 1.6, f"{a:g}", ha="center", va="top", fontsize=8.5, color=INK)
        ax.text(w, b + 0.9, f"{b:g}", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_ylim(0, 32)
    ax.set_title("Median detection latency, s", loc="left", fontsize=10)
    ax.legend(loc="lower right", fontsize=8.5)
    ax = axes[1]
    det = [c["events"]["Syncope"]["detected"] for c in cfg]
    n = cfg[0]["events"]["Syncope"]["n"]
    ax.plot(ws, det, color=SYNCOPE, lw=0, marker="o", ms=9)          # dots: the axis does not start at zero
    for w, d in zip(ws, det):
        ax.text(w, d + 0.4, f"{d}/{n}", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_ylim(70, 82)
    ax.set_title("Syncope episodes detected", loc="left", fontsize=10)
    for a in axes:
        a.set_xticks(ws)
        a.set_xlabel("smoothing window W, s")
        for c in chosen:
            a.axvline(c, color=INK2, lw=1, ls=":", zorder=0)
    axes[1].text(chosen[0] + 0.25, 81.2, f"chosen in every fold: W = {chosen[0]:g} s", fontsize=8.5, color=INK2)
    note(fig, "Full fusion, composite episodes (public datasets plus modelled eye, head and seat channels). W chosen per fold on the "
              "other folds. The syncope axis starts at 70 to show the differences. Source: results/fusion_metrics.json.", y=-0.1)
    save(fig, "5_Validation_Benchmarking", "w_sweep.png")


def motion_by_type() -> None:
    m = json.loads((RES / "motion_real.json").read_text())["cross_validation"]["seizeit2"]
    order = ["convulsive", "tonic or clonic", "unclassified", "hyperkinetic", "automatisms", "non-motor"]
    rows = [(k, m[k]) for k in order if k in m]
    y = np.arange(len(rows))[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    sens = [v["detected"] / v["seizures"] for _, v in rows]
    ax.barh(y, sens, height=0.6, color=[SEIZURE if k == "convulsive" else "#9fdcc6" for k, _ in rows],
            edgecolor=SURFACE, linewidth=2)
    for yi, (k, v), s in zip(y, rows, sens):
        ax.text(s + 0.015, yi, f"{v['detected']}/{v['seizures']}  ({v['patients']} patients)", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [k for k, _ in rows], color=INK)
    ax.set_xlim(0, 1.15)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "25 %", "50 %", "75 %", "100 %"])
    ax.grid(axis="y", visible=False)
    ax.set_title("Motion branch: seizures detected by type, held-out patients", loc="left", fontsize=10)
    note(fig, "Public dataset: SeizeIT2 (OpenNeuro ds005873), neck accelerometer, patients held out in five folds. "
              "The branch targets convulsive motion; other types barely move a neck sensor. Source: results/motion_real.json.")
    save(fig, "5_Validation_Benchmarking", "motion_by_seizure_type.png")


def fault_matrix() -> None:
    fm = json.loads((RES / "fault_matrix.json").read_text())
    cases = list(fm["cases"].items())
    fig, ax = plt.subplots(figsize=(9, 0.36 * len(cases) + 0.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, len(cases) + 0.2)
    ax.axis("off")
    for i, (name, c) in enumerate(cases):
        yy = len(cases) - 1 - i
        if i % 2 == 0:
            ax.add_patch(Rectangle((0, yy - 0.5), 10, 1, color="#f0efec", lw=0))
        ok = c["passed"] == c["runs"]
        ax.text(0.1, yy, name, va="center", fontsize=9, color=INK)
        ax.text(4.55, yy, c["expected"], va="center", fontsize=9, color=INK2)
        ax.text(9.0, yy, ("✓ " if ok else "✗ ") + f"{c['passed']}/{c['runs']}", va="center", fontsize=9,
                color=INK, fontweight="bold")
        ax.add_patch(Rectangle((8.75, yy - 0.18), 0.12, 0.36, color=GOOD if ok else "#d03b3b", lw=0))
    ax.text(0.1, len(cases) - 0.15, "Case", fontsize=9, color=MUTED, va="bottom")
    ax.text(4.55, len(cases) - 0.15, "Required outcome", fontsize=9, color=MUTED, va="bottom")
    ax.text(9.0, len(cases) - 0.15, "Passed", fontsize=9, color=MUTED, va="bottom")
    ax.set_title(f"Fault and attack matrix: {sum(c['passed'] for _, c in cases)} of "
                 f"{sum(c['runs'] for _, c in cases)} runs reached the required outcome", loc="left", fontsize=10, pad=4)
    note(fig, f"Synthetic sensors through the full software pipeline, {fm['seeds']} seeds per case. "
              "Source: results/fault_matrix.json (experiments/fault_matrix.py).")
    fig.subplots_adjust(top=0.93, bottom=0.04)
    save(fig, "5_Validation_Benchmarking", "fault_matrix.png")


# ------------------------------------------------------------------- detection ---
def fusion_bound() -> None:
    gamma = config.CONFIDENCE_THRESHOLD_GAMMA
    l0 = math.log(0.1 / 0.8)
    target = math.log(gamma / (1 - gamma))
    c = np.linspace(0, 5, 400)
    post = lambda lo: 1 / (1 + np.exp(-lo))  # noqa: E731
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    lo_c, hi_c = (target - l0) / 2, target - l0
    ax.axvspan(lo_c, hi_c, color="#e8f3ee", zorder=0)
    ax.plot(c, post(l0 + c), color=SYNCOPE, lw=2, ls="--", label="one branch at its bound")
    ax.plot(c, post(l0 + 2 * c), color=NORMAL, lw=2, label="two agreeing branches at the bound")
    ax.axhline(gamma, color=INK, lw=1)
    ax.text(0.05, gamma + 0.015, f"decision threshold Γ = {gamma}", fontsize=9, color=INK)
    ax.axvline(BRANCH_CAP, color=INK2, lw=1, ls=":")
    ax.text(BRANCH_CAP + 0.05, 0.52, f"c = {BRANCH_CAP:g}\n(used)", fontsize=9, color=INK2)
    ax.text(2.45, 0.28, f"admissible bound\n{lo_c:.2f} < c < {hi_c:.2f}", ha="center", va="center",
            fontsize=8.5, color=INK2)
    ax.text(4.95, post(l0 + 4.95) - 0.03, "one branch", ha="right", va="top", fontsize=9, color=INK)
    ax.text(0.12, 0.66, "two branches", ha="left", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("evidence bound c per branch (log-likelihood ratio)")
    ax.set_ylabel("posterior of the event")
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("Why one sensor cannot start a manoeuvre", loc="left", fontsize=10)
    note(fig, "From the fusion rule with prior 0.1 per event and 0.8 for normal driving: at c = 3 one branch at its bound stays below "
              "Γ and two agreeing branches exceed it. Computed from the equations, not data.")
    save(fig, "3_Detection_AI_Methodology", "fusion_bound.png")


def clonic_train() -> None:
    fs, dur, sp0 = 100.0, 20.0, 0.10
    rng = np.random.default_rng(7)
    acc = clonic_waveform(dur, fs, 0.2, sp0, math.log(1 / sp0) / 40, rng)
    t = np.arange(len(acc)) / fs
    mag = np.linalg.norm(acc, axis=1)
    fig, ax = plt.subplots(figsize=(9, 2.6))
    ax.plot(t, mag, color=SEIZURE, lw=1.2)
    ax.set_xlim(0, dur)
    ax.set_xlabel("time from clonic onset, s")
    ax.set_ylabel("|acceleration|, g")
    ax.set_title("Modelled clonic jerk train used to test seizure detection", loc="left", fontsize=10)
    ax.annotate("0.2 s discharges", xy=(0.6, mag[:100].max()), xytext=(2.0, 0.27), fontsize=8.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.annotate("silent periods grow towards 1 s", xy=(14.25, 0.01), xytext=(11.5, 0.27), fontsize=8.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.set_ylim(0, 0.32)
    note(fig, "Synthetic: the clonic dynamics of Conradsen et al. (2013), 0.2 s discharges with exponentially growing silent periods, "
              "at 0.2 g; added to held-out real driving for testing only, never for training.", y=-0.12)
    save(fig, "3_Detection_AI_Methodology", "clonic_jerk_train.png")


# -------------------------------------------------------------------- security ---
SHORT = {"MRM_Phase": "phase", "MRM_Active": "active", "HazardFlashers_Req": "hazards", "EPB_Clamp_Req": "EPB",
         "Doors_Unlock_Req": "doors", "Decel_Request": "braking request", "Detected_Etiology": "etiology",
         "Degraded_Level": "degraded", "Spoof_Interlock": "spoof", "eCall_Req": "eCall", "DENM_Req": "DENM",
         "Confidence": "confidence", "Shoulder_Req": "shoulder", "SecOC_FV": "freshness", "SecOC_MAC": "MAC"}


def frame_layout() -> None:
    import cantools
    db = cantools.database.load_file(ROOT / "cabinguard_mrm.dbc")
    msg = db.get_message_by_frame_id(0x120)
    group = {"SecOC_FV": ("freshness value", "#eda100"), "SecOC_MAC": ("24-bit MAC (AES-128-CMAC)", "#e34948")}
    fig, ax = plt.subplots(figsize=(11, 2.7))
    ax.set_xlim(-0.2, 64.2)
    ax.set_ylim(-1.5, 1.6)
    ax.axis("off")
    for s in sorted(msg.signals, key=lambda s: s.start):
        label, colour = group.get(s.name, ("command", "#2a78d6"))
        ax.add_patch(Rectangle((s.start, 0), s.length, 1, facecolor=colour, edgecolor=SURFACE, lw=2,
                               alpha=1.0 if s.name in group else 0.18 + 0.1 * (s.start % 2)))
        name = SHORT.get(s.name, s.name)
        fs_ = 8 if s.length >= 4 else 7
        rot = 0 if s.length >= 6 else 90
        ax.text(s.start + s.length / 2, 0.5, name, ha="center", va="center", fontsize=fs_, rotation=rot,
                color="white" if s.name in group else INK)
    for byte in range(9):
        ax.plot([byte * 8] * 2, [-0.15, 1.15], color=INK2, lw=1)
        if byte < 8:
            ax.text(byte * 8 + 4, 1.3, f"byte {byte}", ha="center", fontsize=8.5, color=MUTED)
    ax.annotate("", xy=(0, -0.45), xytext=(32, -0.45), arrowprops=dict(arrowstyle="<->", color=INK2, lw=1))
    ax.text(16, -0.75, "payload (32 bits): the minimum-risk manoeuvre command", ha="center", va="top", fontsize=8.5, color=INK)
    ax.annotate("", xy=(32, -0.45), xytext=(64, -0.45), arrowprops=dict(arrowstyle="<->", color=INK2, lw=1))
    ax.text(48, -0.75, "SecOC profile 1: 8 low bits of a 64-bit freshness value,\n24-bit CMAC over data ID, payload, full freshness",
            ha="center", va="top", fontsize=8.5, color=INK)
    ax.set_title("CAN frame 0x120 MRM_Cmd (8 bytes, every 100 ms), read from cabinguard_mrm.dbc", loc="left", fontsize=10)
    save(fig, "4_Security_Threat_Model", "frame_0x120.png")


def trust_boundaries() -> None:
    fig, ax = plt.subplots(figsize=(12.5, 5.4))
    ax.set_xlim(0, 26.5)
    ax.set_ylim(0, 10.6)
    ax.axis("off")
    H = 1.7

    def box(x, y, w, text, ec=MUTED):
        ax.add_patch(FancyBboxPatch((x, y), w, H, boxstyle="round,pad=0.02,rounding_size=0.25", fc="#ffffff", ec=ec, lw=1.4))
        ax.text(x + w / 2, y + H / 2, text, ha="center", va="center", fontsize=9, color=INK, linespacing=1.3)

    def arrow(x1, y1, x2, y2, label=None, lx=None):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, color=INK2, lw=1.4))
        if label:                                   # labels sit inside one zone, never across a border
            ax.text(lx if lx is not None else (x1 + x2) / 2, max(y1, y2) + 0.15, label, ha="center", va="bottom",
                    fontsize=8, color=INK2)

    def zone(x, w, y, h, title, colour, fc):
        ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=colour, lw=1.2, ls="--"))
        ax.text(x + 0.2, y + h - 0.45, title, fontsize=9, color=colour, fontweight="bold")

    zone(0.2, 10.1, 0.3, 9.9, "Vehicle cabin and edge host", NORMAL, "#f3f7fd")
    zone(10.7, 6.2, 0.3, 9.9, "Untrusted channels", "#c0392b", "#fdf1ec")
    zone(17.3, 9.0, 5.8, 4.4, "Trusted boundary: actuators", "#13805a", "#eef8f3")
    top, mid, low = 7.2, 4.0, 0.9
    yc = lambda y: y + H / 2  # noqa: E731
    lab = 11.6                                       # centre of the untrusted zone's left margin

    box(0.6, top, 3.6, "Sensors\ncamera, IMU,\nseat and wheel")
    box(5.8, top, 4.0, "Edge host\ndetection, MRM;\nholds the CAN key")
    arrow(4.2, yc(top), 5.8, yc(top), "CRC only")
    box(12.7, top, 3.8, "CAN bus\nattacker: forge,\nreplay, tamper")
    arrow(9.8, yc(top), 12.7, yc(top), "0x120 + MAC", lx=lab)
    box(17.8, top, 3.7, "Gateway\nMAC, freshness,\nplausibility, alive", ec=SEIZURE)
    arrow(16.5, yc(top), 17.8, yc(top))
    box(22.2, top, 3.8, "Actuators\nbrakes, hazards,\nshoulder, EPB")
    arrow(21.5, yc(top), 22.2, yc(top))

    box(5.8, mid, 4.0, "Telematics\nsigns: ECDSA P-256\nencrypts: ECIES")
    arrow(7.8, top, 7.8, mid + H)
    box(12.7, mid, 3.8, "Cellular / SMS\nattacker: read,\ndrop, inject")
    arrow(9.8, yc(mid), 12.7, yc(mid), "sealed MEC", lx=lab)
    box(17.8, mid, 3.7, "Emergency centre\ndecrypts, verifies;\nonly etiology reader")
    arrow(16.5, yc(mid), 17.8, yc(mid))

    box(12.7, low, 3.8, "V2X radio, public\nDENM cause 93,\nsub-cause 0")
    ax.plot([7.8, 7.8], [mid, yc(low)], color=INK2, lw=1.4)
    arrow(7.8, yc(low), 12.7, yc(low), "DENM", lx=lab)
    box(17.8, low, 3.7, "Nearby vehicles\n'human problem',\nno diagnosis")
    arrow(16.5, yc(low), 17.8, yc(low))

    ax.text(0.6, 5.2, "Out of scope (residual risk):\n\u2022 physical access to\n   the sensor link\n"
                      "\u2022 a compromised host\n   that holds the key", fontsize=8.5, color=INK2, va="top", linespacing=1.35)
    ax.set_title("Trust boundaries and what crosses them", loc="left", fontsize=10)
    save(fig, "4_Security_Threat_Model", "trust_boundaries.png")


if __name__ == "__main__":
    fused_detector()
    w_sweep()
    motion_by_type()
    fault_matrix()
    fusion_bound()
    clonic_train()
    frame_layout()
    trust_boundaries()
