#!/bin/bash
# uninstall.sh — Completely remove the KMFlow Task Mining Agent from this Mac.
# Usage: uninstall.sh [--force]
#
# Without --force, prompts the user for confirmation before removing anything.
# With --force,    skips all prompts (suitable for MDM/scripted removal).

set -euo pipefail

FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        *) echo "Unknown argument: $arg" >&2; echo "Usage: uninstall.sh [--force]" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------
echo "=== KMFlow Agent Uninstaller ==="
echo ""
echo "This script will remove:"
echo "  - KMFlow Agent.app from /Applications"
echo "  - LaunchAgent: ~/Library/LaunchAgents/com.kmflow.agent.plist"
echo "  - Application Support: ~/Library/Application Support/KMFlowAgent/"
echo "  - Logs: ~/Library/Logs/KMFlowAgent/"
echo "  - Keychain items for com.kmflow.agent and com.kmflow.agent.consent"
echo ""

if [[ $FORCE -eq 0 ]]; then
    read -r -p "Are you sure you want to uninstall KMFlow Agent? [y/N] " CONFIRM
    echo ""
    case "$CONFIRM" in
        [Yy]|[Yy][Ee][Ss]) : ;;
        *)
            echo "Uninstall cancelled."
            exit 0
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# Step 1: Unload the LaunchAgent
# ---------------------------------------------------------------------------
echo "--- Step 1: Stopping KMFlow Agent ---"

USER_UID="$(id -u)"
launchctl bootout "gui/${USER_UID}" com.kmflow.agent 2>/dev/null \
    && echo "  LaunchAgent unloaded." \
    || echo "  LaunchAgent was not loaded (OK)."

# Kill any remaining process
if pgrep -x "KMFlowAgent" &>/dev/null; then
    echo "  Killing remaining KMFlowAgent process(es)..."
    pkill -x "KMFlowAgent" || true
    sleep 1
    pkill -9 -x "KMFlowAgent" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Step 2: Remove the LaunchAgent plist
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 2: Removing LaunchAgent plist ---"

PLIST="${HOME}/Library/LaunchAgents/com.kmflow.agent.plist"
if [[ -f "$PLIST" ]]; then
    rm "$PLIST"
    echo "  Removed: $PLIST"
else
    echo "  Not found (already removed): $PLIST"
fi

# ---------------------------------------------------------------------------
# Step 3: Remove the .app bundle
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 3: Removing KMFlow Agent.app ---"

APP_PATH="/Applications/KMFlow Agent.app"
if [[ -d "$APP_PATH" ]]; then
    rm -rf "$APP_PATH"
    echo "  Removed: $APP_PATH"
else
    echo "  Not found (already removed): $APP_PATH"
fi

# ---------------------------------------------------------------------------
# Step 4: Remove Application Support data
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 4: Removing Application Support data ---"

APP_SUPPORT="${HOME}/Library/Application Support/KMFlowAgent"
if [[ -d "$APP_SUPPORT" ]]; then
    rm -rf "$APP_SUPPORT"
    echo "  Removed: $APP_SUPPORT"
else
    echo "  Not found (already removed): $APP_SUPPORT"
fi

# ---------------------------------------------------------------------------
# Step 5: Remove log files
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 5: Removing log files ---"

LOG_DIR="${HOME}/Library/Logs/KMFlowAgent"
if [[ -d "$LOG_DIR" ]]; then
    rm -rf "$LOG_DIR"
    echo "  Removed: $LOG_DIR"
else
    echo "  Not found (already removed): $LOG_DIR"
fi

# ---------------------------------------------------------------------------
# Step 6: Remove Keychain items
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 6: Removing Keychain items ---"

# Remove all generic password items for the agent service name
for SERVICE in "com.kmflow.agent" "com.kmflow.agent.consent"; do
    # Loop to delete all accounts with this service name (may be multiple)
    DELETED=0
    while security delete-generic-password -s "$SERVICE" 2>/dev/null; do
        (( DELETED++ )) || true
    done
    if [[ $DELETED -gt 0 ]]; then
        echo "  Removed $DELETED keychain item(s) for service: $SERVICE"
    else
        echo "  No keychain items found for service: $SERVICE"
    fi
done

# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------
echo ""
echo "=== KMFlow Agent has been fully removed from this Mac. ==="
echo ""
echo "If you have questions, contact support@kmflow.ai."
