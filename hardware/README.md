# Phase 2 bench prototype

The software in `prototype/` already runs against real hardware through
`cabinguard/hardware.py`. This page lists what to buy, how to wire it, and how
to run the end-to-end bench that Phase 2 asks for: real sensors, data
acquisition, detection, safety decision, a vehicle response over CAN, and
secure emergency communication.

## Bill of materials (about 150 EUR without the host)

| Item | Role | Notes |
|---|---|---|
| Edge host: laptop, Raspberry Pi 5, or Jetson Orin Nano | ECU (`run_realtime.py`) | Cycle compute is ~3 ms on a laptop core; measure on the target |
| USB camera, 30 fps, with IR-cut removed + 850 nm LED ring | Eyes, head pitch, rPPG | Mount on the steering column facing the driver |
| ESP32 DevKit (WROOM-32) | Sensor node (`hardware/esp32_sensor_node`) | USB serial 921600 baud |
| MPU6050 breakout | Headrest IMU | Inside the headrest foam, axes noted |
| 2 x FSR 406 (square, 38 mm) + 10 kOhm resistors | Seatback pressure, wheel-rim grip force | Voltage dividers into ADC1 pins |
| Copper tape, 2 pads | Capacitive touch zones on the rim | Left and right hand positions |
| 10 kOhm potentiometer or torque sensor | Steering-torque proxy | Bench stand-in for the EPS torque signal |
| 2 x USB-CAN adapter (CANable / PCAN-USB), or MCP2515 HAT on a Pi | ECU and gateway on a real CAN bus | 120 Ohm termination at both ends |
| Second machine or Pi | Gateway / actuator side (`run_gateway.py`) | Can be the same PC on a virtual channel |
| 4G USB modem (optional) | Real cellular bearer for the MEC | The SMS fallback uses the same modem |

## Wiring

```
                 USB 3.0 (UVC)
NIR camera  ───────────────────────────────┐
                                           │
MPU6050 ──I2C(21/22)──┐                    ▼
Seat FSR ──GPIO34─────┤               ┌──────────┐   CAN-H/L   ┌──────────────┐
Rim FSR  ──GPIO35─────┼─ ESP32 ─USB──▶│ ECU host │────────────▶│ Gateway host │──▶ actuator log /
Touch L/R─GPIO4/15────┤               └──────────┘             └──────────────┘    simulator
Steer pot─GPIO32──────┘                    │ cellular / SMS
                                           ▼
                                     PSAP endpoint
```

## Bring-up

1. Flash `esp32_sensor_node.ino` (Arduino IDE, board "ESP32 Dev Module").
   Calibrate `TOUCH_THRESHOLD` by printing `touchRead` with and without a hand.
2. `pip install -e "prototype[hardware]"` on the ECU host.
3. Generate a SecOC key and copy it to both hosts, never into git:
   `python -c "import os;print(os.urandom(16).hex())" > secrets/secoc.key`
4. Bring up CAN on Linux: `sudo ip link set can0 up type can bitrate 500000`.
5. Gateway side: `python run_gateway.py --can socketcan:can0 --key-file secrets/secoc.key`
6. ECU side: `python run_realtime.py --source hardware --serial /dev/ttyUSB0 --camera 0 --can socketcan:can0 --key-file secrets/secoc.key`

Without CAN hardware, `--can virtual` on both commands runs the same frames
over python-can's in-process bus.

## Phase 2 validation plan

Each row produces a number the Phase 2 paper must report; the scripts that
produce the software-only versions of these numbers are listed.

| Requirement | Bench procedure | Metric | Software analogue |
|---|---|---|---|
| Normal driving, false alarms | Volunteers drive a simulator rig for 2 h each | MRM starts per hour, pre-alerts per hour | `realdata/evaluate_fusion.py` |
| Syncope class | Volunteer simulates collapse (eyes closed, head drop, hands off) with a recorded pulseless rPPG trace replayed into the camera path | Sensitivity, onset-to-MRM latency | composite syncope episodes |
| Seizure class | Volunteer performs a scripted convulsion mimic on the instrumented seat; IMU amplitude logged | Sensitivity vs measured headrest amplitude | `motion_injected.npz` sweep |
| rPPG accuracy | Camera vs finger PPG reference, still and with simulated road vibration | MAE in bpm, beat detection F1 | `vision.RPPGTracker` |
| Real-time | 1 h continuous run on the target host | Cycle compute median, p99, max vs 100 ms | `run_realtime.py` summary |
| Sensor failure / missing data | Unplug the IMU, cover the camera, disconnect the seat FSR mid-run | Mode reported, false MRM count | `fault_matrix.py` |
| Processing failure | Kill or stall the ECU process during normal driving and during an MRM | Gateway reaction time, fail-silent vs fail-operational | `fault_matrix.py` |
| Tampered, replayed, forged, implausible frames | `cansend`/python-can attacker node on the bus | Rejection rate, vehicle reaction | `fault_matrix.py` |
| Communication failure | Pull the modem antenna / disable data | Delivery time with retries and SMS fallback | `fault_matrix.py` |

Recruiting volunteers needs ethics approval and informed consent; no patient
data is needed for the bench, and no raw video or physiological waveform is
stored by the software (only the 10 s feature buffers in memory).
