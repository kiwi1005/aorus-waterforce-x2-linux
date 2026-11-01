"""CLI. Hardware is opened only by explicitly requested commands."""
import argparse
import json
import sys
import time
from . import __version__
from . import firmware, monitor
from .device import Cooler


def display_temperature(cooler, persist=False):
    version = tuple(map(int, cooler.firmware().split('.')))
    width = 13 if version >= (2, 0) else 6
    old = cooler.query(b'\xdf')
    flags = bytearray(old[2:2+width*4])
    if len(flags) != width*4:
        raise ValueError('Truncated display settings')
    flags[:width] = bytes(width)
    flags[3] = 1  # Display4XII(Elite).CPUTemperature = 1 << 3
    cooler.send(b'\xe2' + flags)
    time.sleep(.2)
    cooler.send(b'\xe7\x01\x00')
    cooler.send(b'\xac\x00')  # Celsius
    time.sleep(.2)
    if cooler.query(b'\xdf')[2:2+width*4] != flags:
        raise RuntimeError('Display settings readback mismatch; not saved')
    if cooler.screen_mode() != 1:
        raise RuntimeError('Screen mode readback mismatch; not saved')
    if persist:
        cooler.save()
    return {'firmware': '.'.join(map(str, version)), 'mode': 1,
            'display': 'CPU temperature', 'saved': persist}


def main():
    p = argparse.ArgumentParser(prog='waterforce-linux')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('command', choices=['status', 'monitor', 'display-temperature', 'firmware'])
    args, rest = p.parse_known_args()
    if args.command == 'monitor':
        monitor.main(rest)
    elif args.command == 'firmware':
        firmware.main(rest)
    else:
        sub = argparse.ArgumentParser(prog='waterforce-linux ' + args.command)
        if args.command == 'display-temperature':
            sub.add_argument('--save', action='store_true', help='persist to device flash once')
        opts = sub.parse_args(rest)
        firmware.require_idle()
        with Cooler() as c:
            if args.command == 'display-temperature':
                print(json.dumps(display_temperature(c, opts.save)))
            else:
                print(json.dumps({'model': c.model(), 'firmware': c.firmware(),
                                  'screen_mode': c.screen_mode(),
                                  'fan_rpm_pump_rpm': c.rpm()}))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        sys.exit(f'Error: {exc}')
