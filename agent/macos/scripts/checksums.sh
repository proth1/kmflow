#!/bin/bash
# KMFlow Agent — Generate SHA-256 checksums for release artifacts
#
# Usage: ./scripts/checksums.sh <build_dir>
# Optional: Set GPG_KEY_ID to sign the checksums file.

set -euo pipefail

BUILD_DIR="${1:?Usage: checksums.sh <build_dir>}"
CHECKSUMS_FILE="$BUILD_DIR/SHA256SUMS"

echo "Generating SHA-256 checksums..."

cd "$BUILD_DIR"
rm -f SHA256SUMS SHA256SUMS.sig

# Find all release artifacts (app bundles as zip, DMG, PKG)
ARTIFACTS=()

# Create a zip of the .app bundle for checksum purposes
for app in *.app; do
    if [ -d "$app" ]; then
        zip_name="${app%.app}.zip"
        if [ ! -f "$zip_name" ]; then
            ditto -c -k --keepParent "$app" "$zip_name"
        fi
        ARTIFACTS+=("$zip_name")
    fi
done

for ext in dmg pkg; do
    for f in *."$ext"; do
        [ -f "$f" ] && ARTIFACTS+=("$f")
    done
done

if [ ${#ARTIFACTS[@]} -eq 0 ]; then
    echo "No artifacts found in $BUILD_DIR"
    exit 1
fi

# Generate checksums
for artifact in "${ARTIFACTS[@]}"; do
    shasum -a 256 "$artifact" >> SHA256SUMS
done

echo "Checksums written to $CHECKSUMS_FILE"
cat SHA256SUMS

# Optional GPG signature
if [ -n "${GPG_KEY_ID:-}" ]; then
    echo ""
    echo "Signing checksums with GPG key $GPG_KEY_ID..."
    gpg --default-key "$GPG_KEY_ID" --detach-sign --armor SHA256SUMS
    echo "GPG signature: $CHECKSUMS_FILE.asc"
fi
