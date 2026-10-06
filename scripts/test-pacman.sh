#!/usr/bin/env bash
# Test actual signed transactions in an extracted, disposable Hafthi OS root.
set -euo pipefail
if (( EUID != 0 )); then echo 'Run in the isolated Arch CI container as root.' >&2; exit 1; fi
iso=${1:?Supply an existing Hafthi OS ISO}
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
temporary=$(mktemp -d /var/tmp/hafthios-pacman.XXXXXX)
root="$temporary/root"
cleanup() {
    if mountpoint -q "$root"; then umount -R "$root"; fi
    rm -rf -- "$temporary"
}
trap cleanup EXIT
xorriso -osirrox on -indev "$iso" -extract /arch/x86_64/airootfs.sfs "$temporary/airootfs.sfs"
unsquashfs -no-progress -d "$root" "$temporary/airootfs.sfs"
mount --bind "$root" "$root"
[[ -f "$root/usr/local/bin/hafthios-install" && -f "$root/usr/share/doc/hafthios/file-guide.json" ]]
# Apply only the pending package configuration; do not use the host's keyring.
cp "$project/live/etc/pacman.d/mirrorlist" "$root/etc/pacman.d/mirrorlist"
rm -rf -- "$root/etc/pacman.d/gnupg"
rm -f -- "$root/etc/resolv.conf"
cp /etc/resolv.conf "$root/etc/resolv.conf"
# Execute the exact key initialization commands shipped in the boot service.
while IFS= read -r command; do
    arch-chroot "$root" /bin/bash -euc "$command"
done < <(sed -n 's/^ExecStart=//p' "$project/live/etc/systemd/system/hafthios-package-keys.service")
arch-chroot "$root" /bin/bash -euc '
    test -f /etc/pacman.d/gnupg/hafthios-ready
    pacman-conf SigLevel | grep -qx PackageRequired
    pacman-conf SigLevel | grep -qx PackageTrustedOnly
    pacman -Syu --noconfirm --needed git base-devel
    pacman -Q git base-devel
    git --version
    make --version
    # A second signed transaction with the persisted keyring verifies reuse.
    pacman -S --noconfirm git
    git --version
'
echo 'HAFTHIOS_PACMAN_INSTALL_OK: signed git/base-devel install and git reinstall succeeded in the extracted OS root'
