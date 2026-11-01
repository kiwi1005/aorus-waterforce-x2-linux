# Pictures and animations

The X II's custom animation mode plays **320×320, 25 fps, H.264 Main@3.1,
yuv420p, no B-frames, in Matroska**. This tool converts still pictures into a
short stationary video in the same mode; it does not use the separate vendor
JPEG gallery. Inputs: PNG, JPEG, WebP, BMP, GIF, MP4, MKV, MOV and WebM.

Install FFmpeg with `libx264` and `ffprobe` on PATH, plus the normal project
requirements. FFmpeg binaries are not bundled. The default fit preserves the
whole picture with black padding; `--fit crop` fills the square by cropping.
Clips are limited to 10 seconds by default; `--duration 30` raises that limit
(up to 60). Short animations keep their original duration and loop on-device.

From the repository directory:

```sh
# Convert and inspect the result on your computer, without accessing USB:
python3.11 -m waterforce_linux media prepare photo.png preview.mkv

# List stored media:
sudo python3.11 -m waterforce_linux media --manage-service list

# Upload a picture and show it:
sudo python3.11 -m waterforce_linux media --manage-service upload photo.png --name photo.mkv --play

# Upload a GIF or movie:
sudo python3.11 -m waterforce_linux media --manage-service upload animation.gif --name animation.mkv --play

# Reuse a previously prepared file:
sudo python3.11 -m waterforce_linux media --manage-service upload preview.mkv --encoded --name preview.mkv --play

# Switch without reuploading:
sudo python3.11 -m waterforce_linux media --manage-service play photo.mkv

# Return to live CPU temperature:
sudo python3.11 -m waterforce_linux media --manage-service temperature
```

`--manage-service` requires root and temporarily stops active `waterforce-linux`
or `waterforce-monitor` services, restoring them afterward even on ordinary
errors. Conversion happens before stopping the service. Other clients such as
RigDeck/CoolerControl must be stopped separately. This option does not start a
service that was previously inactive. Playback and returning to temperature always apply/save settings once. On the
tested F2.0 unit, readback changed but the visible screen stayed unchanged until
this step. Upload without `--play` only stores the file.

Existing filenames are refused (case-insensitive), and existing files are never
deleted or reordered. Choose a new `.mkv` name, at most 64 UTF-8 bytes. Uploads
check free space, stop on write failure, and require the new name to appear in
the directory before switching playback. Directory and playback readback are
not a content checksum or proof that the LCD decoded the file correctly.

## Hardware validation

On X II 240 F2.0, a 2,960-byte stationary blue/yellow test image and a
441,710-byte moving test clip were uploaded and appeared in the directory.
Playback mode and selected index matched readback, the original
`Aorus_Opening_video.mkv` remained present, and the temperature service resumed.
The user confirmed both the moving animation and the correct stationary
blue/yellow picture after Apply/Save. Returning to CPU temperature also passed
settings readback; mode selection must precede per-mode display-field updates.
Other models and power-cycle persistence are untested.

## Protocol

The transport and conversion derive from RigDeck (see [NOTICE](../NOTICE.md)),
with checks against the Windows Cooler module's media API:

- `F3 02` prepares the media listing; `F4 02` returns count and `F5 02 index`
  returns each filename.
- `F1 01 size_be32 name_length_including_NUL name` starts a transfer.
- `F2 marker data` carries 6,141 bytes per full report (`marker=FD`); the last
  partial report uses its length modulo 256. Reports are padded by the transport.
- `F1 02 size_be32` commits animation media. The directory is polled afterward.
- `F6 07 interval position` selects a one-based position in the current list.
- `FB interval 07` selects the custom-animation-only mode loop; `E7 07 00`
  activates it. `FD 07` reads playback selection and `E8` reads screen mode.
- `B6` applies/saves playback settings after readback passes; required for visible
  playback changes on the tested F2.0 device.

All command bytes above exclude the leading HID report ID `99`.
No firmware update commands are used for media operations.
