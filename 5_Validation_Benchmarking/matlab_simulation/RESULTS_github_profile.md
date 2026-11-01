# Closed-loop results with the Python system's timings (profile 'github', highway scene 1, 100 km/h, T = 45 s)

All numbers were produced by `cg_auto_suite('github')` on our PC. Simulation only.

| Case | ALERT | HAZARD | Take-over | Stop | Collision | Note |
|---|---|---|---|---|---|---|
| Syncope at 2 s | 14.0 s | 18.0 s | 24.0 s | 8.8 s later, 123 m | rear-end hit by the scripted follower at 30.5 s, impact 0.7 m/s | needed only 0.3 m/s^2 at take-over |
| Seizure at 2 s | 14.5 s | 18.5 s | 24.5 s | 8.8 s later, 123 m | none, smallest gap 0.11 m | same follower |
| Camera lost | 14.6 s | 18.6 s | 24.6 s | 8.8 s later, 123 m | none, gap 1.8 m | degraded mode, +0.6 s |
| Cellular down | 14.0 s | 18.0 s | 24.0 s | - | follower hit as in syncope | e-call placed 18 s, delivered by SMS at 26 s |
| Conscious driver | none | none | none | - | contact with a slow car ahead at 33.6 s | no take-over, no ALERT: CabinGuard stayed quiet. The simulated driver does not brake for traffic |

Findings to state:
- The chain timeline matches the Python system: ALERT = onset + 12 s, HAZARD +4 s, take-over +10 s.
- With these timings the car has no driver control for about 22 s (about 600 m at 100 km/h) before braking begins.
- Collisions came from the scripted follower (10 to 45 m behind, reacting 1.3 to 2.8 s after we brake) and are reported, not tuned away.
- Not shown: statistics. This is one scene.
