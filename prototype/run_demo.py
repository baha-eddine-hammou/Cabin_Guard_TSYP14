"""
CabinGuard-ADI: Interactive PoC Prototype & Simulation Suite Runner
Demonstrates real-time multimodal detection, Watchdog Algorithm 1 interlocks,
UNECE R157 MRM vehicle dynamics, and CAN-FD SecOC / 76-byte MEC telematics.
"""
import sys
import time
import argparse
from typing import Optional

# Import rich components for high-impact terminal visualization
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, BarColumn, TextColumn
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from cabinguard.simulator import MultimodalSensorSimulator, ScenarioType
from cabinguard import config
from cabinguard.feature_extraction import FeatureExtractor
from cabinguard.classifier import BayesianEtiologyClassifier
from cabinguard.watchdog import CrossSensorWatchdog
from cabinguard.safety_controller import VehicleSafetyController, MRMState
from cabinguard.telematics import TelematicsEngine

console = Console() if HAS_RICH else None

def print_banner():
    title = """
================================================================================
           CabinGuard-ADI: In-Cabin Driver Medical Crisis Framework
                 IEEE VTS TSYP14 Technical Challenge - Phase 1
================================================================================
 Multi-Modal Sensor Fusion | UNECE R157 MRM | AUTOSAR SecOC | 76-Byte MEC eCall
================================================================================
"""
    if HAS_RICH:
        console.print(Panel(Text(title.strip(), justify="center", style="bold cyan"), border_style="blue"))
    else:
        print(title)

def run_simulation(scenario: ScenarioType, speed_multiplier: float = 1.0, show_progress: bool = True):
    """Executes an end-to-end simulation of a specific driving/medical scenario."""
    if HAS_RICH:
        console.print(f"\n[bold green]>>> Launching Scenario:[/] [bold yellow]{scenario.value}[/]")
    else:
        print(f"\n>>> Launching Scenario: {scenario.value}")

    simulator = MultimodalSensorSimulator(scenario, duration_s=32.0, seed=42)
    extractor = FeatureExtractor()
    classifier = BayesianEtiologyClassifier()
    watchdog = CrossSensorWatchdog(classifier)
    controller = VehicleSafetyController(initial_speed_kmh=100.0)
    telematics = TelematicsEngine()

    sim_start_time = time.time()
    last_print_time = 0.0

    mrm_triggered = False
    final_mec = None
    final_can = None

    # Step through simulation frames at 10 Hz
    for frame in simulator:
        # Stage 1: Feature Extraction
        features = extractor.process_frame(frame)

        # Stage 2 & 3: Watchdog & Bayesian Classification (Algorithm 1)
        decision = watchdog.evaluate(features)

        # Stage 4: Safety Controller & Vehicle Dynamics
        dynamics = controller.step(
            mrm_trigger=decision.mrm_trigger_flag,
            etiology=decision.active_class,
            steering_torque=features.steering_torque_nm,
            brake_pressed=frame.brake_pedal_pressed
        )

        # Telematics Encoding on Events
        if dynamics.hazard_flashers_active:
            final_can = telematics.generate_can_fd_mrm_frame(
                target_decel=dynamics.longitudinal_accel_mss,
                hazards_on=dynamics.hazard_flashers_active,
                mrm_state_code=3
            )

        if dynamics.ecall_transmitted and final_mec is None:
            final_mec = telematics.generate_76byte_mec(
                etiology_str=dynamics.confirmed_etiology,
                confidence=decision.top_confidence,
                latency_ms=int(decision.persistence_seconds * 1000)
            )

        # Periodic Display (every 0.5s of simulation time)
        if show_progress and (frame.timestamp - last_print_time >= 0.5):
            last_print_time = frame.timestamp
            _render_step_status(frame.timestamp, features, decision, dynamics)

        # Control playback speed
        if speed_multiplier > 0:
            target_real_dt = config.FUSION_DT / speed_multiplier
            elapsed = time.time() - sim_start_time
            expected = frame.timestamp / speed_multiplier
            sleep_dt = expected - elapsed
            if sleep_dt > 0.001:
                time.sleep(sleep_dt)

    # Final Summary Report
    _render_scenario_summary(scenario, decision, dynamics, final_can, final_mec)

def _render_step_status(t, feat, decision, dyn):
    """Prints a concise single-line or multi-line telemetry status update."""
    post = decision.raw_classification.posteriors
    p_norm = post.get("Normal", 0.0)
    p_sync = post.get("Syncope", 0.0)
    p_seiz = post.get("Seizure", 0.0)

    status_line = (
        f"t={t:4.1f}s | "
        f"HR:{feat.rppg_hr_bpm:3.0f}bpm EAR:{feat.ear:.2f} SER:{feat.ser_2_6hz:.2f} PSI:{feat.psi:.2f} | "
        f"P(Norm/Sync/Seiz): {p_norm:.2f}/{p_sync:.2f}/{p_seiz:.2f} | "
        f"State: {dyn.mrm_state.name[:12]} | "
        f"Speed: {dyn.speed_kmh:5.1f}km/h | "
        f"Lat: {dyn.lateral_pos_m:4.1f}m"
    )

    if decision.laser_spoofing_detected:
        status_line += " [!] LASER SPOOFING BLOCKED"

    if HAS_RICH:
        color = "white"
        if dyn.mrm_state == MRMState.PHASE_1_PRE_ALERT:   color = "yellow"
        elif dyn.mrm_state == MRMState.PHASE_2_ESCALATION: color = "magenta"
        elif dyn.mrm_state == MRMState.PHASE_3_ACTIVE_MRM:  color = "red"
        elif dyn.mrm_state == MRMState.PHASE_4_STANDSTILL: color = "bold green"
        console.print(f"[{color}]{status_line}[/]")
    else:
        print(status_line)

def _render_scenario_summary(scenario, decision, dyn, can_frame, mec):
    """Prints the comprehensive final engineering outcome for the scenario."""
    if HAS_RICH:
        table = Table(title=f"Scenario Results: {scenario.value}", border_style="cyan")
        table.add_column("System Metric", style="bold")
        table.add_column("Outcome", style="green")

        table.add_row("Final Operational State", dyn.mrm_state.value)
        table.add_row("Confirmed Medical Etiology", dyn.confirmed_etiology)
        table.add_row("Final Vehicle Speed", f"{dyn.speed_kmh:.1f} km/h")
        table.add_row("Lateral Stopping Position", f"{dyn.lateral_pos_m:.2f} m ({'Shoulder Safe' if dyn.lateral_pos_m <= -6.5 else 'Active Lane'})")
        table.add_row("Total Stopping Distance", f"{dyn.longitudinal_dist_m:.1f} m")
        table.add_row("Doors Unlocked & Lights Active", str(dyn.doors_unlocked))
        table.add_row("Electronic Parking Brake Clamped", str(dyn.epb_clamped))

        if can_frame:
            table.add_row("CAN-FD SecOC Frame (0x120)", f"{can_frame.raw_bytes[:8].hex().upper()}... | Fresh:{can_frame.freshness_counter} | MAC:{can_frame.mac_signature_hex}")

        if mec:
            table.add_row("76-Byte MEC eCall Payload", f"Size: {len(mec.raw_76_bytes)}B | Code: 0x{mec.etiology_code:02X} | Conf: {mec.confidence_pct}% | GDPR Compliant: {mec.is_gdpr_compliant}")

        console.print(table)
    else:
        print("\n" + "="*60)
        print(f"SCENARIO RESULTS: {scenario.value}")
        print(f"- Final State: {dyn.mrm_state.value}")
        print(f"- Confirmed Etiology: {dyn.confirmed_etiology}")
        print(f"- Final Speed: {dyn.speed_kmh:.1f} km/h (Dist: {dyn.longitudinal_dist_m:.1f} m)")
        print(f"- Lateral Position: {dyn.lateral_pos_m:.2f} m")
        if mec:
            print(f"- 76-Byte MEC: Code=0x{mec.etiology_code:02X}, Conf={mec.confidence_pct}%, GDPR={mec.is_gdpr_compliant}")
        print("="*60 + "\n")

def run_all_benchmarks():
    """Runs all 5 scenarios automatically in fast-forward and compiles an executive summary."""
    print_banner()
    if HAS_RICH:
        console.print("[bold yellow]Executing Automated Test Suite across All 5 Target Scenarios...[/]\n")

    scenarios = [
        ScenarioType.NORMAL_DRIVING,
        ScenarioType.CARDIAC_SYNCOPE,
        ScenarioType.EPILEPTIC_SEIZURE,
        ScenarioType.OPTICAL_BLINDING_ATTACK,
        ScenarioType.IMU_HARDWARE_FAULT
    ]

    results = []
    for sc in scenarios:
        sim = MultimodalSensorSimulator(sc, duration_s=32.0, seed=42)
        ext = FeatureExtractor()
        clf = BayesianEtiologyClassifier()
        wd = CrossSensorWatchdog(clf)
        ctl = VehicleSafetyController()
        tel = TelematicsEngine()

        start_t = time.perf_counter()
        spoof_blocked = False
        degraded_entered = False

        for f in sim:
            feat = ext.process_frame(f)
            dec = wd.evaluate(feat)
            dyn = ctl.step(dec.mrm_trigger_flag, dec.active_class, feat.steering_torque_nm, f.brake_pedal_pressed)
            if dec.laser_spoofing_detected:
                spoof_blocked = True
            if dec.operational_mode != "Nominal Mode":
                degraded_entered = True

        exec_time_ms = (time.perf_counter() - start_t) * 1000.0
        avg_cycle_ms = exec_time_ms / len(sim)

        results.append({
            "Scenario": sc.value,
            "Final State": dyn.mrm_state.name,
            "Confirmed Etiology": dyn.confirmed_etiology,
            "Safe Shoulder Stop": (dyn.mrm_state == MRMState.PHASE_4_STANDSTILL and dyn.lateral_pos_m <= -6.5),
            "Spoofing Blocked": spoof_blocked,
            "Degraded Mode": degraded_entered,
            "Avg Cycle Latency": f"{avg_cycle_ms:.2f} ms"
        })

    if HAS_RICH:
        table = Table(title="CabinGuard-ADI Phase 1 Validation & Benchmark Summary", border_style="bold green")
        table.add_column("Scenario", style="cyan")
        table.add_column("Triggered Etiology", style="yellow")
        table.add_column("MRM Safety Action", style="magenta")
        table.add_column("Special Handling", style="green")
        table.add_column("Avg Latency/Step", style="white")

        for r in results:
            special = "Normal Baseline"
            if r["Spoofing Blocked"]: special = "[bold red]Spoofing Interlocked[/]"
            elif r["Degraded Mode"]: special = "[bold yellow]Degraded Mode Fallback[/]"
            elif r["Safe Shoulder Stop"]: special = "[bold green]Off-Lane Standstill OK[/]"

            table.add_row(
                r["Scenario"],
                r["Confirmed Etiology"],
                r["Final State"],
                special,
                r["Avg Latency/Step"]
            )
        console.print(table)
    else:
        print("Benchmark Summary:")
        for r in results:
            print(f"- {r['Scenario']}: {r['Confirmed Etiology']} | Action: {r['Final State']} | Latency: {r['Avg Latency/Step']}")

def interactive_menu():
    print_banner()
    while True:
        print("\nSelect a CabinGuard-ADI Demonstration Scenario:")
        print("  1. Normal Highway Driving (Baseline Cruise, Natural Blinking)")
        print("  2. Sudden Cardiac Syncope (Postural Slump, Bradycardia -> MRM Pullover)")
        print("  3. Convulsive Epileptic Seizure (2-6 Hz Clonic Tremor Resonance -> MRM Pullover)")
        print("  4. Adversarial Optical Blinding Attack (Algorithm 1 Anti-Spoofing Interlock)")
        print("  5. Headrest Sensor Disconnect Fault (Degraded Mode 2 Fallback)")
        print("  6. Run Full Benchmark & Automated Test Suite (All Scenarios)")
        print("  0. Exit")

        choice = input("\nEnter choice [0-6]: ").strip()
        if choice == "1":
            run_simulation(ScenarioType.NORMAL_DRIVING, speed_multiplier=2.0)
        elif choice == "2":
            run_simulation(ScenarioType.CARDIAC_SYNCOPE, speed_multiplier=2.0)
        elif choice == "3":
            run_simulation(ScenarioType.EPILEPTIC_SEIZURE, speed_multiplier=2.0)
        elif choice == "4":
            run_simulation(ScenarioType.OPTICAL_BLINDING_ATTACK, speed_multiplier=2.0)
        elif choice == "5":
            run_simulation(ScenarioType.IMU_HARDWARE_FAULT, speed_multiplier=2.0)
        elif choice == "6":
            run_all_benchmarks()
        elif choice == "0":
            print("Exiting CabinGuard-ADI PoC.")
            break
        else:
            print("Invalid selection, please try again.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CabinGuard-ADI PoC Prototype & Simulator")
    parser.add_argument("--scenario", choices=["normal", "syncope", "seizure", "attack", "fault"], help="Run specific scenario")
    parser.add_argument("--all", action="store_true", help="Run full benchmark suite across all scenarios")
    parser.add_argument("--speed", type=float, default=2.0, help="Simulation playback speed multiplier (default: 2.0x)")

    args = parser.parse_args()

    if args.all:
        run_all_benchmarks()
    elif args.scenario == "normal":
        run_simulation(ScenarioType.NORMAL_DRIVING, speed_multiplier=args.speed)
    elif args.scenario == "syncope":
        run_simulation(ScenarioType.CARDIAC_SYNCOPE, speed_multiplier=args.speed)
    elif args.scenario == "seizure":
        run_simulation(ScenarioType.EPILEPTIC_SEIZURE, speed_multiplier=args.speed)
    elif args.scenario == "attack":
        run_simulation(ScenarioType.OPTICAL_BLINDING_ATTACK, speed_multiplier=args.speed)
    elif args.scenario == "fault":
        run_simulation(ScenarioType.IMU_HARDWARE_FAULT, speed_multiplier=args.speed)
    else:
        interactive_menu()

