#!/bin/bash
# customize-profiles.sh — Replace placeholder values in MDM configuration profiles.
#
# Usage:
#   customize-profiles.sh --team-id <TEAM_ID> [--org-name <ORG_NAME>] [--output <dir>]
#
# This script reads the template .mobileconfig files in the same directory,
# replaces placeholder tokens, and writes the customized profiles to the
# output directory (default: ./customized/).
#
# Placeholders:
#   REPLACE_TEAM_ID   → Apple Developer Team ID (10-character string)
#   REPLACE_ORG_NAME  → Organization display name (optional, defaults to "KMFlow")
#
# The resulting profiles are ready for deployment via MDM (Jamf, Mosyle, etc.)
# or for manual signing with `security cms -S`.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEAM_ID=""
ORG_NAME="KMFlow"
OUTPUT_DIR="${SCRIPT_DIR}/customized"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 --team-id <TEAM_ID> [--org-name <ORG_NAME>] [--output <dir>]"
    echo ""
    echo "  --team-id   Apple Developer Team ID (required, 10-char alphanumeric)"
    echo "  --org-name  Organization display name (default: KMFlow)"
    echo "  --output    Output directory for customized profiles (default: ./customized/)"
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --team-id)  TEAM_ID="${2:?'--team-id requires a value'}";  shift 2 ;;
        --org-name) ORG_NAME="${2:?'--org-name requires a value'}"; shift 2 ;;
        --output)   OUTPUT_DIR="${2:?'--output requires a value'}"; shift 2 ;;
        -h|--help)  usage ;;
        *)          echo "ERROR: Unknown argument: $1" >&2; usage ;;
    esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ -z "$TEAM_ID" ]]; then
    echo "ERROR: --team-id is required." >&2
    usage
fi

# Apple Team IDs are 10-character alphanumeric strings
if [[ ! "$TEAM_ID" =~ ^[A-Z0-9]{10}$ ]]; then
    echo "ERROR: Team ID must be a 10-character alphanumeric string (got: '$TEAM_ID')." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Find template profiles
# ---------------------------------------------------------------------------
TEMPLATES=("${SCRIPT_DIR}"/*.mobileconfig)

if [[ ${#TEMPLATES[@]} -eq 0 || ! -f "${TEMPLATES[0]}" ]]; then
    echo "ERROR: No .mobileconfig template files found in ${SCRIPT_DIR}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Create output directory
# ---------------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"

echo "=== KMFlow Profile Customization ==="
echo "  Team ID:     $TEAM_ID"
echo "  Org Name:    $ORG_NAME"
echo "  Output:      $OUTPUT_DIR"
echo "  Templates:   ${#TEMPLATES[@]} file(s)"
echo ""

# ---------------------------------------------------------------------------
# Process each template
# ---------------------------------------------------------------------------
for TEMPLATE in "${TEMPLATES[@]}"; do
    FILENAME="$(basename "$TEMPLATE")"
    OUTPUT_FILE="${OUTPUT_DIR}/${FILENAME}"

    echo "  Processing: ${FILENAME}"

    CONTENT="$(cat "$TEMPLATE")"
    CONTENT="${CONTENT//REPLACE_TEAM_ID/$TEAM_ID}"
    CONTENT="${CONTENT//REPLACE_ORG_NAME/$ORG_NAME}"

    # Write content with placeholders replaced
    echo "$CONTENT" > "$OUTPUT_FILE"

    # Regenerate PayloadUUID values so each deployment gets unique IDs
    python3 -c "
import re, subprocess, sys
path = sys.argv[1]
content = open(path).read()
def new_uuid(m):
    uuid = subprocess.check_output(['uuidgen']).decode().strip().upper()
    return f'<key>PayloadUUID</key>\n    <string>{uuid}</string>'
content = re.sub(r'<key>PayloadUUID</key>\s*\n\s*<string>[A-F0-9-]+</string>', new_uuid, content)
open(path, 'w').write(content)
" "$OUTPUT_FILE"
    echo "    UUIDs regenerated"
    echo "    → ${OUTPUT_FILE}"
done

echo ""
echo "=== Customization complete ==="
echo ""
echo "Next steps:"
echo "  1. Review the customized profiles in ${OUTPUT_DIR}/"
echo "  2. Optionally sign them:  security cms -S -N '<signing cert>' -i <profile> -o <signed.mobileconfig>"
echo "  3. Deploy via MDM (Jamf, Mosyle, etc.)"
