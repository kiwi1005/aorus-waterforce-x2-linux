# SPDX-License-Identifier: GPL-3.0-or-later
"""Local image/video conversion and X II media transfer (adapted from RigDeck)."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .device import CHUNK, Cooler
from .firmware import require_idle

MAX_BYTES = 32 * 1024 * 1024


def validate_name(name):
    if (not name or name in ('.', '..') or any(ord(c) < 32 or c in '/\\:' for c in name)
            or len(name.encode('utf-8')) > 64 or not name.lower().endswith('.mkv')):
        raise ValueError('Use a filename ending in .mkv, at most 64 UTF-8 bytes, without paths/control characters')
    return name


def run_media_tool(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:] or 'Media tool failed')
    return result.stdout


def prepare(source, output, duration=10, fit='contain'):
    source = Path(source).expanduser().resolve(strict=True)
    output = Path(output).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.mp4', '.mkv', '.mov', '.webm'):
        raise ValueError('Expected a local PNG/JPEG/WebP/BMP/GIF/MP4/MKV/MOV/WebM file')
    if not 1 <= duration <= 60:
        raise ValueError('Duration must be 1–60 seconds')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not shutil.which('ffprobe'):
        raise RuntimeError('Install ffmpeg (with libx264) and ffprobe and put them on PATH')
    # Restrict input protocols: local media must not fetch referenced network resources.
    args = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-protocol_whitelist', 'file,pipe']
    if source.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
        args += ['-loop', '1']
    if fit == 'contain':
        vf = 'scale=320:320:force_original_aspect_ratio=decrease,pad=320:320:(ow-iw)/2:(oh-ih)/2:black'
    elif fit == 'crop':
        vf = "crop='min(iw,ih)':'min(iw,ih)',scale=320:320:flags=lanczos"
    else:
        raise ValueError('fit must be contain or crop')
    args += ['-i', str(source), '-t', str(duration), '-map', '0:v:0', '-vf',
             vf + ',setsar=1,fps=25,format=yuv420p', '-an', '-sn', '-dn', '-map_metadata', '-1',
             '-c:v', 'libx264', '-threads', '2', '-profile:v', 'main', '-level', '3.1',
             '-b:v', '1000k', '-bf', '0', '-f', 'matroska', str(output)]
    run_media_tool(args)
    validate_encoded(output)


def validate_encoded(path):
    path = Path(path).resolve(strict=True)
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('Encoded media must be 1 byte–32 MiB')
    probe = shutil.which('ffprobe')
    if not probe:
        raise RuntimeError('ffprobe is required')
    data = json.loads(run_media_tool([probe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                     '-show_streams', '-show_format', '-of', 'json', str(path)]))
    streams = data.get('streams', [])
    if len(streams) != 1:
        raise ValueError('Expected one video stream without audio')
    v = streams[0]
    if (v.get('codec_name') != 'h264' or v.get('width') != 320 or v.get('height') != 320
            or v.get('has_b_frames') != 0 or v.get('pix_fmt') != 'yuv420p'
            or v.get('profile') != 'Main' or v.get('level') != 31
            or v.get('r_frame_rate') != '25/1'
            or 'matroska' not in data.get('format', {}).get('format_name', '')
            or not 0 < float(data.get('format', {}).get('duration', 0)) <= 60.1):
        raise ValueError('Expected 320x320/25fps Main@3.1 H.264 MKV, yuv420p, no B-frames, duration <=60s')
    return path.read_bytes()


def list_media(c):
    c.send(b'\xf3\x02')
    time.sleep(.5)
    count = c.query(b'\xf4\x02', match=2)[3]
    if count > 250:
        raise RuntimeError('Invalid media count')
    return [c.query(bytes([0xf5, 2, i]), match=3)[6:].split(b'\0', 1)[0].decode('utf-8')
            for i in range(count)]


def upload(c, data, name, timeout=30):
    validate_name(name)
    if not 0 < len(data) <= MAX_BYTES:
        raise ValueError('Invalid media size')
    before = list_media(c)
    if any(n.casefold() == name.casefold() for n in before):
        raise ValueError('That filename already exists; choose a different name')
    if len(before) >= 250 or len(data) + 65536 > c.storage_free_kb() * 1024:
        raise ValueError('Not enough storage on cooler')
    size = len(data).to_bytes(4, 'big')
    encoded = name.encode('utf-8')
    c.send(b'\xf1\x01' + size + bytes([len(encoded) + 1]) + encoded)
    time.sleep(.01)
    for off in range(0, len(data), CHUNK):
        part = data[off:off+CHUNK]
        c.send(bytes([0xf2, 0xfd if len(part) == CHUNK else len(part) & 255]) + part)
        time.sleep(.003)
    c.send(b'\xf1\x02' + size)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(.5)
        after = list_media(c)
        if name in after:
            if any(n not in after for n in before):
                raise RuntimeError('Existing media list changed unexpectedly')
            return after
    raise TimeoutError('Upload not confirmed in directory; playback was not changed')


def play(c, name):
    names = list_media(c)
    if name not in names:
        raise ValueError('Filename not found on cooler')
    position = names.index(name) + 1
    # Select a position in the existing order; never rewrite order or delete files.
    c.send(bytes([0xf6, 7, 10, position]))
    time.sleep(.1)
    c.send(b'\xfb\x0a\x07')  # screen-mode loop contains only Custom GIF
    c.send(b'\xe7\x07\x00')
    time.sleep(.2)
    selection = c.query(b'\xfd\x07', match=2)
    if c.screen_mode() != 7 or selection[4] != position or selection[5] != 0:
        raise RuntimeError('Playback settings readback mismatch')
    # F2.0 can report staged settings without displaying them until Apply/Save.
    c.save()
    time.sleep(.5)


@contextmanager
def idle_device(manage_service):
    stopped = []
    try:
        if manage_service:
            if os.geteuid() != 0:
                raise PermissionError('--manage-service requires root')
            for service in ('waterforce-monitor', 'waterforce-linux'):
                if subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0:
                    # Register first so an interrupted stop also attempts restoration.
                    stopped.append(service)
                    subprocess.run(['systemctl', 'stop', service], check=True, timeout=30)
        require_idle()
        with Cooler() as c:
            yield c
    finally:
        for service in reversed(stopped):
            subprocess.run(['systemctl', 'start', service], check=True, timeout=30)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manage-service', action='store_true', help='root: temporarily stop/resume active temperature service')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    temp = sub.add_parser('temperature', help='return to live CPU temperature')
    convert = sub.add_parser('prepare', help='offline conversion, no USB access')
    convert.add_argument('source')
    convert.add_argument('output')
    send = sub.add_parser('upload', help='convert and upload, preserving existing files')
    send.add_argument('source')
    send.add_argument('--name', required=True)
    send.add_argument('--encoded', action='store_true', help='already prepared MKV; validate without conversion')
    send.add_argument('--play', action='store_true')
    for cmd in (convert, send):
        cmd.add_argument('--duration', type=float, default=10, help='maximum seconds, default 10, max 60')
        cmd.add_argument('--fit', choices=['contain', 'crop'], default='contain')
    show = sub.add_parser('play')
    show.add_argument('name')
    args = p.parse_args(argv)
    if args.action == 'prepare':
        prepare(args.source, args.output, args.duration, args.fit)
        print(json.dumps({'prepared': str(args.output)}))
        return
    if args.action == 'upload':
        validate_name(args.name)
        # Conversion completes before pausing the temperature service.
        if args.encoded:
            data = validate_encoded(args.source)
        else:
            with tempfile.TemporaryDirectory(prefix='waterforce-media-') as temp:
                output = Path(temp) / 'prepared.mkv'
                prepare(args.source, output, args.duration, args.fit)
                data = validate_encoded(output)
    with idle_device(args.manage_service) as c:
        if args.action == 'list':
            result = {'files': list_media(c), 'free_kb': c.storage_free_kb(), 'mode': c.screen_mode()}
        elif args.action == 'temperature':
            from .__main__ import display_temperature
            result = display_temperature(c, True)
        elif args.action == 'upload':
            files = upload(c, data, args.name)
            if args.play:
                play(c, args.name)
            result = {'uploaded': args.name, 'bytes': len(data), 'playing': args.play, 'files': files}
        else:
            play(c, args.name)
            result = {'playing': args.name, 'saved': True}
    print(json.dumps(result, ensure_ascii=False))
