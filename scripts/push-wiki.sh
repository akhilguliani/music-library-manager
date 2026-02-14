#!/usr/bin/env bash
# Push wiki pages to GitHub wiki repository.
#
# Usage:
#   ./scripts/push-wiki.sh
#
# Prerequisites:
#   - GitHub wiki must be initialized (create at least one page via the web UI first)
#   - SSH key or HTTPS credentials configured for git push

set -euo pipefail

REPO="akhilguliani/music-library-manager"
WIKI_DIR="$(cd "$(dirname "$0")/.." && pwd)/wiki"
TEMP_DIR=$(mktemp -d)

echo "Cloning wiki repo..."
git clone "git@github.com:${REPO}.wiki.git" "$TEMP_DIR"

echo "Copying wiki pages..."
cp "$WIKI_DIR"/*.md "$TEMP_DIR/"

cd "$TEMP_DIR"
git add -A

if git diff --cached --quiet; then
    echo "No changes to push."
else
    git commit -m "Update wiki docs"
    git push
    echo "Wiki updated successfully."
fi

rm -rf "$TEMP_DIR"
