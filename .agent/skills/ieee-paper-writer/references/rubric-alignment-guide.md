# Scoring Rubric Alignment & Optimization Guide

This reference guide details how to structure and optimize academic papers for competitive engineering challenges, hackathons, and technical evaluations (e.g., IEEE VTS/EMBS Student Challenges).

---

## 1. The Reviewer Psychology & Scanning Behavior
Reviewers on technical evaluation panels typically review 10 to 30 submissions under tight time constraints. They evaluate using a structured rubric sheet. If a criterion is not immediately visible within **30 seconds of skimming**, points are lost.

### Key Rules for Rubric Visibility:
1. **Verbatim Keyword Matching:** Use the exact terminology from the challenge spec book in section titles, bold paragraph leads, and contribution items.
   * *Example:* If the rubric states "Multi-Etiology Differentiation (10 pts)", create a subsection explicitly titled: `\subsection{Multi-Etiology Differentiation Methodology}`.
2. **Explicit Score Anchoring:** In the introduction, explicitly state:
   > *"To address the challenge requirements for Multi-Etiology Differentiation, Clinical Grounding, and Minimum Risk Maneuvering, this paper introduces..."*
3. **Structured Summary Tables:** Tables are scanned before paragraphs. Ensure every major rubric category has a corresponding summary table:
   * Class parameter comparison table (for Multi-Etiology)
   * Fault matrix table (for Fail-Safe & Fault Handling)
   * Bit-level packet structure (for CAN/V2X Message Design)
   * Latency budget breakdown (for Real-Time Execution)

---

## 2. Category-Specific Optimization Playbook

### A. Clinical & Epidemiological Grounding (10 pts)
* **What Reviewers Look For:** Real medical epidemiology, clinical guideline citations, and physiological validity.
* **Winning Formula:**
  - Quote exact clinical diagnostic guidelines (e.g., American Heart Association / American College of Cardiology syncope guidelines, International League Against Epilepsy motor seizure classification).
  - Explicitly define physiological threshold numbers (e.g., bradycardia $<40\text{ BPM}$, tachycardia $>150\text{ BPM}$, clonic frequency resonance $2\text{--}6\text{ Hz}$, cerebral hypoperfusion time-to-LOC $3\text{--}5\text{ s}$).
  - Document medical assumptions and physiological variations across driver demographics.

### B. Multi-Etiology Differentiation (10 pts)
* **What Reviewers Look For:** Proving that the model does not just detect generic "unresponsiveness", but separates distinct diseases that require different responses.
* **Winning Formula:**
  - Define contrasting physiological profiles: Hyper-motor (seizure: high kinetic energy, muscular spasms) vs. Hypo-motor/Atonic (syncope: complete loss of tone, postural slump, cardiovascular collapse).
  - Include confusion matrix projections and multi-class posterior probability derivations.

### C. Vehicle Architecture & Real-Time Edge Processing (10 pts)
* **What Reviewers Look For:** Feasibility of real-vehicle integration, low latency, realistic bus communication, zero wearable burden.
* **Winning Formula:**
  - Provide a complete hardware topology showing sensor pinouts, CAN bus IDs, and gateway routing.
  - Detail an explicit latency budget (Frame acquisition $\to$ Preprocessing $\to$ Inference $\to$ Verification window $\to$ Bus transmission), showing total time $< 2.5\text{ s}$.
  - Benchmark resource consumption (CPU %, GPU RAM, power draw in Watts on embedded hardware like Jetson Orin / Raspberry Pi).

### D. CAN/V2X Message Design & Integrability (10 pts)
* **What Reviewers Look For:** Standard-compliant messaging, non-proprietary packets, low-overhead bit layouts.
* **Winning Formula:**
  - V2V: Cite ETSI EN 302 637-3 (DENM) with specific Cause Codes (Cause Code 6 = Vehicle breakdown / emergency stop).
  - V2N: Cite CEN/ETSI EN 15722 (eCall) and Commission Regulation (EU) 2024/1180 (NG-eCall).
  - Present an exact bit-level packet diagram (e.g., the 76-byte Medical Extension Container).
  - Explain how emergency vehicles (ambulances) use this data to prepare medical countermeasures before arriving.

### E. Fail-Safe & Fault Handling Design (5 pts)
* **What Reviewers Look For:** What happens when sensors fail, get dirty, or are blinded?
* **Winning Formula:**
  - Present an ASIL-D fault matrix.
  - Define at least two distinct degraded operational modes (e.g., Degraded Mode 1 when camera is blinded, Degraded Mode 2 when IMU disconnects).
  - Cross-sensor plausibility checks: If sensor A indicates an emergency but sensor B indicates normal driving, how is the conflict resolved without crashing the vehicle?

### F. Cybersecurity & Privacy by Design (15 pts Phase 2 / Prep Phase 1)
* **What Reviewers Look For:** Compliance with GDPR Article 9 (Special Category biometric data) and automotive cybersecurity (ISO/SAE 21434, UN R155).
* **Winning Formula:**
  - Assert that zero raw video, facial landmarks, or biometric waveforms leave the local edge device.
  - Detail message integrity (AUTOSAR SecOC with AES-128 CMAC).
  - Detail anti-replay protection (monotonically increasing sequence counters, UTC timestamp windows $< 500\text{ ms}$).
  - Use rotating pseudonym certificates (IEEE 1609.2 SCMS) to prevent vehicle tracking.

