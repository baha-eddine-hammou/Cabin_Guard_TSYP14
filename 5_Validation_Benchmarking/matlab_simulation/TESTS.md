# The 5 closed-loop tests (`cg_auto_suite('github')`)

All five run in the full Simulink model (detailed plant) on **highway scene 1**, start speed **100 km/h**, run length **45 s**,
with the timings of the Python system (`profile = 'github'`): ALERT = onset + 12 s, HAZARD 4 s later, take-over (BRAKE) 10 s after ALERT,
minimum-risk deceleration -3.2 m/s^2. The incapacitation starts at **2 s**. Simulation only.

Expected timeline when everything works: **ALERT 14 s, HAZARD 18 s, take-over 24 s, standstill about 33 s.**

| # | Test | What we inject | What it must show | Result |
|---|---|---|---|---|
| 1 | Syncope | Syncope at 2 s | Take-over near 24 s, controlled stop | Take-over 24.0 s, stop 8.8 s / 123 m. Marked failed: scripted follower hit the car from behind at 30.5 s (0.7 m/s) |
| 2 | Seizure | Seizure at 2 s | Same chain, detector delay 9.5 s, so take-over near 24.5 s | Take-over 24.5 s, no collision, smallest gap 0.11 m. **Pass** |
| 3 | Conscious driver | No event | CabinGuard must stay quiet: no ALERT, no take-over | No ALERT, no take-over. **Pass** |
| 4 | Camera lost | Camera sensor fails at 2 s | Take-over still happens, a little later (degraded mode) | Take-over 24.6 s (+0.6 s), no collision, gap 1.8 m. **Pass** |
| 5 | Cellular down | Cellular network unavailable | Take-over unchanged; the e-call goes by SMS 8 s after it was placed | E-call placed 18.0 s, delivered 26.0 s, take-over 24.0 s. Marked failed: same follower hit as in test 1 |

## What each test proves

1. **Syncope** shows the whole chain end to end: detector, Host verification, ALERT, HAZARD with the e-call, Gateway-approved BRAKE, stop.
2. **Seizure** shows that the second incapacitation type follows the same chain with its own detector latency.
3. **Conscious driver** shows there is no false take-over when nothing is wrong. The car holds speed because the simulated driver does not brake for traffic; a slow car ahead appears at 33.6 s. This contact is reported but not counted against CabinGuard.
4. **Camera lost** shows graceful degradation: the Host keeps working with the remaining sensors and reports a degraded mode, costing 0.6 s.
5. **Cellular down** shows that the manoeuvre never waits for the e-call: the stop is unchanged and the message falls back to SMS.

## Reading the two "failed" rows

Tests 1 and 5 are marked failed only because of a collision flag. In both, the contact is a **rear-end touch at 0.7 m/s by a scripted follower**
(10 to 45 m behind, reacting 1.3 to 2.8 s after we brake, non-reactive in the model). The take-over times, the e-call and the stop are as designed,
and only 0.3 m/s^2 of braking was needed at the take-over, so nothing ahead was involved. We report it and do not tune the scene to hide it.

## Timeline of tests 1 and 5 (identical until the e-call)

| Event | Time |
|---|---|
| Incapacitation | 2.0 s |
| ALERT | 14.0 s |
| HAZARD, e-call placed | 18.0 s |
| Take-over (BRAKE accepted) | 24.0 s |
| Standstill | about 33 s (8.8 s after take-over, 123 m) |

## Files

`results_final/suite_github/suite_system.csv` (all numbers), `suite01_chain.png` to `suite05_chain.png` (one figure per test in the order above),
`suite_overview.png` (all tests together).

## Conclusion

This is a **proof of concept**: it shows, in simulation, that the CabinGuard chain detects, verifies, hands the command through the authenticated
Gateway, performs a controlled stop and sends the emergency message, and that it degrades gracefully when a sensor or the network is lost.
It will be **enhanced in Phase 2**: the real AI in the loop, reactive traffic, protection of the unresponsive phase (AEB and follower warning),
more scenes and the real communication stack.
