#!/usr/bin/env bash
# Publish the generated data snapshot produced by a scheduled workflow run.
#
# Why this exists: Process Repos (every 2h), Discover Repos (4x/day) and the
# Daily Breakout job all regenerate the same whole-file artefacts
# (data/exports/**, README.md, the two Astro pages). GitHub's scheduler can
# start them at the same minute, or delay one of them by an hour, so `main`
# often moves while a run is still busy. A plain `git pull --rebase` then hits
# "CONFLICT (content)" on those generated files, aborts, and the whole run's
# data is thrown away -- see runs 44946046984 and 45082611738.
#
# Rules enforced here:
#   * Only generated artefacts are staged. Never `git add -A`.
#   * Conflicts in generated artefacts are resolved by keeping THIS run's
#     freshly generated snapshot (the newest data we have) and retrying.
#   * Conflicts anywhere else are a real conflict: abort and fail loudly
#     instead of silently dropping someone's change.
#   * Leftover edits the pipeline did not stage are stashed in this disposable
#     runner workspace, so they cannot abort the rebase (the cause of the
#     earlier "cannot pull with rebase: You have unstaged changes" failures).
set -uo pipefail

STAGED_PATHS=(
  "data/exports"
  "README.md"
  "web/src/layouts/Layout.astro"
  "web/src/pages/index.astro"
)

message="${1:-}"
if [ -z "$message" ]; then
  echo "::error::usage: ci_commit_data.sh \"<conventional commit message>\""
  exit 1
fi

git config user.name "Bharat Malhotra"
git config user.email "mr.bharatmalhotra@gmail.com"

for path in "${STAGED_PATHS[@]}"; do
  if [ -e "$path" ]; then
    git add -f -- "$path"
  fi
done

if git diff --staged --quiet; then
  echo "::notice::No generated data changes - nothing to publish"
  exit 0
fi

git commit -m "$message"

# The runner workspace is disposable, so anything the pipeline touched but did
# not stage must not be allowed to block the publish: a dirty tree is what made
# `git pull --rebase` fail with "cannot pull with rebase: You have unstaged
# changes" in runs 44822604564 and 44858768619. Stash instead of discarding so
# the leftovers can still be inspected in an emergency.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "::warning::Stashing leftovers that are not part of this snapshot:"
  git status --short --untracked-files=no | head -20
  git stash push --quiet -m "ci-leftovers" || true
fi

is_generated() {
  local file="$1" prefix
  for prefix in "${STAGED_PATHS[@]}"; do
    case "$file" in
      "$prefix" | "$prefix"/*) return 0 ;;
    esac
  done
  return 1
}

for attempt in 1 2 3; do
  if ! git fetch --quiet origin main; then
    echo "::warning::fetch of main failed (attempt $attempt) - retrying"
    sleep 5
    continue
  fi

  if ! git rebase origin/main; then
    conflicts=$(git diff --name-only --diff-filter=U)
    if [ -z "$conflicts" ]; then
      echo "::warning::rebase failed without conflicts (attempt $attempt)"
      git rebase --abort 2>/dev/null || true
      sleep 5
      continue
    fi

    unexpected=""
    while IFS= read -r file; do
      [ -z "$file" ] && continue
      if is_generated "$file"; then
        # During a rebase "--theirs" is the commit being replayed: this run.
        git checkout --theirs -- "$file" 2>/dev/null || git rm -f --quiet -- "$file" 2>/dev/null || true
        git add -f -- "$file" 2>/dev/null || true
      else
        unexpected="${unexpected}${file}"$'\n'
      fi
    done <<< "$conflicts"

    if [ -n "$unexpected" ]; then
      echo "::error::Conflict outside generated data - needs a human:"
      echo "$unexpected"
      git rebase --abort 2>/dev/null || true
      exit 1
    fi

    echo "::notice::Rebased on newer main; kept this run's generated snapshot."
    if ! git -c core.editor=true rebase --continue; then
      git rebase --abort 2>/dev/null || true
      echo "::warning::rebase --continue failed (attempt $attempt)"
      sleep 5
      continue
    fi
  fi

  if git push origin HEAD:main; then
    echo "::notice::Published generated data to main."
    exit 0
  fi
  echo "::warning::push rejected because main moved again (attempt $attempt)"
  sleep 5
done

echo "::error::Could not publish generated data after 3 attempts"
exit 1
