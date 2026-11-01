# Attribution and licensing

This project is distributed under GPL-3.0-or-later; see LICENSE.

`waterforce_linux/device.py`, `waterforce_linux/sensors.py`, and media protocol/conversion portions of `waterforce_linux/media.py` are adapted from
[gabriellaines/rigdeck](https://github.com/gabriellaines/rigdeck), commit
`b9a89b3d8a141922c54b4ba6de3eaae1bcf980e6`, distributed under GPL-3.0-or-later.
Credit belongs to RigDeck's contributors for their original Linux HID transport,
CPU sensor discovery and WATERFORCE X II protocol work. This project is independent
and is not an official RigDeck or GIGABYTE release.

Changes include a reduced hardware interface, exclusive advisory device locking,
short-write detection, bounded input draining, CPU load accounting, a strict
sensor reader, firmware-aware telemetry, and a standalone firmware updater.

The F2.0 packet layout and update sequence were established through static analysis
of user-supplied vendor applications for interoperability, then tested on a
WATERFORCE X II 240. Vendor applications, resources, DLLs, firmware, artwork and
extracted/disassembled code are not included or licensed by this project.
Protocol descriptions and the Python implementation are provided instead.

GIGABYTE and AORUS are trademarks of their respective owners. This project is
not affiliated with or endorsed by GIGABYTE.
