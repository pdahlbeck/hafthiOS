# Hafþi OS File Guide

An offline, English-language reference for every project-owned file in Hafþi OS.

## Open it locally

On the live welcome screen, click **Hafþi OS Guide** or press **F1**. You can also run:

```sh
hafthios-welcome --guide
```

Search for a file name or a word in its explanation. Select a file to see its purpose, when it is used, connected files and implementation details. **Show source** displays the exact source snapshot bundled with that ISO; it does not execute it.

The bundle lives at `/usr/share/doc/hafthios/`. It needs no browser or internet connection. It is included in the current live image; the future disk installer must copy the same bundle into the installed system. The prototype does not yet install to disk.

## Read or maintain it in the repository

Articles are stored in [file-guide.json](file-guide.json). The catalog covers project source, configuration, tests, build automation and documentation files. Arch-provided files and third-party packages are outside its scope.

The ISO build checks that every project file has an entry and bundles source copies matching that build. Update the explanation when changing behavior. New undocumented files stop the documentation build. Generated ISO files, screenshots, logs and bytecode are excluded.

## Follow the startup chain

`autologin.conf` starts a live tty1 login → `.bash_profile` starts `hafthios-session` → Cage launches `hafthios-welcome` → the Guide button reads the local documentation bundle.

The build chain is `build.yml` → `build-iso.sh` → `build-guide.py` and Archiso → `test-boot.py` → downloadable ISO and VM diagnostics.
