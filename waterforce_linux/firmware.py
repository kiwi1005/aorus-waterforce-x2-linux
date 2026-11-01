#!/usr/bin/env python3
"""Linux port of the supplied updater protocol. Python 3.9+, stdlib only.
No firmware bundled. Default commands never send firmware/reset commands.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import time

SIZE = 6144
PKG_HASH = 'bd7ed3d4a9313821f69b9a2cec94e061124bf8ba9e1e655021a08377f8a263d5'
PKG_NAME = b'GP-AORUS WATERFORCE X II F2.0.PKG'
DESCRIPTOR = bytes.fromhex('05000902a101859905000902a1000900150025ff750896ff0081020900150025ff750896ff179102c0c0')


def validate(path):
    data = Path(path).read_bytes()
    if len(data) != 11447615 or hashlib.sha256(data).hexdigest() != PKG_HASH:
        raise ValueError('Not the exact F2.0 PKG extracted from the supplied updater')
    return data


def reports(data):
    """Match original buffer reuse, including final-block trailing bytes."""
    size = len(data).to_bytes(4, 'big')
    begin = b'\x99\xa2\x01' + size + bytes([len(PKG_NAME)+1]) + PKG_NAME + b'\0'
    yield begin.ljust(SIZE, b'\0'), .010
    block = bytearray(SIZE)
    block[:2] = b'\x99\xa0'
    for offset in range(0, len(data), SIZE-2):
        part = data[offset:offset+SIZE-2]
        block[2:2+len(part)] = part
        yield bytes(block), .001
    yield (b'\x99\xa2\x00'+size).ljust(SIZE,b'\0'), .010
    yield b'\x99\xe7\x01\x00'.ljust(SIZE,b'\0'), 0
    yield b'\x99\xa1'.ljust(SIZE,b'\0'), 0


def discover():
    matches=[]
    for p in Path('/sys/class/hidraw').glob('hidraw*'):
        meta=(p/'device/uevent').read_text()
        if 'HID_ID=0003:00000414:00007A5E' in meta:
            if (p/'device/report_descriptor').read_bytes()!=DESCRIPTOR:
                raise RuntimeError('Unverified HID descriptor; refusing access')
            matches.append('/dev/'+p.name)
    if len(matches)!=1:
        raise RuntimeError(f'Expected exactly one matching cooler, found {len(matches)}')
    return matches[0]


class Device:
    def __init__(self):
        self.path=discover()
        self.fd=os.open(self.path,os.O_RDWR|os.O_NONBLOCK)
        try: fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:
            os.close(self.fd)
            raise
    def close(self):
        os.close(self.fd)
    def write(self,report):
        if len(report)!=SIZE: raise ValueError('Invalid report size')
        if os.write(self.fd,report)!=SIZE:
            raise IOError('Short HID write; transfer stopped, never retried')
    def query(self,command):
        deadline=time.monotonic()+2
        while select.select([self.fd],[],[],0)[0]:
            os.read(self.fd,256)
            if time.monotonic()>deadline: raise TimeoutError('Device input never drained')
        self.write(bytes([0x99,command]).ljust(SIZE,b'\0'))
        while time.monotonic()<deadline:
            if select.select([self.fd],[],[],max(0,deadline-time.monotonic()))[0]:
                r=os.read(self.fd,256)
                if len(r)>=4 and r[:2]==bytes([0x99,command]): return r
        raise TimeoutError(f'No response to {command:02x}')
    def version(self):
        r=self.query(0xd6)
        return tuple(r[2:4])
    def info(self):
        model=self.query(0xde)[2]
        if model!=0: raise RuntimeError('This firmware updater is restricted to the verified X II 240')
        return {'device':self.path,'model':'WATERFORCE X II 240','firmware':self.version()}


def require_idle():
    for service in ('waterforce-linux','waterforce-monitor','rigdeck','coolercontrold'):
        r=subprocess.run(['systemctl','is-active',service],capture_output=True,text=True)
        if r.stdout.strip() in ('active','activating','reloading'):
            raise RuntimeError(f'Stop {service} before exclusive access')
    path=discover()
    r=subprocess.run(['fuser',path],capture_output=True,text=True)
    if r.returncode!=1:
        raise RuntimeError('Device is in use or ownership check failed: '+r.stdout.strip())


def flash(data,confirm):
    if confirm!='FLASH-0414:7a5e-F1.2-TO-F2.0':
        raise ValueError('Explicit confirmation token required')
    if os.geteuid()!=0: raise RuntimeError('Flash requires root for owner checks')
    require_idle()
    d=Device()
    try:
        info=d.info()
        if info['firmware']!=(1,2): raise RuntimeError('Only the F1.2 -> F2.0 path is supported')
        print(json.dumps(info),flush=True)
        print('Starting irreversible transfer; do not interrupt power. No automatic retries.',flush=True)
        for i,(report,delay) in enumerate(reports(data)):
            d.write(report)
            if delay: time.sleep(delay)
            if i%100==0: print(f'Transmitted reports: {i+1}',flush=True)
    finally: d.close()
    print('Transfer complete, NOT yet verified. Waiting 360 seconds as original F1.2 path.',flush=True)
    time.sleep(360)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            d=Device()
            try: info=d.info()
            finally: d.close()
            print('Version readback: '+str(info['firmware']),flush=True)
            if info['firmware']==(2,0):
                print('VERIFIED firmware F2.0. LCD appearance still requires visual confirmation.',flush=True)
                print('Restart a telemetry client with F2.0 packet support, then verify LCD temperature.',flush=True)
                return
        except (OSError,RuntimeError,TimeoutError): pass
        time.sleep(6)
    raise RuntimeError('UNVERIFIED: no F2.0 readback. Do not blindly retry flash or cut power.')


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['plan','probe','flash'])
    ap.add_argument('--pkg')
    ap.add_argument('--confirm',default='')
    a=ap.parse_args(argv)
    if a.command=='probe':
        require_idle()
        d=Device()
        try: print(json.dumps(d.info()))
        finally: d.close()
        return
    if not a.pkg: ap.error('--pkg is required')
    data=validate(a.pkg)
    if a.command=='plan':
        packets=list(reports(data))
        print(json.dumps({'pkg_sha256':PKG_HASH,'bytes':len(data),'reports':len(packets),
                          'report_size':SIZE,'wire_sha256':hashlib.sha256(b''.join(p for p,_ in packets)).hexdigest(),
                          'old_firmware':'1.2','target':'2.0','minimum_post_reset_wait_seconds':360,
                          'hardware_access':False},indent=2))
    else: flash(data,a.confirm)


if __name__=='__main__':
    try: main()
    except Exception as exc:
        raise SystemExit(f'FAILED: {exc}')
