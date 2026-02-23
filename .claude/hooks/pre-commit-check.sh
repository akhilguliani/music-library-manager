#!/bin/bash
# Pre-commit hook: runs mypy and pytest before allowing git commit.
# Used by Claude Code's PreToolUse hook to gate commits.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only intercept git commit commands
if [[ ! "$COMMAND" =~ git[[:space:]].*commit ]]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# --- Gate 1: mypy ---
echo "Running mypy..." >&2
if ! mypy src/ --ignore-missing-imports 2>&1 >&2; then
  echo '{"decision":"block","reason":"mypy type check failed — fix errors before committing"}'
  exit 0
fi
echo "mypy: PASSED" >&2

# --- Gate 2: pytest ---
echo "Running pytest..." >&2
if ! python -m pytest tests/ -x -q --tb=short 2>&1 >&2; then
  echo '{"decision":"block","reason":"pytest failed — fix failing tests before committing"}'
  exit 0
fi
echo "pytest: PASSED" >&2

# All checks passed — allow the commit
exit 0
