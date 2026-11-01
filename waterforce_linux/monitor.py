#!/usr/bin/python3.11
"""Feed real CPU telemetry to 0414:7a5e; transport from pinned RigDeck.

GPL-3.0-or-later. No flash writes or fan-curve changes in normal operation.
On sensor failure, request volatile turbo modes instead of sending fake 0 C.
"""
import argparse
import logging
import signal
import time
from pathlib import Path

from .device import Cooler
from .presets import read_config, live_label
from .sensors import CpuSensors, core_counts, is_amd

log = logging.getLogger("waterforce-monitor")
running = True


def read_temperature(path):
    if not path:
        raise ValueError("CPU temperature sensor missing")
    value = int(Path(path).read_text())
    if not 1000 <= value <= 110000:
        raise ValueError(f"invalid CPU temperature: {value} millidegrees")
    return round(value / 1000)


def f2_sensor_payload(temperature, load, frequency_mhz):
    # AorusLcdService 26.08: SendCoolerData47A5EElite, 24 bytes including 0x99.
    if not 1 <= temperature <= 110:
        raise ValueError("invalid CPU temperature")
    report = bytearray(24)
    report[:2] = bytes([0x99, 0xE0])
    report[4] = temperature
    report[6] = max(0, min(255, frequency_mhz // 1000))
    report[7] = (max(0, frequency_mhz) // 100) % 10
    report[11] = max(0, min(100, load))
    return bytes(report[1:])  # Cooler.send adds report ID.


def stop(signum, frame):
    global running
    running = False


def run(once=False, sensor=None):
    sensors = CpuSensors()
    if sensor:
        sensors.temp_path = sensor
    cores, threads = core_counts()
    with Cooler() as cooler:
        firmware = tuple(map(int, cooler.firmware().split(".")))
        log.info("connected: %s firmware=%s", cooler.model(), firmware)
        original_modes = cooler.modes()
        failed = False
        last_log = 0
        last_label_check = 0
        last_label = None
        while running:
            try:
                temperature = read_temperature(sensors.temp_path)
            except (OSError, ValueError) as exc:
                if not failed:
                    # Same observed protocol as RigDeck, without save-to-flash.
                    cooler.send(bytes([0xE5, 1, 4]))
                    cooler.send(bytes([0xE5, 2, 4]))
                    cooler.send_cpu_name("CPU SENSOR ERROR")
                    log.error("%s; requested fan/pump turbo, no fake temperature sent", exc)
                    failed = True
                if once:
                    raise
                time.sleep(3)
                sensors = CpuSensors()
                if sensor:
                    sensors.temp_path = sensor
                continue
            if failed:
                for kind, mode in enumerate(original_modes, 1):
                    cooler.send(bytes([0xE5, kind, int(mode)]))
                log.info("CPU sensor recovered; restored original cooling modes")
                failed = False
                last_label_check = 0
                last_label = None
            now = time.monotonic()
            if now - last_label_check >= 10 or last_label is None:
                label = live_label(read_config())
                if label != last_label:
                    cooler.send_cpu_name(label)
                    last_label = label
                last_label_check = now
            if firmware >= (2, 0):
                cooler.send(f2_sensor_payload(temperature, sensors.load(), sensors.freq_mhz()))
            else:
                cooler.send_sensors(cpu_temp=temperature, cpu_load=sensors.load(),
                                    ghz_tenths=sensors.freq_mhz() // 100,
                                    cores=cores, threads=threads, amd=is_amd())
            now = time.monotonic()
            if now - last_log >= 30 or last_log == 0:
                fan, pump = cooler.rpm()
                log.info("sent CPU=%d C; fan=%d rpm pump=%d rpm screen=%d sensor=%s",
                         temperature, fan, pump, cooler.screen_mode(), sensors.temp_path)
                last_log = now
            if once:
                return
            time.sleep(1.5)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--sensor", help="explicit CPU hwmon temp*_input path")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    global running
    running = True
    run(args.once, args.sensor)
