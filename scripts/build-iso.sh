#!/usr/bin/env bash
set -euo pipefail
if (( EUID != 0 )); then echo 'Run this build script as root on Arch Linux.' >&2; exit 1; fi
command -v mkarchiso >/dev/null
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
workspace=$(mktemp -d /var/tmp/hafthios-build.XXXXXX)
trap 'rm -rf -- "$workspace"' EXIT
profile="$workspace/profile"
cp -a /usr/share/archiso/configs/baseline "$profile"
cp -a "$root/live/." "$profile/airootfs/"
python3 "$root/scripts/build-guide.py" "$profile/airootfs/usr/share/doc/hafthios"
# Copy the current baseline boot files; adjust only image branding/compression.
cat >> "$profile/profiledef.sh" <<'PROFILE'
iso_name="hafthios-prototype"
iso_label="HAFTHIOS"
iso_publisher="Hafþi OS <https://github.com/pdahlbeck/hafthiOS>"
iso_application="Hafþi OS graphical installer prototype"
airootfs_image_type="squashfs"
airootfs_image_tool_options=(-comp xz -b 1M)
file_permissions+=(
  ["/usr/local/bin/hafthios-session"]="0:0:755"
  ["/usr/local/bin/hafthios-welcome"]="0:0:755"
)
PROFILE
cat > "$profile/packages.x86_64" <<'PACKAGES'
base
linux
mkinitcpio
mkinitcpio-archiso
syslinux
cage
foot
gtk4
python
python-gobject
mesa
networkmanager
polkit
ttf-dejavu
PACKAGES
# Use the normal Arch repositories and their signature checks from the baseline.
mkdir -p "$profile/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sf /usr/lib/systemd/system/NetworkManager.service "$profile/airootfs/etc/systemd/system/multi-user.target.wants/NetworkManager.service"
mkdir -p "$root/out"
mkarchiso -v -w "$workspace/work" -o "$root/out" "$profile"
python3 - "$root/out" <<'PY'
import hashlib, pathlib, sys
out = pathlib.Path(sys.argv[1])
iso = max(out.glob('*.iso'), key=lambda p: p.stat().st_mtime)
size = iso.stat().st_size
with iso.open('rb') as f:
    checksum = hashlib.file_digest(f, 'sha256').hexdigest()
iso.with_suffix('.iso.sha256').write_text(f'{checksum}  {iso.name}\n')
report = f'ISO: {iso.name}\nBytes: {size}\nFits a 1 GB USB: {"yes" if size < 1_000_000_000 else "no"}\n'
(out / 'size.txt').write_text(report)
print(report)
PY
