#!/usr/bin/env bash
#
# GitHub Labels Sync Script
# Syncs label taxonomy to GitHub repository
# Compatible with bash 3.x (macOS default)
#
# Usage: ./gh-sync-labels.sh OWNER/REPO [--dry-run]
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_create() { echo -e "${CYAN}[CREATE]${NC} $1"; }
log_skip() { echo -e "${NC}[SKIP]${NC} $1"; }

# Parse arguments
REPO="${1:-}"
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            ;;
    esac
done

if [[ -z "$REPO" ]]; then
    echo "Usage: $0 OWNER/REPO [--dry-run]"
    echo ""
    echo "Options:"
    echo "  --dry-run    Preview changes without applying them"
    exit 1
fi

echo ""
echo "=============================================="
echo "     GitHub Labels Sync"
echo "=============================================="
echo ""
log_info "Repository: $REPO"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN MODE - No changes will be made"
fi
echo ""

# Verify gh CLI
if ! command -v gh &> /dev/null; then
    log_error "GitHub CLI (gh) is not installed"
    exit 1
fi

# Verify authentication
if ! gh auth status &> /dev/null; then
    log_error "GitHub CLI is not authenticated"
    exit 1
fi

# Get existing labels
log_info "Fetching existing labels from repository..."
EXISTING_LABELS=$(gh label list --repo "$REPO" --json name --limit 200 -q '.[].name' 2>/dev/null || echo "")

# Function to check if label exists
label_exists() {
    local name="$1"
    echo "$EXISTING_LABELS" | grep -q "^${name}$" && return 0 || return 1
}

# Function to create or update a label
sync_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    if label_exists "$name"; then
        log_skip "Label '$name' already exists"
    else
        log_create "Label '$name' (color: $color)"
        if [[ "$DRY_RUN" == "false" ]]; then
            gh label create "$name" --repo "$REPO" --color "$color" --description "$description" 2>/dev/null || true
        fi
    fi
}

log_info "Syncing labels..."
echo ""

# Issue Type Labels
log_info "Creating type labels..."
sync_label "epic" "7057ff" "Major initiative containing multiple stories"
sync_label "story" "0075ca" "User-facing feature with acceptance criteria"
sync_label "task" "008672" "Technical work item"
sync_label "bug" "d73a4a" "Something isn't working"
sync_label "feature" "a2eeef" "New feature request"
sync_label "documentation" "0075ca" "Improvements or additions to documentation"
sync_label "enhancement" "84b6eb" "Improvement to existing functionality"

# Priority Labels
echo ""
log_info "Creating priority labels..."
sync_label "priority:critical" "b60205" "Must be fixed immediately - production down"
sync_label "priority:high" "d93f0b" "Should be fixed soon - significant impact"
sync_label "priority:medium" "fbca04" "Normal priority - plan for next sprint"
sync_label "priority:low" "0e8a16" "Low priority - nice to have"

# Status Labels
echo ""
log_info "Creating status labels..."
sync_label "status:backlog" "ededed" "In backlog, not yet prioritized"
sync_label "status:ready" "c5def5" "Ready to be worked on"
sync_label "status:in-progress" "fbca04" "Currently being worked on"
sync_label "status:in-review" "1d76db" "PR created, awaiting review"
sync_label "status:blocked" "d73a4a" "Blocked by external dependency"
sync_label "status:done" "0e8a16" "Completed and merged"

# Component Labels
echo ""
log_info "Creating component labels..."
sync_label "component:frontend" "bfdadc" "Frontend/UI related"
sync_label "component:backend" "bfd4f2" "Backend/API related"
sync_label "component:infrastructure" "d4c5f9" "Infrastructure/DevOps related"
sync_label "component:testing" "fef2c0" "Testing infrastructure"
sync_label "component:security" "f9d0c4" "Security related"

# Phase Labels (SDLC)
echo ""
log_info "Creating SDLC phase labels..."
sync_label "phase:strategic" "c2e0c6" "Phase 1 - Strategic Intelligence"
sync_label "phase:development" "fef2c0" "Phase 2 - Automated Development"
sync_label "phase:deployment" "f9d0c4" "Phase 3 - Orchestrated Deployment"
sync_label "phase:lifecycle" "d4c5f9" "Phase 4 - Lifecycle Management"

# Compliance Labels (CDD)
echo ""
log_info "Creating compliance labels..."
sync_label "cdd:evidence-required" "5319e7" "Requires CDD evidence collection"
sync_label "cdd:verified" "0e8a16" "CDD evidence verified"
sync_label "bdd:has-scenarios" "1d76db" "Has BDD Gherkin scenarios"

echo ""

# Summary
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN complete - no changes were made"
    echo ""
    echo "Run without --dry-run to apply changes:"
    echo "  $0 $REPO"
else
    log_success "Label sync complete!"
    echo ""
    echo "View labels at:"
    echo "  https://github.com/$REPO/labels"
fi
