#!/usr/bin/env bash
# Enforces file-ownership boundaries between branches. Design reference:
# plans/reports/plan.md §2 (merge-safety), §6 (output control).
#
# Usage: scripts/check-ownership.sh [base-ref]
#   base-ref defaults to origin/dev. Compares the current branch's changed
#   files against the owner declared in ROLE (env var) or inferred from the
#   branch name (feat/<role>).
#
# Exits non-zero if:
#   - a changed file falls outside the branch owner's allowed paths
#   - a changed file introduces a new top-level directory not already seeded

set -euo pipefail

BASE_REF="${1:-origin/dev}"
BRANCH="$(git branch --show-current)"
ROLE="${ROLE:-${BRANCH#feat/}}"

declare -A OWNED=(
  [data-plane]="contracts.py registry/ ingest/ sim/ store/ eval/ fixtures/ tests/data_plane/"
  [trust-engine]="trust/ tests/trust/"
  [agents]="worldstate/ agents/ graph/ prompts/ tests/agents/"
  [tools-runner-api]="tools/ schedule/ verify/ api/ tests/tools/"
  [operator-ux]="frontend/"
)

# Paths every branch may append to (never reorder), matched by prefix too.
APPEND_ONLY="plans/ .env.example tests/invariants/ docs/ requirements/"

if [[ -z "${OWNED[$ROLE]:-}" ]]; then
  echo "check-ownership: unknown role '$ROLE' (branch: $BRANCH). Set ROLE explicitly or run from a feat/<role> branch." >&2
  exit 2
fi

CHANGED_FILES="$(git diff --name-only "$BASE_REF"...HEAD || true)"
if [[ -z "$CHANGED_FILES" ]]; then
  echo "check-ownership: no changes vs $BASE_REF. OK."
  exit 0
fi

# Existing top-level entries at BASE_REF — anything new outside this set is
# a forbidden new top-level directory (§2: "forbidden. Need one? Ask on dev").
EXISTING_TOP_LEVEL="$(git ls-tree --name-only "$BASE_REF" | sort)"

fail=0

while IFS= read -r f; do
  [[ -z "$f" ]] && continue

  top="${f%%/*}"
  if [[ "$f" == "$top" ]]; then
    # It's already a top-level file (e.g. contracts.py) — fine, checked below.
    :
  elif ! grep -qxF "$top" <<<"$EXISTING_TOP_LEVEL"; then
    echo "FORBIDDEN: '$f' introduces new top-level directory '$top/' — ask on dev to have it seeded (§2)." >&2
    fail=1
    continue
  fi

  allowed=0
  for pattern in ${OWNED[$ROLE]} $APPEND_ONLY; do
    if [[ "$f" == "$pattern"* || "$f" == "$pattern" ]]; then
      allowed=1
      break
    fi
  done

  if [[ "$allowed" -eq 0 ]]; then
    echo "OWNERSHIP VIOLATION: '$f' is outside $ROLE's owned/append-only paths." >&2
    fail=1
  fi
done <<<"$CHANGED_FILES"

if [[ "$fail" -ne 0 ]]; then
  echo "check-ownership: FAILED for role '$ROLE'." >&2
  exit 1
fi

echo "check-ownership: OK for role '$ROLE' ($(wc -l <<<"$CHANGED_FILES") file(s) checked)."
