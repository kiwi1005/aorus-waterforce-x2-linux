#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin=${WATERFORCE_PYTHON:-$(command -v python3.11 || command -v python3)}
"$python_bin" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
for svc in waterforce-monitor rigdeck coolercontrold; do
    if systemctl is-active --quiet "$svc"; then
        echo "Stop conflicting $svc before installation." >&2
        exit 1
    fi
done
getent group waterforce-linux >/dev/null || groupadd --system waterforce-linux
id waterforce-linux >/dev/null 2>&1 || useradd --system --gid waterforce-linux --no-create-home --home-dir /nonexistent --shell /sbin/nologin waterforce-linux
systemctl stop waterforce-linux 2>/dev/null || true
install -d -m 755 /opt/waterforce-linux/waterforce_linux
install -m 644 "$project_dir"/waterforce_linux/*.py /opt/waterforce-linux/waterforce_linux/
install -m 644 "$project_dir/LICENSE" "$project_dir/NOTICE.md" /opt/waterforce-linux/
sed "s|@PYTHON@|$python_bin|g" "$project_dir/packaging/waterforce-linux.service" > /etc/systemd/system/waterforce-linux.service
install -m 644 "$project_dir/packaging/71-waterforce-linux.rules" /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=hidraw
systemctl daemon-reload
systemctl enable --now waterforce-linux
systemctl --no-pager status waterforce-linux
