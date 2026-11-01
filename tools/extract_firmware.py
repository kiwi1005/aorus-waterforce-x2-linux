#!/usr/bin/env python3
"""Extract the tested PKG from a user-supplied vendor EXE without executing it.
Requires optional dnfile, installed into an isolated analysis environment.
"""
import argparse
import hashlib
from pathlib import Path
import sys

EXE_SHA256 = '48a2818cdd9a072497d4b623680eae93bb584232986c55ef3e24d835a4a85bfb'
PKG_SHA256 = 'bd7ed3d4a9313821f69b9a2cec94e061124bf8ba9e1e655021a08377f8a263d5'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    if hashlib.sha256(args.exe.read_bytes()).hexdigest() != EXE_SHA256:
        ap.error('EXE does not match the tested input; no extraction performed')
    import dnfile
    pe = dnfile.dnPE(str(args.exe))
    for resource in pe.net.resources:
        for entry in getattr(resource.data, 'entries', []):
            if isinstance(entry.value, bytes) and hashlib.sha256(entry.value).hexdigest() == PKG_SHA256:
                with args.output.open('xb') as out:
                    out.write(entry.value)
                print(f'Extracted verified package: {args.output}')
                return
    sys.exit('Expected package not found')


if __name__ == '__main__':
    main()
