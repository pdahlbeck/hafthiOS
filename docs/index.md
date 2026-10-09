# Hafþi OS File Guide

An offline English reference with a complete ISO file register and a separate project source guide.

## Open it locally

On the live welcome screen, click **Hafþi OS Guide** or press **F1**. You can also run:

```sh
hafthios-welcome --guide
```

Search for a file name or a word in its explanation. Select a file to see its purpose, when it is used, connected files and implementation details. **Show source** displays the exact source snapshot bundled with that ISO; it does not execute it.

The bundle lives at `/usr/share/doc/hafthios/`. It needs no browser or internet connection. It is included in the live image and copied to the installed system by the disk installer.

## Read or maintain it in the repository

Articles are stored in [file-guide.json](file-guide.json). The catalog covers project source, configuration, tests, build automation and documentation files. Arch-provided files and third-party packages appear in the complete ISO register; this separate source-article catalog covers the project itself.

The ISO build checks that every project file has an entry and bundles source copies matching that build. Update the explanation when changing behavior. New undocumented files stop the documentation build. Generated ISO files, screenshots, logs and bytecode are excluded.

## Follow the startup chain

`autologin.conf` starts a live tty1 login → `.bash_profile` starts `hafthios-session` → Cage launches `hafthios-welcome` → the Guide button reads the local documentation bundle. **Try the desktop** exits Cage and starts the Niri user session, which launches Hafþi and desktop controls. The tty1 autologin user is `hafthi`.

The build chain is `build.yml` → `build-iso.sh` → `build-guide.py` and Archiso → `test-boot.py` → downloadable ISO and VM diagnostics.

## Quiet startup

The live image shows an animated ship splash during OS startup. Press **Esc** to toggle boot details, and press it again to return to the ship. Firmware screens before the OS starts remain controlled by the computer. The welcome screen and offline guide remain available after boot.

## Complete ISO file register

**Hafþi OS Guide** (or **F1**) opens **All ISO files**. Search by full or partial path, package name, or layer. The register covers every filesystem entry in the ISO filesystem, the compressed live system, the early and main initramfs, and the EFI FAT image, including directories, hidden files, links and device nodes. Ordinary data archives are indexed as files, rather than interpreting library/archive members as filesystem entries. Runtime virtual mounts such as `/proc` are not files shipped in the ISO.

Each record includes its layer, path, type, byte size where applicable, permissions, UID/GID, link target, and verified live-package owner/version/description where available. Project explanations are identified separately from location-based inference; unknown file-specific roles are explicitly marked. A package description describes the package, not a claim that every file has that exact purpose.

The local database is `/usr/share/doc/hafthios/file-register.sqlite`. A copy is also at `/hafthios-file-register.sqlite` in the ISO filesystem. The build exports `hafthios-file-register.csv` and `hafthios-file-register.sqlite` next to the ISO, with final container sizes. The embedded register leaves the final compressed live-image size unspecified because that container is generated after embedding the register. Every embedded layer/path/type is compared against a fresh extraction of the final ISO.

Choose **Project source guide** for the separate, detailed source explanations and snapshots.

## Installed graphical login

The installer enables greetd on tty1 after Plymouth, with an unprivileged Cage/gtkgreet login screen. PAM checks the installation password before `hafthios-installed-session` loads saved user settings and starts Niri. Live media keep the trial/install welcome screen. Other TTYs remain available for recovery.

The Niri desktop controls are a GTK4 Layer Shell panel anchored to the right edge.
Hide panel leaves an edge tab; Super+Shift+Space toggles it and Super+D opens display
settings. Advertised output modes and scaling come from Niri IPC. A 15-second
confirmation and independent restore watchdog protect display trials. Confirmed
modes are written to the validated user Niri configuration and survive language
changes. Panel visibility and display modes are saved separately from language.

## Programs

Super+Space opens native GTK program search. Installed desktop entries appear automatically; recent programs are shown first when the query is empty. Enter opens the selected result, arrows select and Escape dismisses. Hafthi can be resized horizontally by dragging its left or right edge.
