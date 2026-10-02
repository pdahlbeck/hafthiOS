#!/usr/bin/env bash
set -euo pipefail
useradd --create-home --uid 1000 --user-group --groups wheel,uucp,audio,video --shell /bin/bash hafthi
passwd -d hafthi
chown -R hafthi:hafthi /home/hafthi
niri validate --config /etc/niri/config.kdl
