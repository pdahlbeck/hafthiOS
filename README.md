# Hafþi OS

A minimal Arch Linux desktop built around Hafþi, Wayland and Chrome.

## First prototype

This is an **x86_64 live USB prototype**, not a finished distribution. Boot into a graphical welcome screen, click **Install Hafþi OS**, choose a disk, and review the proposed desktop. The prototype **does not partition, format or install to any disk**. Its review screen explicitly marks installation as unavailable. This lets us test the live image and interface before adding a destructive installer backend.

The planned installed desktop is Arch Linux with Niri, Hafþi and Google Chrome. The prototype live image uses Cage and GTK to show only the installer. Hafþi and Chrome are not included in this first live image.

## Download and try

Open this repository's **Actions → Build prototype ISO**, choose a successful run, and download **hafthiOS-prototype** while signed in to GitHub. Extract the artifact archive to find the `.iso`, its SHA256 file, and size report.

First test in a virtual machine: select the ISO as an optical boot image, give the VM 2 GB RAM and a disposable virtual disk. Use an **x86_64 VM**; Apple Silicon requires x86 emulation for this image. Native ARM images are not available yet. Both BIOS and UEFI boot files are built, but boot compatibility must be tested.

The ISO size is measured on each build. Fitting a marketed 1 GB USB means staying below **1,000,000,000 bytes**; this is a target, not a promise. The live session has no persistence. Wireless, graphics hardware and Secure Boot compatibility are not validated yet.

## Build on Arch Linux

```sh
sudo pacman -S --needed archiso grub
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
