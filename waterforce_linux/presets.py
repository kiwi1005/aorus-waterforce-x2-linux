# SPDX-License-Identifier: GPL-3.0-or-later
"""Native LCD presets. Live network labels reuse the CPU-name text field."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

CONFIG = Path('/etc/waterforce-linux/preset.json')
# Display mask bits: fan, pump, CPU clock, CPU temperature, CPU usage.
PRESETS = {
    'temperature': {'title': 'CPU 溫度大字', 'mode': 1, 'zones': [8, 0, 0, 0]},
    'frequency': {'title': 'CPU 頻率大字', 'mode': 1, 'zones': [4, 0, 0, 0]},
    'temp-clock': {'title': '溫度＋頻率', 'mode': 4, 'zones': [8, 4, 0, 0]},
    'dashboard': {'title': '溫度／頻率／使用率／風扇', 'mode': 4, 'zones': [8, 4, 16, 1]},
    'cooling': {'title': '溫度／風扇與水泵輪播／頻率', 'mode': 3, 'zones': [8, 3, 4, 0]},
    'network': {'title': '本機 IPv4＋溫度與頻率輪播', 'mode': 2, 'zones': [12, 0, 0, 0]},
}
COLORS = bytes.fromhex('ffb347 45d9ff b5ff70 ffffff')


def local_ip(interface=None):
    """Read the kernel's chosen IPv4 source; no packets sent to the lookup target."""
    if interface:
        if not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,15}', interface) or interface.startswith('-'):
            raise ValueError('Invalid interface name')
        command = ['ip', '-j', '-4', 'address', 'show', 'dev', interface]
    else:
        command = ['ip', '-j', '-4', 'route', 'get', '1.1.1.1']
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        if result.returncode:
            return None
        rows = json.loads(result.stdout)
        candidates = ([a.get('local') for r in rows for a in r.get('addr_info', []) if a.get('scope') == 'global']
                      if interface else [r.get('prefsrc') or r.get('src') for r in rows])
        for value in candidates:
            if value:
                address = ipaddress.ip_address(value)
                if address.version == 4 and not address.is_loopback and not address.is_unspecified:
                    return str(address)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
        return None
    return None


def read_config(path=CONFIG):
    try:
        config = json.loads(Path(path).read_text())
        if not isinstance(config, dict) or config.get('preset') not in PRESETS:
            return {}
        interface = config.get('interface')
        if interface is not None and (not isinstance(interface, str) or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,15}', interface) or interface.startswith('-')):
            return {}
        return config
    except (OSError, ValueError):
        return {}


def live_label(config):
    from .sensors import cpu_name
    if config.get('preset') == 'network':
        address = local_ip(config.get('interface'))
        return 'IP ' + address if address else 'IP OFFLINE'
    return cpu_name()


def write_config(config, path=CONFIG):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.preset-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(config, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def apply(c, name, label=None):
    preset = PRESETS[name]
    firmware = tuple(map(int, c.firmware().split('.')))
    width = 13 if firmware >= (2, 0) else 6
    mode = preset['mode']
    before = c.modes()
    c.send(bytes([0xfb, 10, mode]))
    c.send(bytes([0xe7, mode, 0]))
    time.sleep(.2)
    flags = bytes((mask >> bit) & 1 for mask in preset['zones'] for bit in range(width))
    c.send(b'\xe2' + flags)
    c.send(bytes([0xe4, mode]) + COLORS)
    c.send(b'\xaa\x03\x03\x03')  # 3 seconds per selected item in rotating zones
    c.send(b'\xac\x00')
    if mode == 2:
        c.send(b'\xae\x01')
        c.send_cpu_name(label or 'IP OFFLINE')
    time.sleep(.2)
    if c.screen_mode() != mode or c.query(b'\xdf')[2:2+len(flags)] != flags:
        raise RuntimeError('Preset readback failed; settings were not saved')
    if c.modes() != before:
        raise RuntimeError('Cooling modes unexpectedly changed; settings were not saved')
    c.save()
    time.sleep(.3)
    return {'preset': name, 'title': preset['title'], 'mode': mode, 'saved': True,
            'cooling_modes_unchanged': c.modes() == before}


def main(argv=None):
    from .media import idle_device
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manage-service', action='store_true')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('list', help='list presets without opening USB')
    sub.add_parser('choose', help='interactive numbered preset menu')
    sub.add_parser('current', help='show saved preset preference and current network label, without USB')
    choose = sub.add_parser('apply')
    choose.add_argument('name', choices=PRESETS)
    choose.add_argument('--interface', help='network preset: choose a specific interface instead of the default route')
    args = p.parse_args(argv)
    if args.action == 'list':
        for name, preset in PRESETS.items():
            print(f'{name:14s} {preset["title"]}')
        return
    if args.action == 'current':
        config = read_config()
        print(json.dumps({'preference': config, 'label': live_label(config)}, ensure_ascii=False))
        return
    if args.action == 'choose':
        if not sys.stdin.isatty():
            p.error('choose needs an interactive terminal; use apply NAME in scripts')
        names = list(PRESETS)
        for i, name in enumerate(names, 1):
            print(f'{i}. {PRESETS[name]["title"]} ({name})')
        answer = input('選擇預設 / Choose 1–6 (Enter to cancel): ').strip()
        if not answer:
            return
        if not answer.isdigit() or not 1 <= int(answer) <= len(names):
            p.error('Invalid selection')
        args.name, args.interface = names[int(answer)-1], None
    if os.geteuid() != 0:
        p.error('Applying a preset requires root to write /etc/waterforce-linux/preset.json')
    if args.interface and args.name != 'network':
        p.error('--interface is only valid for network')
    config = {'preset': args.name, 'interface': args.interface}
    label = live_label(config)  # validate interface before touching the device
    with idle_device(args.manage_service) as c:
        result = apply(c, args.name, label)
        write_config(config)
    print(json.dumps(result, ensure_ascii=False))
