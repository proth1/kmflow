#!/bin/bash
# notarize.sh — Submit a signed .app bundle to Apple Notary Service and staple the ticket.
# Usage: notarize.sh <APP_PATH>
# Env:   APPLE_ID       Apple ID email used for notarization
#        TEAM_ID        Apple Developer Team ID
#        APP_PASSWORD   App-specific password for the Apple ID
#        KMFLOW_CODESIGN_IDENTITY  (default: "-", only used for display)

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
APP_PATH="${1:?Usage: notarize.sh <APP_PATH>}"

# ---------------------------------------------------------------------------
# Guard: require APPLE_ID for release builds, skip only for dev builds
# ---------------------------------------------------------------------------
if [[ -z "${APPLE_ID:-}" ]]; then
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        echo "ERROR: APPLE_ID not set but KMFLOW_RELEASE_BUILD=1." >&2
        echo "       Notarization is mandatory for release builds." >&2
        exit 1
    fi
    echo "Skipping notarization: APPLE_ID not set (dev build)"
    exit 0
fi

TEAM_ID="${TEAM_ID:?TEAM_ID environment variable is required for notarization}"
APP_PASSWORD="${APP_PASSWORD:?APP_PASSWORD environment variable is required for notarization}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: APP_PATH does not exist or is not a directory: $APP_PATH" >&2
    exit 1
fi

APP_NAME="$(basename "$APP_PATH" .app)"
ZIP_PATH="${TMPDIR:-/tmp}/${APP_NAME}-notarize-$$.zip"

echo "=== KMFlow Agent Notarization ==="
echo "  App:     $APP_PATH"
echo "  Apple ID: $APPLE_ID"
echo "  Team ID:  $TEAM_ID"
echo "  Zip:      $ZIP_PATH"
echo ""

# Cleanup on exit (success or failure)
cleanup() {
    if [[ -f "$ZIP_PATH" ]]; then
        echo "  Removing temporary zip: $ZIP_PATH"
        rm -f "$ZIP_PATH"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Step 1: Create zip archive for upload
# ---------------------------------------------------------------------------
echo "--- Step 1: Creating zip archive ---"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
ZIP_SIZE="$(du -sh "$ZIP_PATH" | cut -f1)"
echo "  Created: $ZIP_PATH ($ZIP_SIZE)"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Submit to Apple Notary Service and wait for result
# ---------------------------------------------------------------------------
echo "--- Step 2: Submitting to Apple Notary Service ---"
echo "  (This may take several minutes...)"
SUBMIT_OUTPUT="$(xcrun notarytool submit "$ZIP_PATH" \
    --apple-id  "$APPLE_ID" \
    --team-id   "$TEAM_ID" \
    --password  "$APP_PASSWORD" \
    --wait 2>&1)"
echo "$SUBMIT_OUTPUT"

# Extract the submission ID and verify the status is "Accepted"
SUBMISSION_ID="$(echo "$SUBMIT_OUTPUT" | grep -m1 'id:' | awk '{print $2}')"
if [[ -z "$SUBMISSION_ID" ]]; then
    echo "ERROR: Could not extract submission ID from notarytool output." >&2
    exit 1
fi

NOTARY_STATUS="$(echo "$SUBMIT_OUTPUT" | grep -m1 'status:' | awk '{print $2}')"
if [[ "$NOTARY_STATUS" != "Accepted" ]]; then
    echo "ERROR: Notarization was NOT accepted (status: ${NOTARY_STATUS:-unknown})." >&2
    echo "       Fetching detailed log for submission $SUBMISSION_ID..." >&2
    xcrun notarytool log "$SUBMISSION_ID" \
        --apple-id "$APPLE_ID" \
        --team-id "$TEAM_ID" \
        --password "$APP_PASSWORD" \
        2>&1 || true
    exit 1
fi
echo "  Notarization accepted (submission: $SUBMISSION_ID)."
echo ""

# ---------------------------------------------------------------------------
# Step 3: Staple the notarization ticket to the .app
# ---------------------------------------------------------------------------
echo "--- Step 3: Stapling notarization ticket ---"
xcrun stapler staple "$APP_PATH"
echo "  Ticket stapled."
echo ""

# ---------------------------------------------------------------------------
# Step 4: Verify Gatekeeper accepts the bundle
# ---------------------------------------------------------------------------
echo "--- Step 4: Gatekeeper assessment ---"
spctl --assess --type exec -vvv "$APP_PATH"

echo ""
echo "=== Notarization complete ==="
