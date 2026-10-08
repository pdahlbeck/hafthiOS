# Hafþi OS

A minimal Arch Linux desktop built around Hafþi, Wayland and Chrome.

## Live USB and disk installation

This is an **x86_64 prototype**. Choose **Try the desktop** to use Niri and Hafþi
from the USB, or **Install Hafþi OS** to install the system on a selected disk.
The installer erases the **entire selected disk**; dual boot, disk encryption,
and custom partition layouts are not supported. Back up its contents first.

Only unmounted writable whole disks of at least **12 GiB** are offered. Mounted
partitions, swap, stacked devices and the live boot medium are excluded. Before
installation, review the disk and type the exact **ERASE /dev/...** phrase. The
backend checks the disk identity and current mounts again before writing.

The installer copies the live system offline, creates GPT partitions for BIOS
and UEFI boot, formats an ext4 root filesystem and an EFI system partition, and
installs GRUB. It preserves your live home, language, keyboard and the local file
guide. The account is **hafthi**; choose and repeat your own password. Root is
locked, normal sudo requires your password, and live automatic login is removed.
Restart, remove the USB/ISO, and log in as hafthi to enter Niri.

Google Chrome is downloaded directly from Google on first use. Chrome is not
redistributed inside the ISO. Its normal user sandbox remains enabled. Live
changes disappear on restart; settings on the installed disk persist.

## Offline file guide

The English **Hafþi OS File Guide** opens a complete register of the ISO files. The separate **Project source guide** explains the project files: their purpose, when they are used, connected files and implementation details. Click **Hafþi OS Guide** on the welcome screen or press **F1**. In the project source guide, use **Show source** to read source snapshots matching that ISO, without a browser or internet connection.

The guide is bundled at `/usr/share/doc/hafthios/` in the live image. The disk installer copies this directory into the installed system. The register describes the source ISO, not a fresh inventory of later installed-system changes. See [docs/index.md](docs/index.md) for maintenance details.

## Download and try

Open this repository's **Actions → Build prototype ISO**, choose a successful run, and download **hafthiOS-prototype** while signed in to GitHub. Extract the artifact archive to find the `.iso`, its SHA256 file, and size report.

First test in a virtual machine: select the ISO as an optical boot image, enable 3D graphics acceleration, give the VM 4 GB RAM and a disposable virtual disk. Use an **x86_64 VM**; Apple Silicon requires x86 emulation for this image. Native ARM images are not available yet. CI boots the live ISO, installs it on a disposable disk, and boots that disk without the ISO using both BIOS and UEFI firmware.

The ISO size is measured on each build. Fitting a marketed 1 GB USB means staying below **1,000,000,000 bytes**; this is a target, not a promise. The live session has no persistence. Wireless, graphics hardware and Secure Boot compatibility are not validated yet.

## Build on Arch Linux

```sh
sudo pacman -S --needed archiso grub python mtools mkinitcpio rust git pkgconf wayland libxkbcommon systemd-libs alsa-lib
sudo bash scripts/build-iso.sh
```

Output is in `out/`. The script copies Archiso's baseline profile into a temporary workspace, adds the graphical session, and builds it using the official `mkarchiso` tool. Run it on a build machine; it installs packages only into the image root, not onto a selected target disk.

## Roadmap

The desktop now includes a **Living village** background, controlled from the
right-hand Hafþi panel. The original ship travels from a growing coastal village;
villagers trade, fish and work while slow waves move across the bay. Aggregate
CPU activity adds workers, received network traffic adds trade, and a recognized
CPU temperature sensor warms the light. VM temperature sensors may be unavailable.
Pause freezes the scene; **Save energy** reduces drawing to five frames per second.
Village progress and preferences persist on the installed system. This is a
procedural first version rather than a prerecorded film or full village simulation.

CI renders the actual scene before building, then verifies that the native GTK4
background draws in Niri, pauses and resumes, disables and re-enables, and starts
after installed BIOS/UEFI login.

- Boot and validate the graphical prototype in a VM.
- Test live language, keyboard and network settings on real hardware.
- Test the whole-disk installer on disposable physical test hardware.
- Test the Niri desktop, bundled Hafþi and first-use Chrome download on real hardware.
- Test real hardware and minimize the measured ISO size.

Hafþi OS is an independent project, not an official Arch Linux distribution. Individual bundled packages retain their own licenses.

## Quiet startup

The live image shows an animated ship splash during OS startup. Press **Esc** to toggle boot details, and press it again to return to the ship. Firmware screens before the OS starts remain controlled by the computer. The welcome screen and offline guide remain available after boot.

## Complete ISO file register

**Hafþi OS Guide** (or **F1**) opens **All ISO files**. Search by full or partial path, package name, or layer. The register covers every filesystem entry in the ISO filesystem, the compressed live system, the early and main initramfs, and the EFI FAT image, including directories, hidden files, links and device nodes. Ordinary data archives are indexed as files, rather than interpreting library/archive members as filesystem entries. Runtime virtual mounts such as `/proc` are not files shipped in the ISO.

Each record includes its layer, path, type, byte size where applicable, permissions, UID/GID, link target, and verified live-package owner/version/description where available. Project explanations are identified separately from location-based inference; unknown file-specific roles are explicitly marked. A package description describes the package, not a claim that every file has that exact purpose.

The local database is `/usr/share/doc/hafthios/file-register.sqlite`. A copy is also at `/hafthios-file-register.sqlite` in the ISO filesystem. The build exports `hafthios-file-register.csv` and `hafthios-file-register.sqlite` next to the ISO, with final container sizes. The embedded register leaves the final compressed live-image size unspecified because that container is generated after embedding the register. Every embedded layer/path/type is compared against a fresh extraction of the final ISO.

Choose **Project source guide** for the separate, detailed source explanations and snapshots.

## Live desktop shortcuts

- **Super + Enter**: open Hafþi.
- **Super + B**: open or download Google Chrome.
- **Super + Space**: show or hide the right-hand desktop panel.
- **Super + D**: open display settings.
- **Super + G**: open the local file guide.
- **Super + Left / Right**: switch columns.
- **Super + Q**: close the focused window.

Use at least **4 GB RAM** for the desktop and first-use browser download. The live writable layer can use up to half the RAM. Niri requires accelerated graphics, including virtual 3D acceleration in a VM. The welcome screen can run without it. The live session includes Fish, audio services, common Intel/AMD graphics and Wi-Fi firmware, and normal Arch package tools; disk installation starts only after the explicit erase confirmation. Hafþi is built from a pinned source commit in `scripts/build-hafthi.sh` and retains its MIT license.

## Live settings

The desktop panel stays at the right edge. **Hide panel** gives the space back
to your windows and leaves a small edge tab to reopen it. Its hidden state is
remembered. Keyboard shortcuts open the same panel rather than creating copies.

**Display settings** lists connected displays, their advertised resolutions and
refresh rates, plus UI scaling. **Try display settings** gives you 15 seconds to
keep the change. Unconfirmed changes revert; an independent safety process also
restores the previous mode if the panel crashes. Confirmed settings survive
restart on an installed system and are preserved when changing language.
VM resolution options depend on the virtual graphics device.

Choose **Language and keyboard** on the welcome screen or in the desktop controls.
English and Swedish interface language can be selected independently of US and
Swedish keyboard layouts. **F3** opens these settings; **Super + comma** opens
settings inside Niri. Press **Esc** to return from settings or network status.
The welcome screen, desktop controls and settings support Swedish; the file guide
and installation details remain in English. The locale also applies to new
terminal sessions. Existing applications retain their environment.

The Niri keyboard changes immediately after **Apply**. Before entering Niri,
the welcome screen's keyboard changes when that screen is reopened. Settings are stored in your home. They disappear when restarting the live ISO, but persist on an installed disk.

**Network settings** shows current devices and connections. **Configure connection**
opens NetworkManager's connection tool for Wi-Fi and Ethernet; the status refreshes
when the tool closes. Wi-Fi hardware still needs testing on physical machines.

If Niri fails to start, the welcome screen returns with graphics advice and
actual diagnostics. In UTM use **virtio-vga-gl (GPU Supported)** and fully restart
the VM after changing its display adapter. Logs remain in the live home under
`~/.local/state/hafthios/` until restart.

## Installer testing and limits

Start with an empty disposable VM disk of at least 16 GiB. Secure Boot is not
supported. The installer writes a removable UEFI fallback loader without changing
firmware NVRAM. The BIOS boot partition supports legacy firmware on the same disk.
After the animated ship splash, the installed system shows a graphical password
login. Sign in as `hafthi` with the password chosen during installation; Niri and
Hafthi start with your saved language and keyboard settings. Logging out returns
to the greeter. Ctrl+Alt+F2 opens a text console for recovery.

The automated VM test uses a throwaway password only for its newly created virtual
disk. There is no automatic disk-erasing test service or installer backdoor in the
ISO. It verifies real disk boot with the optical image absent, rejection of a wrong password, graphical password login,
copied Chrome profile, Swedish language/layout persistence, ext4 root and removal of the live login/sudo
policy. Real hardware still needs validation before using disks with valuable data.

For test-script-only corrections, the build workflow can reuse an existing ISO
with the `iso_run_id` manual input, or a commit message containing
`[retest-iso:RUN_ID]`. This downloads the original ISO unchanged and runs the
current VM tests against it. `iso-source.txt` records the original build run;
the source snapshots inside the ISO still describe that original build.

A reused-ISO installation retest uses KVM when the runner supports it, with TCG
as fallback. Ship animation and Esc toggling remain part of a full TCG build;
the faster KVM retest checks the installer, applications and BIOS/UEFI disk boot.
