"""Phase 2 hardware front ends: ESP32 sensor node, camera, and CAN bus.

Everything here produces or consumes the same objects the simulator and the
pipeline use (``SensorSnapshot`` and the ``Bus`` interface), so the detection,
watchdog and safety code runs unchanged on a bench or in a vehicle.

Optional dependencies are imported lazily: ``pyserial`` for the sensor node,
``opencv-python`` and ``mediapipe`` for the camera, ``python-can`` for CAN.

Sensor-node frame (little endian, 24 bytes, 100 Hz):

    0   2  sync 0xA5 0x5A
    2   2  sequence number (wraps)
    4   4  node time, ms
    8   6  acceleration x, y, z, int16, MPU6050 at +-4 g (8192 LSB/g)
    14  2  seatback FSR, 12-bit ADC
    16  2  wheel-rim grip force FSR, 12-bit ADC
    18  1  capacitive touch zones (bit 0 left, bit 1 right)
    19  2  steering proxy, 12-bit ADC (bench potentiometer or torque sensor)
    21  1  status flags (bit 0 IMU I2C error)
    22  2  CRC-16/CCITT-FALSE over bytes 0..21
"""
from __future__ import annotations

import struct
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from .simulator import SensorSnapshot
from .vision import (CHIN, FOREHEAD, LEFT_EYE, NOSE_TIP, RIGHT_EYE, RPPGTracker, eye_aspect_ratio,
                     head_pitch_deg)

SYNC = b"\xA5\x5A"
FRAME = struct.Struct("<2sHI3hHHBHBH")
ACC_LSB_PER_G = 8192.0
IMU_FS = 100.0
FSR_FULL_SCALE = 4095.0
GRIP_CLENCH_ADC = 3000          # rim force above which the grip counts as clenched
STEER_NM_PER_COUNT = 10.0 / 2048.0   # bench proxy: full potentiometer travel = +-10 Nm


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


@dataclass
class NodeSample:
    seq: int
    node_ms: int
    acc_g: tuple
    fsr: float
    grip_force: int
    touch: int
    steer_nm: float
    imu_error: bool
    host_t: float


def encode_node_frame(seq, node_ms, acc_raw, fsr, grip_force, touch, steer, flags=0) -> bytes:
    """Reference encoder (used by tests and the firmware's documentation)."""
    body = FRAME.pack(SYNC, seq & 0xFFFF, node_ms & 0xFFFFFFFF, *acc_raw, fsr, grip_force, touch, steer, flags, 0)[:-2]
    return body + struct.pack("<H", crc16_ccitt(body))


class NodeParser:
    """Byte-stream parser with resynchronisation, CRC check and gap counting."""

    def __init__(self):
        self.buf = bytearray()
        self.crc_errors = 0
        self.lost = 0
        self._last_seq: int | None = None

    def feed(self, data: bytes, host_t: float) -> list[NodeSample]:
        self.buf += data
        out = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:
                del self.buf[:-1]
                return out
            if len(self.buf) - i < FRAME.size:
                del self.buf[:i]
                return out
            raw = bytes(self.buf[i:i + FRAME.size])
            if crc16_ccitt(raw[:-2]) != struct.unpack("<H", raw[-2:])[0]:
                self.crc_errors += 1
                del self.buf[:i + 1]
                continue
            del self.buf[:i + FRAME.size]
            _, seq, ms, ax, ay, az, fsr, grip, touch, steer, flags, _ = FRAME.unpack(raw)
            if self._last_seq is not None:
                self.lost += (seq - self._last_seq - 1) & 0xFFFF
            self._last_seq = seq
            out.append(NodeSample(seq, ms, (ax / ACC_LSB_PER_G, ay / ACC_LSB_PER_G, az / ACC_LSB_PER_G),
                                  fsr / FSR_FULL_SCALE, grip, touch, (steer - 2048) * STEER_NM_PER_COUNT,
                                  bool(flags & 1), host_t))


def grip_state(touch: int, grip_force: int) -> str:
    if grip_force >= GRIP_CLENCH_ADC:
        return "CLENCHED"
    return "ACTIVE" if touch else "DISENGAGED"


class SerialSensorNode:
    """Reads the ESP32 node on a background thread and keeps the last 2 s of IMU data."""

    def __init__(self, port: str, baud: int = 921600):
        import serial  # pyserial
        self.ser = serial.Serial(port, baud, timeout=0.02)
        self.parser = NodeParser()
        self.acc: deque = deque(maxlen=int(2 * IMU_FS))
        self.last: NodeSample | None = None
        self._lock = threading.Lock()
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop:
            data = self.ser.read(256)
            if data:
                for s in self.parser.feed(data, time.monotonic()):
                    with self._lock:
                        if not s.imu_error:
                            self.acc.append(s.acc_g)
                        self.last = s

    def fill(self, snap: SensorSnapshot) -> None:
        with self._lock:
            s = self.last
            if s is None:
                return
            if not s.imu_error and len(self.acc) == self.acc.maxlen:
                snap.imu_t, snap.imu_window_g = s.host_t, np.array(self.acc)
            snap.seat_t = s.host_t
            snap.fsr_pressure = s.fsr
            snap.grip = grip_state(s.touch, s.grip_force)
            snap.steering_torque_nm = s.steer_nm

    def close(self):
        self._stop = True
        self.ser.close()


class CameraFrontEnd:
    """OpenCV capture + MediaPipe Face Mesh -> EAR, head pitch, rPPG beats.

    ``optical_snr_db`` is an exposure check on the forehead patch: a patch
    near saturation or near black (laser, low light) reads -20 dB, otherwise
    +10 dB, which the watchdog compares with ``MIN_OPTICAL_SNR_DB``.
    """

    def __init__(self, index: int = 0, fps: float = 30.0):
        import cv2
        import mediapipe as mp
        self.cv2 = cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=False, max_num_faces=1)
        self.rppg = RPPGTracker(fps)
        self.state = {"t": None, "face": False, "snr": -20.0, "ear": None, "pitch": None}
        self.beats: list[float] = []
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            ok, frame = self.cap.read()
            t = time.monotonic()
            if not ok:
                continue
            res = self.mesh.process(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB))
            h, w = frame.shape[:2]
            if not res.multi_face_landmarks:
                with self._lock:
                    self.state.update(t=t, face=False)
                continue
            lm = res.multi_face_landmarks[0].landmark
            p = np.array([[q.x * w, q.y * h, q.z * w] for q in lm])
            ear = 0.5 * (eye_aspect_ratio(p[list(LEFT_EYE), :2]) + eye_aspect_ratio(p[list(RIGHT_EYE), :2]))
            pitch = head_pitch_deg(p[FOREHEAD], p[NOSE_TIP], p[CHIN])
            fx, fy = int(p[FOREHEAD, 0]), int(p[FOREHEAD, 1])
            r = max(4, int(0.04 * w))
            patch = frame[max(0, fy):fy + 2 * r, max(0, fx - r):fx + r]
            if patch.size == 0:
                continue
            mean_bgr = patch.reshape(-1, 3).mean(axis=0)
            snr = -20.0 if (mean_bgr.max() > 245 or mean_bgr.mean() < 15) else 10.0
            self.rppg.push(t, mean_bgr[::-1])
            beats, _ = self.rppg.new_beats()
            with self._lock:
                self.state.update(t=t, face=True, snr=snr, ear=ear, pitch=pitch)
                self.beats += beats

    def fill(self, snap: SensorSnapshot) -> None:
        with self._lock:
            s = self.state
            snap.camera_t, snap.face_detected, snap.optical_snr_db = s["t"], s["face"], s["snr"]
            snap.ear, snap.pitch_deg = s["ear"], s["pitch"]
            snap.new_beats, self.beats = self.beats, []


class HardwareSource:
    """Iterates SensorSnapshots at 10 Hz from the live front ends."""

    def __init__(self, node: SerialSensorNode | None, camera: CameraFrontEnd | None):
        self.node, self.camera = node, camera

    def snapshot(self) -> SensorSnapshot:
        snap = SensorSnapshot(t=time.monotonic(), camera_t=None, imu_t=None, seat_t=None)
        if self.camera:
            self.camera.fill(snap)
        if self.node:
            self.node.fill(snap)
        return snap


class CanBus:
    """python-can backed implementation of the pipeline's ``Bus`` interface."""

    def __init__(self, interface: str = "virtual", channel: str = "cabinguard", bitrate: int = 500000):
        import can
        kw = {"bitrate": bitrate} if interface == "socketcan" else {}
        self.can = can
        self.bus = can.Bus(interface=interface, channel=channel, receive_own_messages=False, **kw)
        self.frames: list = []

    def send(self, arb_id: int, data: bytes) -> None:
        self.bus.send(self.can.Message(arbitration_id=arb_id, data=data, is_extended_id=False))

    def drain(self) -> list[tuple[int, bytes]]:
        out = []
        while (msg := self.bus.recv(timeout=0.0)) is not None:
            out.append((msg.arbitration_id, bytes(msg.data)))
        return out

    def close(self):
        self.bus.shutdown()
