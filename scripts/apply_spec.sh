#!/usr/bin/env bash
# Applies a drafted spec version: copies the proposal over the spec, runs CI, pushes,
# opens the PR and merges it. Run by the human after /spec-change, never by Claude.
set -euo pipefail

step() { printf '\n→ %s\n' "$*"; }
die() {
  printf '\n✗ %s\n' "$1" >&2
  exit 1
}

# Set before each step; printed if that step fails.
next="Nothing was changed."
trap 'printf "\n✗ Failed at line %s.\n%s\n" "$LINENO" "$next" >&2' ERR

[ $# -eq 1 ] || die "Usage: ./scripts/apply_spec.sh <version>   (for example 1.8)"
version="${1#v}"
branch="spec/v${version}"
spec="docs/spec/phase1-spec.md"
proposal="docs/spec-proposals/phase1-spec-v${version}.md"
title="spec: v${version}"

cd "$(git rev-parse --show-toplevel)"

# a) preconditions
current="$(git branch --show-current)"
[ "$current" = "$branch" ] ||
  die "On branch '${current}', expected '${branch}'. Run: git switch ${branch}"
[ -z "$(git status --porcelain)" ] ||
  die "The working tree is not clean. Commit or stash your changes, then run this again."
[ -f "$proposal" ] ||
  die "${proposal} does not exist. Run /spec-change to draft it, or check the version."
if cmp -s "$spec" "$proposal"; then
  die "${proposal} is identical to ${spec}. There is nothing to apply."
fi

# b) the diff
step "Diff between ${spec} and the proposal (q to leave)"
{ git diff --no-index --color=always -- "$spec" "$proposal" || true; } | less -R

# c) proposed ADRs
proposed="$(grep -l -E '^- Status: proposed[[:space:]]*$' docs/adr/ADR-*.md || true)"
if [ -n "$proposed" ]; then
  printf '\n⚠ These ADRs are still "Status: proposed". Accept them first:\n%s\n' "$proposed"
fi

# d) confirm
printf '\n'
read -r -p "Apply spec v${version}? (y/n) " answer
if [ "$answer" != "y" ]; then
  echo "Not applied. Nothing was changed."
  exit 0
fi

# e) apply
undo="To undo: git restore --source=HEAD --staged --worktree docs/spec docs/spec-proposals"

step "Copy the proposal over ${spec}"
next="$undo"
cp "$proposal" "$spec"
git rm -q "$proposal"
git add "$spec"

step "./scripts/ci_local.sh"
next="CI failed with the new spec in place, nothing is committed.
${undo}
Then fix the proposal on ${branch}, commit, and run this script again."
./scripts/ci_local.sh

step "Commit"
next="The commit failed; the new spec is staged.
Fix the cause and run: git commit -m '${title}'
${undo}"
git commit -q -m "$title"

rest="  gh pr create --base main --head ${branch} --title '${title}' --body 'Applies spec v${version}.'
  gh pr checks ${branch} --watch
  gh pr merge ${branch} --squash --delete-branch
  git switch main && git pull"

step "Push ${branch}"
next="The spec is committed on ${branch} but not pushed. Do not run this script again.
Fix the cause, then run:
  git push -u origin ${branch}
${rest}"
git push -u origin "$branch"

step "Pull request"
next="The branch is pushed but there is no PR yet. Do not run this script again.
Fix the cause, then run:
${rest}"
if [ -z "$(gh pr list --head "$branch" --state open --json number --jq '.[].number')" ]; then
  gh pr create --base main --head "$branch" --title "$title" \
    --body "Applies spec v${version}. The changes and their SC ids are in the \"Version history\" table at the end of the spec and in docs/decisions.md."
else
  echo "A PR for ${branch} is already open."
fi

step "Wait for checks"
next="The checks failed or could not be watched; the PR is open and not merged.
Look at them with: gh pr checks ${branch}
Fix on ${branch}, push, then run:
  gh pr checks ${branch} --watch
  gh pr merge ${branch} --squash --delete-branch
  git switch main && git pull"
sleep 10
gh pr checks "$branch" --watch

step "Squash-merge and delete the branch"
next="The checks passed but the merge failed. Fix the cause, then run:
  gh pr merge ${branch} --squash --delete-branch
  git switch main && git pull"
gh pr merge "$branch" --squash --delete-branch

step "Switch to main and pull"
next="The PR is merged. Finish with: git switch main && git pull"
git switch main
git pull

printf '\n✓ Spec v%s is applied and merged.\n' "$version"
