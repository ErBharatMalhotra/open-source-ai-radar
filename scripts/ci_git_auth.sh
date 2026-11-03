#!/usr/bin/env bash
# Configure git credentials for CI pushes.
#
# Why this exists: the REPO_TOKEN secret is a fine-grained PAT. When it lacks
# "Contents: Read and write" (or gets rotated/revoked) every scheduled workflow
# dies at the push step with:
#     remote: Permission to <owner>/<repo>.git denied
#     fatal: unable to access '...': The requested URL returned error: 403
#
# So: validate the token first, then fall back to the run's own GITHUB_TOKEN,
# which can push because each workflow declares `permissions: contents: write`.
# A bad secret now produces a warning instead of a hard failure.
set -euo pipefail

repo="${GITHUB_REPOSITORY:-ErBharatMalhotra/open-source-ai-radar}"
probe_file="${TMPDIR:-/tmp}/radar-repo-permissions.json"

git config user.name "Bharat Malhotra"
git config user.email "mr.bharatmalhotra@gmail.com"

token=""

if [ -n "${REPO_TOKEN:-}" ]; then
  status=$(curl -sS -o "$probe_file" -w "%{http_code}" \
    -H "Authorization: Bearer ${REPO_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${repo}" 2>/dev/null || echo "000")

  can_push="false"
  if [ "$status" = "200" ] && grep -Eq '"push"[[:space:]]*:[[:space:]]*true' "$probe_file"; then
    can_push="true"
  fi

  if [ "$can_push" = "true" ]; then
    token="$REPO_TOKEN"
    echo "::notice::REPO_TOKEN validated with push access to ${repo}"
  else
    echo "::warning title=REPO_TOKEN unusable::REPO_TOKEN cannot push to ${repo} (HTTP ${status}). Falling back to GITHUB_TOKEN. Recreate the secret with 'Contents: Read and write' (fine-grained) or the 'repo' scope (classic)."
  fi
else
  echo "::notice::REPO_TOKEN not set - using GITHUB_TOKEN"
fi

if [ -z "$token" ]; then
  token="${GITHUB_TOKEN:-}"
fi

if [ -z "$token" ]; then
  echo "::error::No token available to push to ${repo}"
  exit 1
fi

# actions/checkout stores its credential in a local extraheader. Clear it so the
# token we just validated is the one git actually uses.
git config --unset-all "http.https://github.com/.extraheader" 2>/dev/null || true
git remote set-url origin "https://x-access-token:${token}@github.com/${repo}.git"

# Never print the token itself, only that auth is configured.
echo "Git auth configured for ${repo} (token: $([ "$token" = "${REPO_TOKEN:-}" ] && echo REPO_TOKEN || echo GITHUB_TOKEN))"
