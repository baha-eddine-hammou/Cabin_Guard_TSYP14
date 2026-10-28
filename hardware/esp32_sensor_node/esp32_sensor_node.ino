// CabinGuard-ADI sensor node (ESP32, Arduino core 2.x or 3.x).
//
// Samples the headrest MPU6050, the seatback and wheel-rim FSRs, two
// capacitive touch zones on the wheel and a steering proxy at 100 Hz and
// streams one 24-byte frame per sample over USB serial at 921600 baud.
// The frame layout and CRC are defined in prototype/cabinguard/hardware.py,
// whose NodeParser is the reference decoder.
//
// Wiring (see hardware/README.md):
//   MPU6050  SDA=GPIO21 SCL=GPIO22, 3V3, GND   (I2C 400 kHz, address 0x68)
//   Seat FSR divider  -> GPIO34 (ADC1_CH6)
//   Rim FSR divider   -> GPIO35 (ADC1_CH7)
//   Steering pot/torque sensor -> GPIO32 (ADC1_CH4)
//   Touch pads: left -> GPIO4 (T0), right -> GPIO15 (T3)

#include <Wire.h>

static const uint8_t MPU_ADDR = 0x68;
static const uint32_t PERIOD_US = 10000;      // 100 Hz
static const int PIN_SEAT = 34, PIN_RIM = 35, PIN_STEER = 32;
static const int PIN_TOUCH_L = 4, PIN_TOUCH_R = 15;
static const uint16_t TOUCH_THRESHOLD = 30;   // lower reading = touched; calibrate per wheel

static uint16_t seq = 0;
static uint32_t next_us = 0;

static uint16_t crc16_ccitt(const uint8_t *d, size_t n) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t)d[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

static bool mpu_write(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static bool mpu_init() {
  return mpu_write(0x6B, 0x00)      // wake, internal clock
      && mpu_write(0x1A, 0x03)      // DLPF 44 Hz: removes aliasing above the 50 Hz Nyquist limit
      && mpu_write(0x1C, 0x08);     // accelerometer +-4 g, 8192 LSB/g
}

static bool mpu_read(int16_t a[3]) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)MPU_ADDR, 6) != 6) return false;
  for (int i = 0; i < 3; i++) a[i] = (int16_t)((Wire.read() << 8) | Wire.read());
  return true;
}

static inline void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static inline void put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = (v >> (8 * i)) & 0xFF; }

void setup() {
  Serial.begin(921600);
  Wire.begin(21, 22, 400000);
  analogReadResolution(12);
  mpu_init();
  next_us = micros();
}

void loop() {
  if ((int32_t)(micros() - next_us) < 0) return;
  next_us += PERIOD_US;

  int16_t a[3] = {0, 0, 0};
  uint8_t flags = 0;
  if (!mpu_read(a)) {
    flags |= 0x01;                   // IMU I2C error: host marks the IMU unavailable
    mpu_init();                      // try to recover a reset or reconnected sensor
  }
  uint8_t touch = 0;
  if (touchRead(PIN_TOUCH_L) < TOUCH_THRESHOLD) touch |= 0x01;
  if (touchRead(PIN_TOUCH_R) < TOUCH_THRESHOLD) touch |= 0x02;

  uint8_t f[24];
  f[0] = 0xA5; f[1] = 0x5A;
  put16(f + 2, seq++);
  put32(f + 4, millis());
  for (int i = 0; i < 3; i++) put16(f + 8 + 2 * i, (uint16_t)a[i]);
  put16(f + 14, analogRead(PIN_SEAT));
  put16(f + 16, analogRead(PIN_RIM));
  f[18] = touch;
  put16(f + 19, analogRead(PIN_STEER));
  f[21] = flags;
  put16(f + 22, crc16_ccitt(f, 22));
  Serial.write(f, sizeof f);
}
