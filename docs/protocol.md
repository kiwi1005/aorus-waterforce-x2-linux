# Protocol and evidence

## Sources

- [RigDeck protocol notes](https://github.com/gabriellaines/rigdeck/blob/b9a89b3d8a141922c54b4ba6de3eaae1bcf980e6/docs/protocols/aorus-waterforce-x2.md).
- Static analysis of the user-supplied `AORUS_WATERFORCE_X_II_240_360_360I_F2.0_SOP.exe`
  (.NET updater version 24.6.1.1) and GCC 26.09.10.01's Cooler 26.08.24.01 module.
- Hardware tests on one WATERFORCE X II 240, USB `0414:7a5e`, F1.2 → F2.0.

The managed metadata/resources were inspected with dnfile and CIL instructions
with dncil. No vendor Windows executable was run on Linux. The updater's
`LcdApi.BenginFlash` (original spelling) establishes the update sequence;
`AorusLcdService.CoolerDataApi.SendCoolerData47A5EElite` establishes the F2 packet.
The vendor binaries/disassembly are not distributed here.

## HID framing

6144-byte output reports, padded to length, leading report ID `99`. Input reports
are 256 bytes. Responses echo `99` and the command. F2 does not change the HID
report descriptor. `D6` reads firmware, `DE` model, `DA` fan/pump RPM.
The updater checks the exact descriptor before opening a matching device.

## Telemetry, firmware 1.x

Offsets include the leading `99`:

| Offset | Meaning |
|---|---|
| 0–1 | `99 E0` |
| 2 | CPU vendor: 0 AMD, 1 Intel |
| 3 | CPU temperature, integer °C |
| 4 | Thread count |
| 5–6 | CPU GHz integer, decimal tenth |
| 7 | Core count |
| 8–9 | VRAM and liquid temperature |
| 10 | CPU utilization |
| 11–12 | CPU power, little endian |

## Telemetry, firmware 2.x

The Windows code selects this layout for firmware >=2.0. The report body is
24 bytes before padding; unspecified bytes are zero.

| Offset | Meaning |
|---|---|
| 0–1 | `99 E0` |
| 4 | CPU temperature, integer °C |
| 6–7 | CPU GHz integer, decimal tenth |
| 11 | CPU utilization |
| 12–13 | CPU power, big endian |
| 14 | DRAM utilization |
| 15 | GPU temperature |
| 16–17 | GPU GHz integer, decimal tenth |
| 18 | GPU utilization |
| 19–20 | GPU power, big endian |
| 21 | GPU VRAM utilization |
| 22–23 | GPU fan RPM, big endian |

Only CPU temperature, clock and utilization are supplied by this daemon. In the
old packet offset4 contained thread count: that explains a fixed16°C on a
16-thread CPU after upgrading. A synthetic packet test verifies that temperature
is now at offset4. Real screen temperature changes were confirmed under load.

## Display selection

`E7 (mode+1) param` sets screen; `E8` reads it. Wire mode1 is the first built-in
screen. `E2` sets four groups of display flags; `DF` reads them. F1 uses6 flags
per group, F2 uses13. CPU temperature is bit3 in either layout. The public CLI
uses the firmware-dependent width and preserves groups2–4.

`AC 00` selects Celsius. `B6` applies/saves settings; media playback and presets
require this step on the tested F2.0 unit. Normal telemetry never calls save.
See [media commands](media.md) and [presets](presets.md).

`E4 mode R1 G1 B1 ... R4 G4 B4` sets native text-zone colors. `AA` sets
rotation intervals. Mode 2 enables its CPU-name text field with `AE 01`; `E1`
sends the length-prefixed ASCII label. The network preset reuses this text field.

## Firmware transfer

The exact tested package is pinned by size and SHA256; see firmware.md.

1. `99 A2 01 sizeBE32 nameLen+1 filename NUL`, padded to6144.
2. Wait10ms. Send `99 A0` plus6142 firmware bytes per report; wait1ms each.
3. The original reuses the previous buffer for a final partial block. The port
   reproduces its tail bytes; declared package length determines meaningful data.
4. `99 A2 00 sizeBE32`, wait10ms.
5. `99 E7 01 00`, then `99 A1` reset.
6. For F1.2, wait360sec before version checks. The port retries queries every6sec
   for up to180sec and requires exact2.0. No transfer retries or success claims
   based solely on successful USB writes.

## Validation boundary

The exact update completed once on real hardware and firmware readback became
2.0 about409sec after transfer finished. The user confirmed the screen lit.
After correcting telemetry, the LCD followed CPU load/temperature. The runtime
service restarted successfully. A cold boot remains untested; other devices,
firmware images, firmware recovery and RGB remain untested. Custom media has
separate validation described in [the media guide](media.md).
