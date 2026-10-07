
# CABINGUARD-ADI TSYP14 TECHNICAL CHALLENGE 



## SCOPE & TOPIC 

Modern vehicles are becoming rolling sensor platforms, with cameras, steering surfaces, seat sensors, in-cabin motion sensors and CAN-bus telemetry. 

- Privacy-Preserving Emergency Broadcast: Share minimal anonymized data for effective emergency response. 

CabinGuard-ADI challenges teams to detect acute medical events in drivers such as epileptic seizure, cardiac syncope/arrhythmia, severe hypoglycemia or acute stroke as early and reliably as possible, while connecting the medical decision to a secure minimum-risk vehicle response. 

- Scientific & Engineering Honesty: Document assumptions, limitations, uncertainties, and performance. 

## Challenge Instructions 

Develop an in-cabin system that detects serious
medical deterioration and connects:

Sensors → Data Processing → Medical Detection →
Cybersecurity → Vehicle Safety

A high-confidence emergency should trigger an
appropriate response such as:
Alert → Verification → Controlled Deceleration → Safe
Positioning → Safe Stop

The system must also demonstrate:
Sensor/communication failure handling
Protection of sensitive biometric data
Rejection of tampered or unauthorized messages
Scientific justification
Privacy preservation
Safe failure behavior

## Challenge problem statement 

Sensors → Data Processing → Medical Detection → Cybersecurity → Vehicle Safety A high-confidence emergency should trigger an appropriate response such as: 

Sudden loss of driving capacity can have different medical causes and physiological signatures. The challenge is not to identify or restrict people with a medical history, but to recognize dangerous deterioration early enough to reduce harm while avoiding unsafe false alarms. 

Alert → Verification → Controlled Deceleration → Safe Positioning → Safe Stop 

The system must also demonstrate: 

- Sensor/communication failure handling Protection of sensitive biometric data Rejection of tampered or unauthorized messages Scientific justification Privacy preservation Safe failure behavior 

Key challenges: 

Wearables require user compliance. Driver-monitoring systems mainly target fatigue/ distraction. 

Single-modal sensing can cause false positives. Biometric data and safety-critical messages require protection. 

## Choose your Approach 

The challenge requires: 

Medical Event Detection: At least 2 medical-event classes + 1 normal-driving class 

Multimodal Reasoning: Combine relevant in-cabin
sensing modalities to reduce false positives.
Secure Vehicle Interface: Connect the detection
decision to a safe vehicle response.

Emergency Communication: Transmit minimum-
necessary, anonymized, etiology-aware information.

## Challenge Goal 

Multimodal Reasoning: Combine relevant in-cabin sensing modalities to reduce false positives. Secure Vehicle Interface: Connect the detection decision to a safe vehicle response. 

Early ADI Detection: Detect physiological and behavioral changes with minimal false alarms. Multi-Etiology Classification: Distinguish medical events from normal driving. 

Emergency Communication: Transmit minimumnecessary, anonymized, etiology-aware information. 

Complete System Architecture: Integrate sensing, processing, detection, control, and communication. 

Data Protection & Secure Communication: Protect biometric data and critical messages. 


## Phase 1:. Research & Concept Validation
Phase 1 focuses on:
Problem Definition Medical elevance AI /Detection
Approach System Architecture

Cybersecurity valuation
Design

Teams may use:
Simulated data
Synthetic data
Public de-identified data
Literature-derived assumptions

#Required deliverables

1.IEEE-Style Research Paper: max. 5 pages

The paper should follow a standard IEEE conference-
paper structure, including, as

applicable:

Abstract
Introduction & Motivation
Related Work / State of the Art
Problem Definition
Proposed Methodology
System Architecture
Medical Event Detection Approach
Cybersecurity & Threat Model
Experimental / Evaluation Methodology
Expected Results or Preliminary Results
Conclusion
References

Important note:
Teams are not expected to have a complete
final system or real-sensor

implementation at
this stage. The paper should clearly explain
what they
propose, why it is relevant, how it will
work, and how it will be evaluated in
Phase 2.

2.Proposed System Architecture
Teams must provide a clear end-to-end architecture
showing:
Sensors Data Acuisition Preprocessing Detection/
usion Safety Decision

Vehicle esponse Secure
Communication
The architecture should identify:
Proposed sensors
Data sources
AI/ML or detection method
Decision mechanism
Communication interfaces
Safety mechanisms
Cybersecurity controls
Privacy considerations

D etection & AI Methodology
Teams should specify:
Target medical events
Normal-driving class
Detection/classification approach
Input features/data
Proposed model or algorithm
Expected detection latency
Confidence/uncertainty strategy
False-positive / false-negative considerations
Security & Threat Model
Teams must identify:
Protected assets
Trust boundaries
Communication vulnerabilities
Privacy risks
Tampered/replayed/missing data
Unauthorized commands
Relevant cybersecurity threats
Preliminary Validation / Benchmarking
Teams should provide evidence supporting the
feasibility of their approach, for example:
Literature-based justification
Experiments on public datasets
Simulation results
Baseline comparison
Preliminary model results
Analytical justification
coplete prototpe is reired

Proposed System Architecture
Teams must provide a clear end-to-end architecture
showing:
Sensors Data Acuisition Preprocessing Detection/
usion Safety Decision

Vehicle esponse Secure
Communication
The architecture should identify:
Proposed sensors
Data sources
AI/ML or detection method
Decision mechanism
Communication interfaces
Safety mechanisms
Cybersecurity controls
Privacy considerations

O ptional Proof-of-Concept Prototype
Teams may implement a lightweight software
prototype demonstrating their

detection concept.

Examples:
A preprocessing pipeline
A trained baseline model
A simulator
A simple detection module
A dashboard
A simulated communication layer
his is optional and shold e considered a ons
rather than a prereisite oraliication


## Phase 2: Full-System Prototype & Real-Time Validation

Finalists transform their Phase 1 concept into a
functional end-to-end prototype.
Required Implementation
Finalists must implement the complete system using
real sensors and/or an approved

physical or simulated

vehicle environment, such as:
Vehicle simulator
CAN interface
Robotic platform
Embedded platform
Other approved environment

Real-Time Detection
Teams must demonstrate:
Detection of ≥2 medical-event classes
Normal driving
Real-time or near-real-time operation
Detection latency
Confidence/uncertainty where applicable
Secure Emergency Communication
Teams must demonstrate:
Secure transmission
Minimal necessary information
Anonymization/privacy protection
Appropriate authentication/integrity mechanisms
Handling of communication failure

The final system should demonstrate:
Real Sensors -> data aquiition ->  Detection/fusion ->   safety decision -> vehicle/simulator response-> secure emergency communication 

Phase 2 Deliverables
1.Updated IEEE-Style Research Paper: max. 6 pages
The Phase 1 paper is extended/updated with:
Final methodology
Implemented architecture
Experimental setup
Real-world implementation
Quantitative results
Detection latency
Classification performance
Safety evaluation
Cybersecurity evaluation
Limitations
Discussion
Conclusion

2.Functional End-to-End Prototype
The prototype must demonstrate the complete
pipeline:
Sensing -> Processing ->Detection ->
Safety-Decision
-> Vehicle Response -> Secure Communication
This is where you require actual implementation.

4.Vehicle/Safety Response
The system should demonstrate an appropriate
response to a detected event, for example:

Medical event detected -> confidence assessment -> safety
decision -> vehicle action-> emergency notification

The exact vehicle action should depend on the teams
proposed scenario.

3.Real-Time Detection
Teams must demonstrate:
Detection of ≥2 medical-event classes
Normal driving
Real-time or near-real-time operation
Detection latency
Confidence/uncertainty where applicable
5.Secure Emergency Communication
Teams must demonstrate:
Secure transmission
Minimal necessary information
Anonymization/privacy protection
Appropriate authentication/integrity mechanisms
Handling of communication failure

6.Safety & Cybersecurity Validation
Teams must demonstrate their system under
controlled failure/adversarial scenarios, such
as:

Sensor failure
Communication failure
Processing failure
Tampered data
Replayed messages
Missing data
Unauthorized commands
And then demonstrate the corresponding safe/
rejection behavior.
At least one controlled cybersecurity or data-integrity
attack/fault scenario

must be demonstrated.

## Rules & Criteria
Open to Student Branches
Maximum 5 members/team
Teams must address at least 2 medical event
classes + normal driving
Phase 1 may use simulated, synthetic, or public de
identified data
Phase 1 does not require a complete working
prototype
Phase 1 proof of concept implementations are
allowed and may strengthen a teams

evaluation
Phase 2 finalists must develop a functional
end to end prototype
Phase 2 must use real sensors and an approved
physical, embedded, robotic,

CAN, or vehicle

simulation environment
Solutions must address safety, cybersecurity and
privacy
Phase 2 teams must demonstrate controlled
handling of system failures and/or
malicious/

tampered data
All experiments and datasets must respect
applicable privacy and ethical

requirements

## Scoring
TOTAL SCORE: 105 POINTS + BONUS (Up to 4pts)
Phase 1: 55 Points
Detection Reliability & Robustness: 10 pts
Multi-Etiology Differentiation: 10 pts
Clinical & Epidemiological Grounding: 10 pts
Vehicle Architecture: 10 pts
CAN/V2X Message Design & Real-Vehicle
Integrability: 10 pts
Fail-Safe & Fault Handling Design: 5 pts
Phase 2: 50 Points
Cybersecurity & Privacy Design: 15 pts
Code Quality & Benchmarking Reproducibility: 15 pts
Report Quality & Architecture Documentation: 10 pts
Live Pitch: 5 pts
Innovation & Creativity: 5 pts
Bonus: Up to 4 Points
+1 pt: At least one IEEE VTS member
+1 pt: At least one IEEE EMBS member
+2 pts: Documented engagement with a
clinical/biomedical, EMS, cybersecurity, or
automotive-industry contact for validation


