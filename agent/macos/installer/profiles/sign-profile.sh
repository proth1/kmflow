#!/bin/bash
# sign-profile.sh — Sign a .mobileconfig profile for non-MDM (user-facing) distribution.
#
# MDM solutions push unsigned profiles over their own authenticated channel.
# For direct user installation (e.g., emailed profile or hosted download),
# the profile should be signed with an S/MIME certificate so macOS shows a
# verified identity in System Settings rather than "Unsigned".
#
# Usage:
#   sign-profile.sh <PROFILE_PATH> <CERT_PEM> <KEY_PEM> [CHAIN_PEM]
#
# Env overrides (alternative to positional args):
#   PROFILE_PATH   Path to the .mobileconfig to sign
#   CERT           Path to the PEM-encoded signing certificate
#   KEY            Path to the PEM-encoded private key
#   CHAIN          Path to the PEM-encoded intermediate certificate chain (optional)
#
# Output:
#   <basename>-signed.mobileconfig  (in the same directory as the input profile)
#
# Requirements:
#   - openssl (ships with macOS or install via brew)
#   - A valid S/MIME certificate issued by a trusted CA (or your enterprise CA)
#
# Example:
#   CERT=certs/signing.pem KEY=certs/signing.key CHAIN=certs/chain.pem \
#     sign-profile.sh com.kmflow.agent.mobileconfig

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters (positional args take precedence over env vars)
# ---------------------------------------------------------------------------
PROFILE_PATH="${1:-${PROFILE_PATH:-}}"
CERT="${2:-${CERT:-}}"
KEY="${3:-${KEY:-}}"
CHAIN="${4:-${CHAIN:-}}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ -z "$PROFILE_PATH" ]]; then
    echo "ERROR: PROFILE_PATH is required." >&2
    echo "Usage: sign-profile.sh <PROFILE_PATH> <CERT_PEM> <KEY_PEM> [CHAIN_PEM]" >&2
    exit 1
fi

if [[ -z "$CERT" ]]; then
    echo "ERROR: CERT is required (path to PEM-encoded signing certificate)." >&2
    exit 1
fi

if [[ -z "$KEY" ]]; then
    echo "ERROR: KEY is required (path to PEM-encoded private key)." >&2
    exit 1
fi

if [[ ! -f "$PROFILE_PATH" ]]; then
    echo "ERROR: Profile not found: $PROFILE_PATH" >&2
    exit 1
fi

if [[ ! -f "$CERT" ]]; then
    echo "ERROR: Certificate not found: $CERT" >&2
    exit 1
fi

if [[ ! -f "$KEY" ]]; then
    echo "ERROR: Private key not found: $KEY" >&2
    exit 1
fi

if [[ -n "$CHAIN" && ! -f "$CHAIN" ]]; then
    echo "ERROR: Certificate chain file not found: $CHAIN" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Derive output path
# ---------------------------------------------------------------------------
PROFILE_DIR="$(dirname "$PROFILE_PATH")"
PROFILE_BASENAME="$(basename "$PROFILE_PATH" .mobileconfig)"
SIGNED_PROFILE="${PROFILE_DIR}/${PROFILE_BASENAME}-signed.mobileconfig"

echo "=== KMFlow Profile Signing ==="
echo "  Input:   $PROFILE_PATH"
echo "  Cert:    $CERT"
echo "  Key:     $KEY"
echo "  Chain:   ${CHAIN:-<none>}"
echo "  Output:  $SIGNED_PROFILE"
echo ""

# ---------------------------------------------------------------------------
# Build openssl smime arguments
# ---------------------------------------------------------------------------
OPENSSL_ARGS=(
    smime
    -sign
    -signer  "$CERT"
    -inkey   "$KEY"
    -outform der
    -nodetach           # embed the content in the signature (required for profiles)
    -in      "$PROFILE_PATH"
    -out     "$SIGNED_PROFILE"
)

# Append intermediate chain if provided (macOS verifier needs the full chain)
if [[ -n "$CHAIN" ]]; then
    OPENSSL_ARGS+=( -certfile "$CHAIN" )
fi

# ---------------------------------------------------------------------------
# Sign
# ---------------------------------------------------------------------------
echo "--- Signing profile ---"
openssl "${OPENSSL_ARGS[@]}"

# ---------------------------------------------------------------------------
# Verify the output is a valid DER-encoded CMS SignedData structure
# ---------------------------------------------------------------------------
echo ""
echo "--- Verifying signed profile ---"
if openssl smime -verify -inform der -noverify -in "$SIGNED_PROFILE" -out /dev/null 2>&1; then
    echo "  Signature structure: valid"
else
    echo "  WARNING: openssl smime -verify returned non-zero." >&2
    echo "           This may be expected if the cert is not in the system trust store." >&2
    echo "           Verify manually: openssl smime -verify -inform der -in $SIGNED_PROFILE" >&2
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
PROFILE_SIZE="$(du -sh "$SIGNED_PROFILE" | cut -f1)"
echo ""
echo "=== Profile Signing Complete ==="
echo "  Output: $SIGNED_PROFILE"
echo "  Size:   $PROFILE_SIZE"
echo ""
echo "Install on a test device to confirm the identity shown in System Settings."
