#!/usr/bin/env bash
set -euo pipefail
# Fail the image build if either repository has no usable runtime server.
for repository in core extra; do
    servers=$(pacman-conf --repo "$repository" Server)
    [[ "$servers" == https://* ]] || { echo "No HTTPS mirror configured for $repository" >&2; exit 1; }
done
useradd --create-home --uid 1000 --user-group --groups wheel,uucp,audio,video --shell /bin/bash hafthi
passwd -d hafthi
chown -R hafthi:hafthi /home/hafthi
niri validate --config /etc/niri/config.kdl

printf "en_US.UTF-8 UTF-8\nsv_SE.UTF-8 UTF-8\n" > /etc/locale.gen
locale-gen
python3 - <<'PYTHON'
import pathlib, runpy, tempfile
settings = runpy.run_path('/usr/local/bin/hafthios-settings')
with tempfile.TemporaryDirectory() as temporary:
    for language, keyboard in [('en', 'us'), ('sv', 'se'), ('en', 'se')]:
        settings['apply_settings'](language, keyboard, pathlib.Path(temporary))
PYTHON
