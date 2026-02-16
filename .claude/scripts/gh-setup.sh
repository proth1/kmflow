#!/usr/bin/env bash
#
# GitHub Issues Setup Script
# Verifies gh CLI installation, authentication, and syncs labels
#
# Usage: ./gh-setup.sh [OWNER/REPO]
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get repository from argument or config
get_repository() {
    if [[ -n "${1:-}" ]]; then
        echo "$1"
    elif [[ -f ".claude/config/project-management.yaml" ]]; then
        grep -E '^repository:' .claude/config/project-management.yaml | awk '{print $2}' | tr -d '"' || echo ""
    else
        echo ""
    fi
}

REPO=$(get_repository "${1:-}")

echo ""
echo "=============================================="
echo "     GitHub Issues Setup & Verification"
echo "=============================================="
echo ""

# Step 1: Verify gh CLI installation
log_info "Checking GitHub CLI installation..."
if ! command -v gh &> /dev/null; then
    log_error "GitHub CLI (gh) is not installed."
    echo ""
    echo "Install GitHub CLI:"
    echo "  macOS:   brew install gh"
    echo "  Linux:   https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    echo "  Windows: winget install --id GitHub.cli"
    echo ""
    exit 1
fi

GH_VERSION=$(gh --version | head -1)
log_success "GitHub CLI installed: $GH_VERSION"

# Step 2: Verify authentication
log_info "Checking GitHub authentication..."
if ! gh auth status &> /dev/null; then
    log_error "GitHub CLI is not authenticated."
    echo ""
    echo "Authenticate with GitHub:"
    echo "  gh auth login"
    echo ""
    echo "For CI/CD environments, use a token:"
    echo "  export GH_TOKEN=<your-token>"
    echo ""
    exit 1
fi

AUTH_USER=$(gh api user --jq '.login' 2>/dev/null || echo "unknown")
log_success "Authenticated as: $AUTH_USER"

# Step 3: Verify repository access (if provided)
if [[ -n "$REPO" ]]; then
    log_info "Verifying repository access: $REPO"

    if ! gh repo view "$REPO" &> /dev/null; then
        log_error "Cannot access repository: $REPO"
        echo ""
        echo "Verify:"
        echo "  1. Repository exists"
        echo "  2. You have access to it"
        echo "  3. Repository name format is OWNER/REPO"
        echo ""
        exit 1
    fi

    PERMISSION=$(gh repo view "$REPO" --json viewerPermission -q '.viewerPermission')
    log_success "Repository access verified: $PERMISSION permission"

    # Step 4: Sync labels (if label taxonomy exists)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SYNC_SCRIPT="$SCRIPT_DIR/gh-sync-labels.sh"

    if [[ -f "$SYNC_SCRIPT" ]]; then
        log_info "Syncing labels to repository..."
        if bash "$SYNC_SCRIPT" "$REPO"; then
            log_success "Labels synced successfully"
        else
            log_warn "Label sync encountered issues (non-fatal)"
        fi
    else
        log_warn "Label sync script not found: $SYNC_SCRIPT"
    fi
else
    log_warn "No repository specified. Skipping repository verification."
    echo ""
    echo "To verify repository access, run:"
    echo "  ./gh-setup.sh OWNER/REPO"
fi

# Step 5: Display configuration summary
echo ""
echo "=============================================="
echo "           Configuration Summary"
echo "=============================================="
echo ""
echo "GitHub CLI Version: $GH_VERSION"
echo "Authenticated User: $AUTH_USER"
if [[ -n "$REPO" ]]; then
    echo "Repository:         $REPO"
    echo "Permission Level:   $PERMISSION"
fi
echo ""

# Step 6: Display next steps
echo "=============================================="
echo "              Next Steps"
echo "=============================================="
echo ""
echo "1. Create your first issue:"
echo "   gh issue create --repo $REPO --title \"My first issue\" --label story"
echo ""
echo "2. List issues:"
echo "   gh issue list --repo $REPO"
echo ""
echo "3. Create a feature branch:"
echo "   git checkout -b feature/123-my-feature"
echo ""
echo "4. Create a PR linked to issue:"
echo "   gh pr create --title \"#123: My feature\" --body \"Closes #123\""
echo ""
log_success "GitHub Issues setup complete!"
