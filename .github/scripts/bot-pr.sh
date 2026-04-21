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

# Stage files — glob each path individually and skip patterns that match nothing.
# Callers may pass optimistic globs (e.g. work/timecodes.txt) that are absent when
# an upstream job failed; we still want to commit whatever partial artifacts exist.
shopt -s nullglob
EXISTING=()
for pattern in "${ADD_PATHS[@]}"; do
  matches=($pattern)
  if [ ${#matches[@]} -gt 0 ]; then
    EXISTING+=("${matches[@]}")
  else
    echo "  (skip: no match for $pattern)"
  fi
done
shopt -u nullglob

if [ ${#EXISTING[@]} -eq 0 ]; then
  echo "No paths matched any files — nothing to commit"
  exit 0
fi

git add "${EXISTING[@]}"

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
if gh pr merge --auto --delete-branch --merge "$PR_URL" 2>/dev/null; then
  echo "Auto-merge enabled (branch will be deleted after merge)"
else
  echo "Auto-merge not available, merging immediately"
  gh pr merge --delete-branch --merge "$PR_URL"
fi
