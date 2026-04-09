#!/usr/bin/env bash
# Create a PR with bot changes instead of pushing directly to main.
#
# Usage:
#   .github/scripts/bot-pr.sh <branch_prefix> <commit_message> <add_paths...>
#
# Example:
#   .github/scripts/bot-pr.sh bot/whisper "Add Whisper data" talks/*/*/source/whisper.json
#
# Requirements:
#   - GH_TOKEN must be set (for gh CLI)
#   - Must be run from repo root with git configured

set -euo pipefail

BRANCH_PREFIX="$1"; shift
COMMIT_MSG="$1"; shift
ADD_PATHS=("$@")

# Stage files
git add "${ADD_PATHS[@]}"

# Check for changes
if git diff --cached --quiet; then
  echo "No changes to commit"
  exit 0
fi

# Create branch with timestamp to avoid collisions
BRANCH="${BRANCH_PREFIX}/$(date +%Y%m%d-%H%M%S)-${RANDOM}"

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git checkout -b "$BRANCH"
git commit -m "$COMMIT_MSG"
git push -u origin "$BRANCH"

PR_URL=$(gh pr create \
  --title "$COMMIT_MSG" \
  --body "Automated PR by GitHub Actions." \
  --base main \
  --head "$BRANCH")

echo "Created PR: $PR_URL"

# Try auto-merge first (requires branch protection with required checks).
# Falls back to immediate merge if auto-merge is not available.
if gh pr merge --auto --merge "$PR_URL" 2>/dev/null; then
  echo "Auto-merge enabled"
else
  echo "Auto-merge not available, merging immediately"
  gh pr merge --merge "$PR_URL"
fi
