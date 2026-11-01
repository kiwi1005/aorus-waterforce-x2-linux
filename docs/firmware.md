# Optional F1.2 → F2.0 firmware update

**You do not need to flash firmware to use telemetry on an already working
F2.0 device.** This updater supports only the exact X II240 F1.2 → F2.0 path
and package tested during development. It intentionally rejects other models,
versions, descriptors, hashes and package sizes. It is not a recovery tool.

An update writes device firmware. Use stable power and a local persistent
session, stop other cooler clients, and keep the machine awake. Software locks
cannot prevent a power loss. Do not interrupt an update, automatically retry a
failed transfer, or assume a black LCD means the operation has completed.

## Obtain and extract the package

Obtain `AORUS_WATERFORCE_X_II_240_360_360I_F2.0_SOP.exe` from a legitimate
[GIGABYTE support source](https://www.gigabyte.com/CPU-Cooler/AORUS-WATERFORCE-X-II-240/support).
No vendor binary is included here. The tested file hashes are:

| File | SHA256 |
|---|---|
| Supplied EXE | `48a2818cdd9a072497d4b623680eae93bb584232986c55ef3e24d835a4a85bfb` |
| Embedded F2.0 PKG,11447615bytes | `bd7ed3d4a9313821f69b9a2cec94e061124bf8ba9e1e655021a08377f8a263d5` |

These hashes identify the analyzed files; they do not verify the vendor's digital
signature. A differently packaged revision needs new analysis, not removal of
the checks. Optional static extraction (never executes the EXE):

```sh
python3.11 -m venv .analysis-venv
.analysis-venv/bin/pip install dnfile
.analysis-venv/bin/python tools/extract_firmware.py /path/to/vendor.exe /path/to/firmware.pkg
python3.11 -m waterforce_linux firmware plan --pkg /path/to/firmware.pkg
```

`plan` opens no hardware. Expected output:1868reports,6144bytes each,
wire SHA256 `6789902268c1d7d443a76ac31d375a0010bb8adff6b4d6c3728761b4e1718274`.

## Perform an intentional update

Read the vendor SOP. Stop and disable your current cooler daemon before flashing;
close every other HID client. This prevents it from restarting during a device
reset or unexpected host restart. The updater checks known system services and
`fuser` ownership but cannot detect all future/uncooperative clients.

Example for this project's service, from a local terminal or persistent tmux:

```sh
sudo systemctl disable --now waterforce-linux
sudo systemd-inhibit --what=shutdown:sleep --mode=block \
  --why='WATERFORCE firmware update' \
  python3.11 -u -m waterforce_linux firmware flash \
  --pkg /path/to/firmware.pkg \
  --confirm FLASH-0414:7a5e-F1.2-TO-F2.0
```

The last argument is a deliberate opt-in, not a checksum. The tool validates the
package itself. It waits six minutes after transfer before polling the version;
it may still read1.2 initially. On the tested device it subsequently read2.0.
Only `VERIFIED firmware F2.0` means the version check succeeded. Confirm screen
operation and cooling separately. No automatic retry follows a partial write.

After verified success:

```sh
sudo python3.11 -m waterforce_linux display-temperature --save
sudo python3.11 -m waterforce_linux monitor --once
sudo systemctl enable --now waterforce-linux
```

If verification fails, preserve logs and device power. Do not blindly reflash or
send guessed reset commands. The project cannot guarantee recovery of a failed
controller. On a successful upgrade, the F2.0-aware telemetry client is required:
a pre-upgrade client can send incorrect temperatures, affecting display/curves.
