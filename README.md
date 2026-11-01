# AORUS WATERFORCE X II on Linux

Display real CPU temperature on an AORUS WATERFORCE X II cooler under Linux,
including the **F2.0 telemetry format**, plus custom pictures and animations. Includes an optional firmware updater
for the exact X II 240 F1.2 → F2.0 upgrade tested during development.

**Hardware-tested:** WATERFORCE X II 240, USB `0414:7a5e`, firmware F2.0,
AMD Ryzen 7 9700X. The LCD displayed changing CPU temperature during a short
load test and the service survived restart. A full power-cycle test has not
been performed. Other sizes/firmware combinations are unverified.

[繁體中文說明](docs/README.zh-TW.md) · [Protocol](docs/protocol.md) ·
[Pictures and animations](docs/media.md) · [Firmware update](docs/firmware.md) · [Attribution](NOTICE.md)

## Why this exists

One tested system had a black LCD under F1.2. Updating to F2.0 restored the
screen, but the old telemetry packet then displayed a fixed **16°C**:
F2.0 interpreted the old packet's CPU thread-count byte as temperature.
This daemon selects the packet layout by firmware version.

This is a successful repair of one device, **not a claim that firmware updates
fix every black screen**. Try the display/telemetry tools before considering
an update. The Linux `gigabyte_waterforce` hwmon driver is a separate project;
this program uses HID userspace access and does not require that module.

## Requirements

- Linux, Python **3.11+**, USB HID access; no Python runtime dependencies.
- A working CPU temperature sensor exposed through hwmon: `k10temp`,
  `zenpower`, or `coretemp`; or an explicitly selected `--sensor` path.
- `ip` (iproute2/iproute) for the optional live IPv4 preset.
- `systemd`, `udev`, and `fuser` (usually the `psmisc` package) for the supplied
  service installer and exclusive-access checks.
- Stop other cooler clients, including RigDeck/CoolerControl, before running
  this daemon or changing display settings. Advisory locks cannot stop
  software that ignores them.

No kernel module is installed. If the CPU sensor is missing on an older
kernel, update to a distribution-supported kernel that supports your CPU.
Do not use an ACPI thermal-zone reading as CPU temperature merely because
it is the only sensor available.

## Try it from source

```sh
git clone https://github.com/kiwi1005/aorus-waterforce-x2-linux.git
cd aorus-waterforce-x2-linux
sudo python3.11 -m waterforce_linux status
sudo python3.11 -m waterforce_linux display-temperature --save
sudo python3.11 -m waterforce_linux monitor
```

`display-temperature` selects the built-in first screen, Celsius, and CPU
temperature in its first information zone. `--save` persists the settings;
omit it to stage settings (F2.0 may not visibly apply them until saved). Run it while the monitor service is stopped.
It does not upload images or replace stored media.

For a non-default sensor:

```sh
sudo python3.11 -m waterforce_linux monitor --sensor /sys/class/hwmon/hwmon2/temp1_input
```

Check the associated `name` and `temp1_label` first. Numeric hwmon paths can
change across boots; automatic discovery is preferable when supported.

## Display presets

Choose temperature, frequency, dual-metric, dashboard, cooling, or local-IP
layouts with `preset --manage-service choose` (root). See the bilingual
[preset guide](docs/presets.md). IP text follows address changes without flash
writes; requires the updated monitor service.

## Pictures and animations

See [the media guide](docs/media.md) for picture/GIF/video conversion, uploading,
playback switching and returning to CPU temperature. Requires FFmpeg + ffprobe.
Existing media is preserved; no firmware flash is needed.

## Start at boot

```sh
sudo ./install.sh
journalctl -u waterforce-linux -f
```

The installer creates a dedicated unprivileged `waterforce-linux` account,
installs code under `/opt/waterforce-linux`, adds a USB-specific udev rule,
and enables a systemd service. It sends telemetry every 1.5 seconds. It does
**not** flash firmware or change display settings. Set the display once with
the command above before starting the service.

Set `WATERFORCE_PYTHON` to an absolute, system-accessible Python path if needed:

```sh
sudo env WATERFORCE_PYTHON=/usr/bin/python3.11 ./install.sh
```

Do not install over another active cooler service. For manual commands after
installation, stop `waterforce-linux`, run the source CLI, then start it again.

To remove the installation:

```sh
sudo systemctl disable --now waterforce-linux
sudo rm /etc/systemd/system/waterforce-linux.service
sudo rm /etc/udev/rules.d/71-waterforce-linux.rules
sudo rm -r /opt/waterforce-linux
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```

The dedicated account/group is left in place. Removing the service does not
restore cooler flash settings or revert firmware.

## Sensor and cooling behavior

The daemon refuses missing or implausible CPU readings; it never substitutes
0°C for a failed sensor. On sensor failure while USB still works, it requests
volatile fan/pump Turbo and retries discovery. On recovery within the same
process it restores the modes captured at startup. On daemon/USB failure,
software cannot guarantee cooling behavior; the cooler may retain its last
telemetry. Verify your own cooling configuration. A process restart while in
Turbo may preserve Turbo rather than infer the earlier modes.

The current packet carries CPU temperature, load, and clock. Unsupported GPU,
power, and memory fields remain zero; do not enable those display widgets.
No fan curves are rewritten during normal operation.

## Tests and limitations

```sh
python3.11 -m unittest discover -s tests -v
python3.11 -m waterforce_linux --help
```

Tests cover the F2.0 byte positions, firmware framing/boundaries, corrupted
package rejection, failed-write aborts, and temperature validation. Tests do
not access hardware or flash anything. See [protocol evidence](docs/protocol.md)
for what was actually tested, rather than treating unit tests as hardware support.

GPL-3.0-or-later. Based in part on RigDeck; see [NOTICE.md](NOTICE.md).
