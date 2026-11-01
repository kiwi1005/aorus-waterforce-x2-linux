# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from RigDeck; see NOTICE.md for provenance and modifications.
"""Low-level driver for GIGABYTE AORUS WATERFORCE X II AIO coolers (USB 0414:7a5e).

Protocol reverse-engineered from GIGABYTE Control Center 26.08 (see docs/protocol.md).
Every report uses HID report ID 0x99; output reports are 6144 bytes, input reports 256.
"""
from __future__ import annotations

import errno
import glob
import os
import select
import time
from dataclasses import dataclass
from enum import IntEnum

import fcntl

class RigdeckError(Exception):
    pass

VENDOR_ID = 0x0414
PRODUCT_IDS = {0x7A5E: "AORUS WATERFORCE X II"}

REPORT_ID = 0x99
OUT_LEN = 6144
IN_LEN = 256
CHUNK = OUT_LEN - 3  # upload payload per 0xF2 report


class SpeedType(IntEnum):
    FAN = 1
    PUMP = 2


class SpeedMode(IntEnum):
    BALANCED = 0
    CUSTOMIZED = 1
    DEFAULT = 2
    FIXED_RPM = 3
    TURBO = 4
    PERFORMANCE = 5
    QUIET = 6
    ZERO_RPM = 7


FAN_MODES = [SpeedMode.DEFAULT, SpeedMode.ZERO_RPM, SpeedMode.QUIET, SpeedMode.BALANCED,
             SpeedMode.PERFORMANCE, SpeedMode.TURBO, SpeedMode.CUSTOMIZED]
PUMP_MODES = [SpeedMode.BALANCED, SpeedMode.TURBO]

# Preset curves GCC shows for the X II series (points at 0/30/50/65 °C). Zero RPM has none published.
PRESET_TEMPS = (0, 30, 50, 65)
PRESET_FAN = {
    SpeedMode.DEFAULT: (1200, 1200, 1400, 2000),
    SpeedMode.QUIET: (1000, 1000, 1000, 1500),
    SpeedMode.BALANCED: (1200, 1200, 1400, 1800),
    SpeedMode.PERFORMANCE: (1800, 1800, 1800, 2400),
    SpeedMode.TURBO: (2300, 2300, 2300, 2400),
}
PRESET_PUMP = {
    SpeedMode.BALANCED: (2500, 2500, 2500, 3000),
    SpeedMode.TURBO: (3000, 3000, 3000, 3000),
}


def preset_curve(kind: "SpeedType", mode: "SpeedMode") -> list[tuple[int, int]] | None:
    table = PRESET_FAN if kind == SpeedType.FAN else PRESET_PUMP
    rpms = table.get(mode)
    return list(zip(PRESET_TEMPS, rpms)) if rpms else None


MODEL_VARIANTS = {0: "WATERFORCE X II 240", 1: "WATERFORCE X II 360I", 2: "WATERFORCE X II 360"}

# Hardware LED effects; byte layouts replayed exactly as GCC sends them.
LED_STATIC = bytes([0xC9, 0x01, 0x64, 0x0A, 0xCC])
LED_RAINBOW_WAVE = bytes([0xC9, 0x08, 0x64, 0x09, 0xCC, 0xCC])

# Screen modes as reported by 0xE8 / set by 0xE7 (value on the wire).
SCREEN_MODE_CUSTOM_GIF = 7
MAX_CAROUSEL = 250


class CoolerError(RigdeckError):
    pass


@dataclass
class Status:
    fan_rpm: int
    pump_rpm: int
    fan_mode: SpeedMode
    pump_mode: SpeedMode


def find_hidraw() -> list[tuple[str, int]]:
    """Return [(devnode, product_id)] for every supported cooler."""
    found = []
    for sysdir in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(sysdir, "device", "uevent")) as f:
                uevent = dict(line.strip().split("=", 1) for line in f if "=" in line)
        except OSError:
            continue
        hid_id = uevent.get("HID_ID", "")  # e.g. 0003:00000414:00007A5E
        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        vid, pid = int(parts[1], 16), int(parts[2], 16)
        if vid == VENDOR_ID and pid in PRODUCT_IDS:
            found.append(("/dev/" + os.path.basename(sysdir), pid))
    return found


class Cooler:
    def __init__(self, path: str | None = None):
        if path is None:
            devs = find_hidraw()
            if len(devs) != 1:
                raise CoolerError("expected exactly one AORUS WATERFORCE X II")
            path, self.product_id = devs[0]
        else:
            self.product_id = 0x7A5E
        self.path = path
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(self.fd)
                raise CoolerError("device already in use by a cooperating client")
        except PermissionError as e:
            raise CoolerError(f"no permission for {path}; install the waterforce-linux udev rule (see README)") from e

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- transport -------------------------------------------------------

    def _drain(self):
        deadline = time.monotonic() + 1
        while select.select([self.fd], [], [], 0)[0]:
            if time.monotonic() > deadline:
                raise CoolerError("input did not drain; another client may be running")
            try:
                os.read(self.fd, IN_LEN)
            except BlockingIOError:
                break

    def send(self, payload: bytes):
        """Send one report. `payload` excludes the 0x99 report ID."""
        if len(payload) > OUT_LEN - 1:
            raise ValueError("payload too long")
        buf = bytes([REPORT_ID]) + payload + bytes(OUT_LEN - 1 - len(payload))
        try:
            if os.write(self.fd, buf) != len(buf):
                raise CoolerError("short HID write; not retried")
        except OSError as e:
            raise CoolerError(f"write failed: {e}") from e

    def query(self, payload: bytes, timeout: float = 1.0, match: int = 1) -> bytes:
        """Send a command and return the 256-byte reply that echoes its first `match` bytes."""
        self._drain()
        self.send(payload)
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                break
            try:
                reply = os.read(self.fd, IN_LEN)
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    continue
                raise CoolerError(f"read failed: {e}") from e
            if reply[:1] == bytes([REPORT_ID]) and reply[1:1 + match] == payload[:match]:
                return reply
        raise CoolerError(f"no reply to command 0x{payload[0]:02x}")

    # ---- info ------------------------------------------------------------

    def firmware(self) -> str:
        r = self.query(b"\xd6")
        return f"{r[2]}.{r[3]}"

    def model(self) -> str:
        r = self.query(b"\xde")
        return "GP-AORUS " + MODEL_VARIANTS.get(r[2], f"WATERFORCE X II (variant {r[2]})")

    def rpm(self) -> tuple[int, int]:
        r = self.query(b"\xda")
        return int.from_bytes(r[2:5], "little"), int.from_bytes(r[5:8], "little")

    def modes(self) -> tuple[SpeedMode, SpeedMode]:
        r = self.query(b"\xdd")
        fan, pump = (0 if v == 3 else v for v in r[2:4])
        return SpeedMode(fan), SpeedMode(pump)

    def status(self) -> Status:
        fan_rpm, pump_rpm = self.rpm()
        fan_mode, pump_mode = self.modes()
        return Status(fan_rpm, pump_rpm, fan_mode, pump_mode)

    def curve(self, kind: SpeedType) -> list[tuple[int, int]]:
        r = self.query(bytes([0xD9, kind]))
        return [(r[4 + i * 3], (r[5 + i * 3] << 8) | r[6 + i * 3]) for i in range(4)]

    def storage_free_kb(self) -> int:
        r = self.query(b"\xfa\x42")
        return int.from_bytes(r[3:3 + r[2]], "little")

    def screen_mode(self) -> int:
        return self.query(b"\xe8")[2]

    def save(self):
        self.send(b"\xb6")

    def send_sensors(self, cpu_temp: int, cpu_load: int, ghz_tenths: int = 0,
                     threads: int = 0, cores: int = 0, liquid_temp: int = 0, cpu_power: int = 0,
                     amd: bool = True):
        """Live data the cooler's curves and screen use. Send every ~1.5 s."""
        clamp = lambda v: max(0, min(255, int(v)))
        p = max(0, min(65535, int(cpu_power)))
        self.send(bytes([0xE0, 0 if amd else 1, clamp(cpu_temp), clamp(threads),
                         clamp(ghz_tenths // 10), clamp(ghz_tenths % 10), clamp(cores), 0,
                         clamp(liquid_temp), clamp(cpu_load), p & 0xFF, p >> 8]))

    def send_cpu_name(self, name: str):
        b = name.encode("ascii", "replace")[:250]
        self.send(bytes([0xE1, len(b)]) + b)
