#!/usr/bin/env bash
set -euo pipefail
# Reproducible source revision; compilation happens in the Arch build container.
revision=636e76f86a828546178c71310297a7e33b228273
destination=$1
workspace=$(mktemp -d /var/tmp/hafthi-source.XXXXXX)
trap 'rm -rf -- "$workspace"' EXIT
git -C "$workspace" init -q
git -C "$workspace" remote add origin https://github.com/pdahlbeck/hafthi.git
git -C "$workspace" fetch --depth=1 origin "$revision"
git -C "$workspace" checkout --detach FETCH_HEAD
(cd "$workspace" && cargo build --release)
install -Dm755 "$workspace/target/release/hafthi" "$destination/usr/local/bin/hafthi"
install -Dm755 "$workspace/scripts/g" "$destination/usr/local/libexec/hafthi/g"
install -Dm644 "$workspace/LICENSE" "$destination/usr/share/licenses/hafthi/LICENSE"
printf '%s\n' "$revision" > "$destination/usr/share/licenses/hafthi/source-revision"
