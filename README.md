# Hafþi OS

A minimal Arch Linux desktop built around Hafþi, Wayland and Chrome.

## First prototype

This is an **x86_64 live USB prototype**, not a finished distribution. Boot into a graphical welcome screen, click **Install Hafþi OS**, choose a disk, and review the proposed desktop. The prototype **does not partition, format or install to any disk**. Its review screen explicitly marks installation as unavailable. This lets us test the live image and interface before adding a destructive installer backend.

The planned installed desktop is Arch Linux with Niri, Hafþi and Google Chrome. The prototype live image uses Cage and GTK to show only the installer. Hafþi and Chrome are not included in this first live image.

## Offline file guide

The English **Hafþi OS File Guide** explains every project file: its purpose, when it is used, connected files and implementation details. Click **Hafþi OS Guide** on the welcome screen or press **F1**. Search the guide and use **Show source** to read source snapshots matching that ISO, without a browser or internet connection.

The guide is bundled at `/usr/share/doc/hafthios/` in the live image. The future disk installer must also copy this directory into the installed system. The current prototype does not install to disk. See [docs/index.md](docs/index.md) for maintenance details.

## Download and try

Open this repository's **Actions → Build prototype ISO**, choose a successful run, and download **hafthiOS-prototype** while signed in to GitHub. Extract the artifact archive to find the `.iso`, its SHA256 file, and size report.

First test in a virtual machine: select the ISO as an optical boot image, give the VM 2 GB RAM and a disposable virtual disk. Use an **x86_64 VM**; Apple Silicon requires x86 emulation for this image. Native ARM images are not available yet. Both BIOS and UEFI boot files are built, but boot compatibility must be tested.

The ISO size is measured on each build. Fitting a marketed 1 GB USB means staying below **1,000,000,000 bytes**; this is a target, not a promise. The live session has no persistence. Wireless, graphics hardware and Secure Boot compatibility are not validated yet.

## Build on Arch Linux

```sh
sudo pacman -S --needed archiso grub python
sudo bash scripts/build-iso.sh
```

Output is in `out/`. The script copies Archiso's baseline profile into a temporary workspace, adds the graphical session, and builds it using the official `mkarchiso` tool. Run it on a build machine; it installs packages only into the image root, not onto a selected target disk.

## Roadmap

- Boot and validate the graphical prototype in a VM.
- Network setup, language and keyboard selection.
- A reviewed installer backend with explicit disk-erasure confirmation.
- Niri session, packaged Hafþi, and separately installed Google Chrome.
- Test real hardware and minimize the measured ISO size.

Hafþi OS is an independent project, not an official Arch Linux distribution. Individual bundled packages retain their own licenses.

## Quiet startup

The live image shows an animated ship splash during OS startup. Press **Esc** to toggle boot details, and press it again to return to the ship. Firmware screens before the OS starts remain controlled by the computer. The welcome screen and offline guide remain available after boot.

## Complete ISO file register

**Hafþi OS Guide** (or **F1**) opens **All ISO files**. Search by full or partial path, package name, or layer. The register covers every filesystem entry in the ISO filesystem, the compressed live system, the early and main initramfs, and the EFI FAT image, including directories, hidden files, links and device nodes. Ordinary data archives are indexed as files, rather than interpreting library/archive members as filesystem entries. Runtime virtual mounts such as `/proc` are not files shipped in the ISO.

Each record includes its layer, path, type, byte size where applicable, permissions, UID/GID, link target, and verified live-package owner/version/description where available. Project explanations are identified separately from location-based inference; unknown file-specific roles are explicitly marked. A package description describes the package, not a claim that every file has that exact purpose.

The local database is `/usr/share/doc/hafthios/file-register.sqlite`. A copy is also at `/hafthios-file-register.sqlite` in the ISO filesystem. The build exports `hafthios-file-register.csv` and `hafthios-file-register.sqlite` next to the ISO, with final container sizes. The embedded register leaves the final compressed live-image size unspecified because that container is generated after embedding the register. Every embedded layer/path/type is compared against a fresh extraction of the final ISO.

Choose **Project source guide** for the separate, detailed source explanations and snapshots.
